"""H3 Long Video Manager - Smart Split core tests (no ComfyUI needed).

The rules under test are the four invariants of the planning doc (section 7):
no dropped frames, no duplicated main frames, no padding, and no 17n+5
alignment. Motion Context may widen the extraction range but must never move a
main boundary.
"""

import os
import unittest

from core.models import MOTION_CONTEXT_OPTIONS
from core.smart_split import (
    DETECT_MAX_SIDE,
    analysis_size,
    assert_lossless,
    build_smart_segments,
    detect_scene_cuts,
    normalize_boundaries,
    scenedetect_available,
    scenedetect_install_hint,
)

try:
    import numpy as np
except ImportError:  # pragma: no cover - the detector tests skip instead
    np = None

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ranges(segments):
    return [(seg["main_start"], seg["main_end"]) for seg in segments]


def extracts(segments):
    return [(seg["extract_start"], seg["extract_end"]) for seg in segments]


class TestNormalizeBoundaries(unittest.TestCase):
    """Planning doc sections 43-46: sort, dedupe, clamp, always keep 0 and end."""

    def test_no_cuts_is_one_segment(self):
        self.assertEqual(normalize_boundaries([], 1000), [0, 1000])
        self.assertEqual(normalize_boundaries(None, 1000), [0, 1000])

    def test_sorted_and_deduplicated(self):
        self.assertEqual(normalize_boundaries([300, 100, 100, 0, 1000], 1000), [0, 100, 300, 1000])

    def test_out_of_range_is_dropped(self):
        self.assertEqual(normalize_boundaries([-10, 100, 1200], 1000), [0, 100, 1000])

    def test_non_integer_is_dropped(self):
        self.assertEqual(normalize_boundaries(["x", None, 50.0], 100), [0, 50, 100])

    def test_empty_timeline(self):
        self.assertEqual(normalize_boundaries([10], 0), [])


class TestSmartSegments(unittest.TestCase):
    """Planning doc sections 6, 7, 9, 13, 18, 47, 48, 49, 64-68."""

    def test_no_cuts_covers_whole_video(self):
        # Core Unit Test 1
        self.assertEqual(ranges(build_smart_segments(1000, [])), [(0, 1000)])

    def test_cuts_become_exact_ranges(self):
        # Core Unit Test 2
        self.assertEqual(
            ranges(build_smart_segments(1000, [100, 300, 700])),
            [(0, 100), (100, 300), (300, 700), (700, 1000)],
        )

    def test_duplicate_bounds_collapse(self):
        # Core Unit Test 3
        self.assertEqual(
            ranges(build_smart_segments(1000, [0, 100, 100, 300, 1000])),
            [(0, 100), (100, 300), (300, 1000)],
        )

    def test_illegal_bounds_are_safe(self):
        # Core Unit Test 4
        segments = build_smart_segments(1000, [-10, 100, 1200])
        self.assertEqual(ranges(segments), [(0, 100), (100, 1000)])
        assert_lossless(segments, 1000)

    def test_no_gaps_no_overlaps_full_coverage(self):
        # Core Unit Test 5
        for cuts in ([], [1], [100, 300, 700], [999], [1, 2, 3, 999]):
            segments = build_smart_segments(1000, cuts)
            assert_lossless(segments, 1000)

    def test_worked_example_from_the_doc(self):
        # Planning doc sections 49 and 98: real cuts, no grid snapping.
        segments = build_smart_segments(1000, [87, 321, 400, 812])
        self.assertEqual(
            ranges(segments),
            [(0, 87), (87, 321), (321, 400), (400, 812), (812, 1000)],
        )
        self.assertEqual([s["main_frames"] for s in segments], [87, 234, 79, 412, 188])
        assert_lossless(segments, 1000)

    def test_lengths_are_never_rounded(self):
        """Off-grid lengths stay off-grid: 5, 18, 127 and 301 frames are all legal."""
        for length in (5, 18, 127, 301):
            segments = build_smart_segments(length, [])
            self.assertEqual(ranges(segments), [(0, length)])

    def test_short_scenes_are_not_merged(self):
        segments = build_smart_segments(100, [3, 7, 11])
        self.assertEqual(ranges(segments), [(0, 3), (3, 7), (7, 11), (11, 100)])

    def test_long_scenes_are_not_split(self):
        segments = build_smart_segments(10_000, [])
        self.assertEqual(len(segments), 1)

    def test_ids_are_sequential_from_zero(self):
        segments = build_smart_segments(1000, [100, 400])
        self.assertEqual([s["segment_id"] for s in segments], [0, 1, 2])
        self.assertEqual([s["scene_id"] for s in segments], [0, 1, 2])

    def test_empty_timeline_has_no_segments(self):
        self.assertEqual(build_smart_segments(0, [5]), [])

    def test_negative_context_is_rejected(self):
        with self.assertRaises(ValueError):
            build_smart_segments(100, [50], motion_context_frames=-1)


class TestNoH3GridDependency(unittest.TestCase):
    """Core Unit Test 6: the smart path must not touch the 17n+5 grid at all."""

    def test_module_does_not_import_h3_grid(self):
        with open(os.path.join(REPO, "core", "smart_split.py"), encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("h3_grid", source.replace("core/h3_grid.py", "").replace("core.h3_grid", ""))
        self.assertNotIn("align_to_h3", source)
        self.assertNotIn("17n + 5", source.replace("17n+5", ""))

    def test_off_grid_lengths_survive_a_full_round_trip(self):
        segments = build_smart_segments(1000, [87, 321, 400, 812])
        for seg in segments:
            self.assertNotEqual((seg["main_frames"] - 5) % 17, 0)


class TestMotionContext(unittest.TestCase):
    """Planning doc sections 11, 50, 51, 52, 70, 71, 77."""

    CUTS = [100, 300, 700]

    def test_context_never_moves_a_main_boundary(self):
        base = build_smart_segments(1000, self.CUTS, 0)
        for mc in MOTION_CONTEXT_OPTIONS:
            segments = build_smart_segments(1000, self.CUTS, mc)
            self.assertEqual(ranges(segments), ranges(base))
            self.assertEqual(
                [s["main_frames"] for s in segments],
                [s["main_frames"] for s in base],
            )

    def test_first_segment_has_no_context(self):
        for mc in MOTION_CONTEXT_OPTIONS:
            first = build_smart_segments(1000, self.CUTS, mc)[0]
            self.assertEqual(first["context_frames"], 0)
            self.assertEqual(first["context_start"], 0)
            self.assertEqual(first["extract_start"], 0)
            self.assertEqual(first["extract_end"], first["main_end"])

    def test_context_is_taken_from_the_previous_shot(self):
        segments = build_smart_segments(1000, self.CUTS, 22)
        for segment in segments[1:]:
            self.assertEqual(segment["context_end"], segment["main_start"])
            self.assertEqual(segment["context_frames"], 22)
            self.assertEqual(segment["context_start"], segment["main_start"] - 22)
            self.assertEqual(segment["extract_start"], segment["context_start"])
            self.assertEqual(segment["extract_frames"], segment["main_frames"] + 22)

    def test_context_is_clamped_at_frame_zero(self):
        # A cut at frame 20 cannot reach back 56 frames.
        segments = build_smart_segments(1000, [20], 56)
        self.assertEqual(segments[1]["context_start"], 0)
        self.assertEqual(segments[1]["context_frames"], 20)
        self.assertEqual(segments[1]["extract_start"], 0)

    def test_every_menu_option_round_trips(self):
        for mc in MOTION_CONTEXT_OPTIONS:
            segments = build_smart_segments(1000, self.CUTS, mc)
            assert_lossless(segments, 1000)
            for segment in segments:
                self.assertEqual(
                    segment["extract_frames"],
                    segment["main_frames"] + segment["context_frames"],
                )
                self.assertLessEqual(segment["extract_start"], segment["main_start"])
                self.assertGreaterEqual(segment["extract_start"], 0)

    def test_only_the_menu_options_are_accepted(self):
        for bad in (-1, 1, 21, 23, 100):
            with self.assertRaises(ValueError):
                build_smart_segments(1000, [500], bad)


class TestLosslessCoverage(unittest.TestCase):
    """Planning doc sections 7, 8, 76: the main ranges must tile the timeline."""

    TOTAL = 1000
    CUTS = [87, 321, 400, 812]

    def test_main_ranges_tile_the_timeline(self):
        for cuts in ([], self.CUTS, [1], [999], [1, 2, 3]):
            segments = build_smart_segments(self.TOTAL, cuts)
            assert_lossless(segments, self.TOTAL)
            self.assertEqual(segments[0]["main_start"], 0)
            self.assertEqual(segments[-1]["main_end"], self.TOTAL)
            self.assertEqual(sum(s["main_frames"] for s in segments), self.TOTAL)

    def test_joining_main_slices_rebuilds_the_source(self):
        source = list(range(self.TOTAL))
        segments = build_smart_segments(self.TOTAL, self.CUTS, 22)
        joined = []
        for segment in segments:
            joined.extend(source[segment["main_start"] : segment["main_end"]])
        self.assertEqual(joined, source)

    def test_no_main_frame_is_duplicated(self):
        segments = build_smart_segments(self.TOTAL, self.CUTS, 56)
        seen = []
        for segment in segments:
            seen.extend(range(segment["main_start"], segment["main_end"]))
        self.assertEqual(len(seen), len(set(seen)))

    def test_context_overlap_is_the_only_overlap(self):
        segments = build_smart_segments(self.TOTAL, self.CUTS, 22)
        for previous, current in zip(segments, segments[1:]):
            self.assertEqual(
                previous["extract_end"] - current["extract_start"],
                current["context_frames"],
            )

    def test_guard_rejects_a_broken_plan(self):
        broken = build_smart_segments(1000, [500])
        broken[0]["main_end"] = 480
        with self.assertRaises(ValueError):
            assert_lossless(broken, 1000)


class TestAnalysisSize(unittest.TestCase):
    """Detection is cheaper on a small copy; frame indices never change."""

    def test_small_frames_are_untouched(self):
        self.assertEqual(analysis_size(256, 144), (256, 144))
        self.assertEqual(analysis_size(64, 64), (64, 64))

    def test_long_side_is_capped(self):
        width, height = analysis_size(1920, 1080)
        self.assertEqual(width, DETECT_MAX_SIDE)
        self.assertEqual(height, round(1080 * DETECT_MAX_SIDE / 1920))

    def test_portrait_is_capped_the_same_way(self):
        width, height = analysis_size(1080, 1920)
        self.assertEqual(height, DETECT_MAX_SIDE)
        self.assertLess(width, height)

    def test_aspect_ratio_is_preserved(self):
        for width, height in ((1920, 1080), (1080, 1920), (3840, 2160), (720, 1280)):
            target_w, target_h = analysis_size(width, height)
            self.assertLessEqual(max(target_w, target_h), DETECT_MAX_SIDE)
            self.assertGreaterEqual(target_w, 2)
            self.assertGreaterEqual(target_h, 2)
            self.assertAlmostEqual((target_w / target_h) / (width / height), 1.0, places=2)


def _clip(cuts, total=120, height=90, width=160, dtype="uint8"):
    """Synthetic hard-cut clip: every shot is a flat colour block."""
    bounds = [0] + list(cuts) + [total]
    frames = np.zeros((total, height, width, 3), dtype=np.uint8)
    for index in range(len(bounds) - 1):
        frames[bounds[index] : bounds[index + 1]] = np.uint8(20 + 60 * index)
    if dtype == "float":
        return (frames.astype(np.float32)) / 255.0
    return frames


@unittest.skipUnless(
    scenedetect_available() and np is not None,
    "PySceneDetect/numpy are not installed in this Python",
)
class TestDetector(unittest.TestCase):
    """The detector runs on the node's own timeline, so cuts are output frame indices."""

    def test_hard_cut_becomes_a_segment_boundary(self):
        cuts, meta = detect_scene_cuts(_clip([60]), 120, 24.0, "medium")
        self.assertEqual(cuts, [60])
        segments = build_smart_segments(120, cuts)
        self.assertEqual(ranges(segments), [(0, 60), (60, 120)])
        assert_lossless(segments, 120)
        self.assertEqual(meta["cut_count"], 1)
        self.assertEqual(meta["scene_count"], 2)

    def test_static_video_is_one_segment(self):
        cuts, meta = detect_scene_cuts(_clip([]), 120, 24.0, "high")
        self.assertEqual(cuts, [])
        self.assertEqual(ranges(build_smart_segments(120, cuts)), [(0, 120)])
        self.assertEqual(meta["scene_count"], 1)

    def test_multiple_shots(self):
        cuts, _ = detect_scene_cuts(_clip([30, 70]), 120, 24.0, "high")
        self.assertEqual(cuts, [30, 70])
        segments = build_smart_segments(120, cuts, 22)
        self.assertEqual(ranges(segments), [(0, 30), (30, 70), (70, 120)])
        assert_lossless(segments, 120)

    def test_float_frames_are_accepted(self):
        cuts, _ = detect_scene_cuts(_clip([60], dtype="float"), 120, 24.0, "medium")
        self.assertEqual(cuts, [60])

    def test_large_frames_are_analysed_downscaled(self):
        _, meta = detect_scene_cuts(_clip([60], height=360, width=640), 120, 24.0, "medium")
        self.assertEqual(meta["analysis_size"], "256x144")

    def test_sensitivity_maps_to_the_threshold(self):
        for name, threshold in (("low", 4.5), ("medium", 3.0), ("high", 2.0)):
            _, meta = detect_scene_cuts(_clip([]), 60, 24.0, name)
            self.assertEqual(meta["adaptive_threshold"], threshold)
        _, meta = detect_scene_cuts(_clip([]), 60, 24.0, "not-a-option")
        self.assertEqual(meta["adaptive_threshold"], 3.0)

    def test_empty_timeline_never_reaches_the_detector(self):
        cuts, meta = detect_scene_cuts(_clip([]), 0, 24.0, "medium")
        self.assertEqual(cuts, [])
        self.assertEqual(meta["scene_count"], 0)


class TestDependencyHint(unittest.TestCase):
    """Planning doc section 96: a missing dependency must explain how to install it."""

    def test_hint_names_the_requirement(self):
        hint = scenedetect_install_hint()
        self.assertIn("pip install", hint)
        self.assertIn("scenedetect", hint)

    def test_available_probe_matches_an_import(self):
        try:
            import scenedetect  # noqa: F401

            self.assertTrue(scenedetect_available())
        except ImportError:
            self.assertFalse(scenedetect_available())


if __name__ == "__main__":
    unittest.main()