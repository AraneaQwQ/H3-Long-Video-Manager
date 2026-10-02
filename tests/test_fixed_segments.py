"""H3 Long Video Manager - fixed-length segmentation tests.

The rules the node must honour (user reports, 2026-10-03):
    every full-length segment, Motion Context included, has the SAME frame
    count, that count is <= the requested duration, and it stays on the
    17n+5 grid. The last segment takes whatever frames are left, grid or not:
    nothing is repeated, padded, or dropped, and H3 decides what to do with an
    off-grid length.
"""

import unittest

from core.h3_grid import (
    fixed_slice_frames,
    generate_fixed_segments,
    is_valid_h3_frame_count,
)


class TestFixedSliceFrames(unittest.TestCase):
    """The requested duration decides the length every full clip gets."""

    def test_rounds_down_to_grid(self):
        # 6.0s @ 24fps = 144 frames -> 141 (17*8+5)
        self.assertEqual(fixed_slice_frames(144), 141)
        self.assertEqual(fixed_slice_frames(120), 107)
        self.assertEqual(fixed_slice_frames(240), 226)
        self.assertEqual(fixed_slice_frames(141), 141)

    def test_never_exceeds_request(self):
        for frames in range(5, 600):
            self.assertLessEqual(fixed_slice_frames(frames), frames)

    def test_five_frame_floor(self):
        """Below 5 frames there is no valid H3 length; the grid floor wins."""
        self.assertEqual(fixed_slice_frames(1), 5)
        self.assertEqual(fixed_slice_frames(4), 5)

    def test_align_off_keeps_exact_duration(self):
        self.assertEqual(fixed_slice_frames(144, align_to_h3=False), 144)

    def test_zero(self):
        self.assertEqual(fixed_slice_frames(0), 0)


class TestFixedSegments(unittest.TestCase):
    """Range plan for the user's real case: 1962 frames @ 24fps, 6.0s clips."""

    TOTAL = 1962
    SLICE = 141
    MC = 22

    def _plan(self, total=None, slice_frames=None, mc=None, align_to_h3=True):
        return generate_fixed_segments(
            total_frames=self.TOTAL if total is None else total,
            slice_frames=self.SLICE if slice_frames is None else slice_frames,
            context_frames=self.MC if mc is None else mc,
            align_to_h3=align_to_h3,
        )

    def _assert_plan_is_legal(self, plan, slice_frames, total, aligned=True):
        """Shared invariants for every plan, tail included."""
        self.assertTrue(plan)
        for seg in plan[:-1]:
            self.assertLessEqual(seg["extract_frames"], slice_frames)
            if aligned:
                self.assertTrue(is_valid_h3_frame_count(seg["extract_frames"]))
        for prev, seg in zip(plan, plan[1:]):
            # Content is neither duplicated nor skipped: the main ranges of the
            # whole plan tile the video exactly once.
            self.assertEqual(seg["main_start"], prev["main_end"])
        for seg in plan:
            self.assertGreaterEqual(seg["extract_start"], 0)
            self.assertLessEqual(seg["extract_end"], total)
        self.assertEqual(plan[0]["extract_start"], 0)
        self.assertEqual(plan[-1]["extract_end"], total)
        self.assertEqual(sum(seg["main_frames"] for seg in plan), total)

    def test_full_length_segments_are_identical(self):
        """Every segment except the tail is exactly slice_frames long."""
        plan = self._plan()
        for seg in plan[:-1]:
            self.assertEqual(seg["extract_frames"], self.SLICE)

    def test_full_segments_are_valid_h3(self):
        for seg in self._plan()[:-1]:
            self.assertTrue(is_valid_h3_frame_count(seg["extract_frames"]))

    def test_ranges_stay_inside_the_video(self):
        for seg in self._plan():
            self.assertGreaterEqual(seg["extract_start"], 0)
            self.assertLessEqual(seg["extract_end"], self.TOTAL)

    def test_first_segment_has_no_context(self):
        seg = self._plan()[0]
        self.assertEqual(seg["extract_start"], 0)
        self.assertEqual(seg["context_frames"], 0)
        self.assertEqual(seg["main_frames"], self.SLICE)

    def test_context_is_the_previous_tail(self):
        plan = self._plan()
        for prev, seg in zip(plan, plan[1:]):
            self.assertEqual(seg["context_frames"], self.MC)
            self.assertEqual(seg["context_start"], seg["main_start"] - self.MC)
            self.assertEqual(seg["context_end"], seg["main_start"])

    def test_content_reaches_the_end(self):
        plan = self._plan()
        self.assertEqual(plan[-1]["main_end"], self.TOTAL)

    def test_user_case_1962_frames_6s(self):
        """The reported case: 1962f @ 24fps, 6.0s -> 141f clips, never 6.6s/7.3s."""
        slice_frames = fixed_slice_frames(144)
        plan = self._plan(slice_frames=slice_frames)
        self.assertTrue(len(plan) > 10)
        self._assert_plan_is_legal(plan, slice_frames, self.TOTAL)
        for seg in plan[:-1]:
            self.assertEqual(seg["extract_frames"], 141)
            self.assertLessEqual(seg["extract_frames"] / 24, 6.0)

    def test_tail_shortens_instead_of_repeating(self):
        """Old "overlap" repeated 83 frames here; the tail must not repeat any."""
        plan = self._plan()
        tail, prev = plan[-1], plan[-2]
        self.assertEqual(tail["extract_end"], self.TOTAL)
        self.assertEqual(tail["main_start"], prev["main_end"])
        self.assertLess(tail["extract_frames"], self.SLICE)

    def test_user_case_tail_is_58_frames(self):
        """1962f leaves 36 content frames, so the tail is 22 MC + 36 = 58f."""
        plan = self._plan()
        tail = plan[-1]
        self.assertEqual(tail["extract_frames"], 58)
        self.assertEqual(tail["main_frames"], 36)
        self.assertEqual(tail["context_frames"], self.MC)
        self.assertEqual(sum(seg["main_frames"] for seg in plan), self.TOTAL)

    def test_tail_is_deliberately_off_grid(self):
        """The last segment is handed to H3 as-is; only full clips are aligned."""
        tail = self._plan()[-1]
        self.assertFalse(is_valid_h3_frame_count(tail["extract_frames"]))

    def test_nothing_is_lost_or_duplicated(self):
        """Whatever the length, the plan covers every frame exactly once."""
        for total in range(self.SLICE + 1, self.SLICE + 400):
            plan = self._plan(total=total)
            self.assertEqual(sum(seg["main_frames"] for seg in plan), total)
            for prev, seg in zip(plan, plan[1:]):
                self.assertEqual(seg["main_start"], prev["main_end"])

    def test_tail_is_kept_even_when_it_is_tiny(self):
        """265f leaves 5 content frames: 22 MC + 5 = 27f, still its own segment."""
        plan = self._plan(total=265)
        self.assertEqual(len(plan), 3)
        self.assertEqual(plan[-1]["main_frames"], 5)
        self.assertEqual(plan[-1]["extract_frames"], self.MC + 5)
        self.assertEqual(plan[-1]["extract_end"], 265)

    def test_one_frame_tail_is_kept(self):
        """One leftover frame is still one segment - H3 decides what to do."""
        plan = self._plan(total=261)
        self.assertEqual(plan[-1]["main_frames"], 1)
        self.assertEqual(plan[-1]["extract_frames"], self.MC + 1)
        self.assertEqual(plan[-1]["extract_end"], 261)

    def test_tail_never_slides_back(self):
        """The tail starts where the previous content ended, never earlier."""
        plan = generate_fixed_segments(6, 5, 0)
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0]["extract_frames"], 5)
        self.assertEqual(plan[1]["extract_start"], 5)
        self.assertEqual(plan[1]["extract_end"], 6)

    def test_align_off_tail_keeps_every_frame(self):
        """Without the grid there is nothing to round to, so nothing is lost."""
        plan = self._plan(total=265, slice_frames=144, align_to_h3=False)
        self._assert_plan_is_legal(plan, 144, 265, aligned=False)
        self.assertEqual(plan[-1]["main_end"], 265)

    def test_short_video_is_one_segment_with_every_frame(self):
        """A video shorter than one clip is also the tail: no rounding."""
        plan = self._plan(total=100)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["extract_start"], 0)
        self.assertEqual(plan[0]["extract_frames"], 100)

    def test_short_video_align_off_uses_all_frames(self):
        plan = generate_fixed_segments(100, 144, 22, align_to_h3=False)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["extract_frames"], 100)

    def test_empty_video(self):
        self.assertEqual(self._plan(total=0), [])

    def test_context_larger_than_the_slice_is_rejected(self):
        """141f with 139 context frames leaves 2 content frames - refuse, don't drift."""
        with self.assertRaises(ValueError):
            self._plan(mc=139)

    def test_grid_of_durations_and_lengths(self):
        """Sweep durations and video lengths: fixed length, <= request, 17n+5."""
        for duration_frames in (17, 34, 144, 240, 720):
            slice_frames = fixed_slice_frames(duration_frames)
            for mc in (0, 5, 22, 39, 56):
                if slice_frames - mc < 5:
                    continue
                for total in (slice_frames, slice_frames + 1,
                              slice_frames * 3 + 7, 5000):
                    plan = self._plan(total=total, slice_frames=slice_frames, mc=mc)
                    self._assert_plan_is_legal(plan, slice_frames, total)
                    for seg in plan[:-1]:
                        self.assertEqual(seg["extract_frames"], slice_frames)


if __name__ == "__main__":
    unittest.main(verbosity=2)
