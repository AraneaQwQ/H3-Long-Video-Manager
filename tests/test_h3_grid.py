"""H3 Long Video Manager — H3 Frame Grid & Seamless Segmentation Tests."""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.h3_grid import (
    align_down_to_h3_grid,
    align_up_to_h3_grid,
    is_valid_h3_frame_count,
    nearest_valid_range,
    generate_aligned_segments,
    generate_aligned_segments_with_mc,
)


class TestH3Grid(unittest.TestCase):
    """Verify 17n+5 frame alignment logic."""

    def test_known_valid_values(self):
        """These are all valid 17n+5 values."""
        valid = [5, 22, 39, 56, 73, 90, 107, 124, 141, 158, 175, 192, 345, 362]
        for v in valid:
            self.assertTrue(is_valid_h3_frame_count(v), f"{v} should be valid")

    def test_known_invalid_values(self):
        """These are NOT valid 17n+5 values."""
        invalid = [1, 2, 10, 50, 100, 144, 166, 200]
        for v in invalid:
            self.assertFalse(is_valid_h3_frame_count(v), f"{v} should be invalid")

    def test_align_down(self):
        """Align down to nearest valid value."""
        self.assertEqual(align_down_to_h3_grid(5), 5)
        self.assertEqual(align_down_to_h3_grid(22), 22)
        self.assertEqual(align_down_to_h3_grid(39), 39)
        self.assertEqual(align_down_to_h3_grid(56), 56)
        self.assertEqual(align_down_to_h3_grid(144), 141)
        self.assertEqual(align_down_to_h3_grid(166), 158)
        self.assertEqual(align_down_to_h3_grid(10), 5)
        self.assertEqual(align_down_to_h3_grid(100), 90)
        self.assertEqual(align_down_to_h3_grid(120), 107)
        self.assertEqual(align_down_to_h3_grid(365), 362)
        self.assertEqual(align_down_to_h3_grid(240), 226)
        self.assertEqual(align_down_to_h3_grid(254), 243)
        self.assertEqual(align_down_to_h3_grid(0), 0)
        self.assertEqual(align_down_to_h3_grid(3), 5)

    def test_align_down_always_valid(self):
        """Result of align_down is always valid (or 0 for input 0)."""
        for n in range(1, 500):
            result = align_down_to_h3_grid(n)
            if result >= 5:
                self.assertTrue(is_valid_h3_frame_count(result),
                                f"align_down({n}) = {result} is not valid 17n+5")

    def test_align_up(self):
        """Align up to nearest valid value."""
        self.assertEqual(align_up_to_h3_grid(5), 5)
        self.assertEqual(align_up_to_h3_grid(22), 22)
        self.assertEqual(align_up_to_h3_grid(144), 158)
        self.assertEqual(align_up_to_h3_grid(10), 22)
        self.assertEqual(align_up_to_h3_grid(1), 5)

    def test_nearest_valid_range(self):
        """Bracketing range."""
        self.assertEqual(nearest_valid_range(144), (141, 158))
        self.assertEqual(nearest_valid_range(22), (22, 22))
        self.assertEqual(nearest_valid_range(166), (158, 175))


class TestSeamlessSegmentation(unittest.TestCase):
    """Verify the carry-forward seamless segmentation algorithm."""

    def test_basic_contiguity(self):
        """All segments must be contiguous (no gaps)."""
        segs = generate_aligned_segments(1440, 240)
        for i in range(len(segs) - 1):
            self.assertEqual(segs[i][1], segs[i + 1][0],
                             f"Gap between segment {i} and {i+1}: {segs[i]} → {segs[i+1]}")

    def test_all_valid_h3(self):
        """All segment frame counts must be valid 17n+5."""
        segs = generate_aligned_segments(1440, 240)
        for i, (s, e) in enumerate(segs):
            frames = e - s
            self.assertTrue(is_valid_h3_frame_count(frames),
                            f"Segment {i}: {frames} frames is not valid 17n+5")

    def test_no_exceed_total(self):
        """No segment should exceed total frames."""
        total = 1440
        segs = generate_aligned_segments(total, 240)
        for s, e in segs:
            self.assertLessEqual(e, total)
        self.assertGreaterEqual(segs[0][0], 0)

    def test_user_example_60s_10s_segments(self):
        """User's example: 60s @ 24fps = 1440 frames, target 10s = 240 frames.

        Expected: 6 contiguous segments, all 17n+5, only last loses frames.
        """
        segs = generate_aligned_segments(1440, 240)
        
        # Should have 6 segments
        self.assertEqual(len(segs), 6, f"Expected 6 segments, got {len(segs)}: {segs}")
        
        # Verify each is 17n+5
        for i, (s, e) in enumerate(segs):
            frames = e - s
            self.assertTrue(is_valid_h3_frame_count(frames),
                            f"Seg {i}: {frames} not valid 17n+5")
        
        # Verify contiguity
        for i in range(len(segs) - 1):
            self.assertEqual(segs[i][1], segs[i + 1][0])
        
        # Verify total coverage (only last segment may lose frames)
        total_covered = segs[-1][1]
        self.assertLessEqual(total_covered, 1440)
        self.assertGreaterEqual(total_covered, 1440 - 240)  # Lost < one target

        # First segment starts at 0
        self.assertEqual(segs[0][0], 0)

    def test_carry_forward_behavior(self):
        """Verify that lost frames are carried to next segment (not just repeated same size).

        With target=240: align_down(240)=226, so carry=14.
        Next: eff=254, align_down(254)=243.
        This means segments should NOT all be the same size.
        """
        segs = generate_aligned_segments(1440, 240)
        sizes = [e - s for s, e in segs]
        
        # Should have at least 2 different sizes (carry-forward creates variation)
        # unless all happen to align to the same value
        if len(sizes) > 1:
            # The first and second should differ if carry > 0
            first_aligned = align_down_to_h3_grid(240)  # 226
            if first_aligned < 240:
                # Carry exists, so second segment should be larger than first
                # (or at least different from a no-carry algorithm)
                self.assertNotEqual(len(set(sizes)), 1,
                                   "All segments same size — carry-forward not working")

    def test_short_video_single_segment(self):
        """Video shorter than one target → single segment."""
        segs = generate_aligned_segments(100, 240)
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0][0], 0)
        frames = segs[0][1] - segs[0][0]
        self.assertTrue(is_valid_h3_frame_count(frames))
        self.assertLessEqual(segs[0][1], 100)

    def test_very_short_video(self):
        """Very short video (10 frames) → single 5-frame segment."""
        segs = generate_aligned_segments(10, 240)
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0], (0, 5))

    def test_exact_h3_value(self):
        """If target is already 17n+5, no carry needed."""
        # 243 = 17*14+5 is valid
        segs = generate_aligned_segments(1440, 243)
        for i, (s, e) in enumerate(segs):
            frames = e - s
            self.assertTrue(is_valid_h3_frame_count(frames),
                            f"Seg {i}: {frames} not valid 17n+5")
        # Contiguity
        for i in range(len(segs) - 1):
            self.assertEqual(segs[i][1], segs[i + 1][0])

    def test_zero_frames(self):
        segs = generate_aligned_segments(0, 240)
        self.assertEqual(segs, [])

    def test_single_frame(self):
        segs = generate_aligned_segments(1, 240)
        self.assertEqual(len(segs), 1)
        # Should be clamped to minimum valid (5) or the actual frame count
        self.assertLessEqual(segs[0][1], 1)

    def test_many_small_segments(self):
        """Small target creates many segments."""
        total = 1000
        target = 22  # 17*1+5 = 22 (valid)
        segs = generate_aligned_segments(total, target)
        
        # All should be valid
        for i, (s, e) in enumerate(segs):
            frames = e - s
            self.assertTrue(is_valid_h3_frame_count(frames),
                            f"Seg {i}: {frames} not valid 17n+5")
        
        # Contiguous
        for i in range(len(segs) - 1):
            self.assertEqual(segs[i][1], segs[i + 1][0])
        
        # Coverage
        self.assertLessEqual(segs[-1][1], total)

    def test_no_infinite_loop(self):
        """Ensure the algorithm terminates for various inputs."""
        for total in [5, 10, 50, 100, 1000, 1440, 10000]:
            for target in [5, 22, 144, 240, 500]:
                segs = generate_aligned_segments(total, target)
                self.assertGreater(len(segs), 0,
                                   f"No segments for total={total}, target={target}")


class TestAlignedSegmentsWithMC(unittest.TestCase):
    """Test MC-aware segment generation."""

    def test_mc_extends_backward(self):
        """MC context should extend backward into previous segment."""
        results = generate_aligned_segments_with_mc(1440, 240, motion_context_frames=22)
        
        # First segment: MC clamped to 0
        self.assertEqual(results[0]["context_start"], 0)
        self.assertEqual(results[0]["context_frames"], 0)
        
        # Second segment: MC extends into first
        self.assertEqual(results[1]["context_start"], results[1]["main_start"] - 22)
        self.assertEqual(results[1]["context_frames"], 22)

    def test_mc_extract_range(self):
        """Extraction range = context_start to main_end."""
        results = generate_aligned_segments_with_mc(1440, 240, motion_context_frames=22)
        
        for r in results:
            self.assertEqual(r["extract_start"], r["context_start"])
            self.assertEqual(r["extract_end"], r["main_end"])
            self.assertEqual(r["extract_frames"], r["context_frames"] + r["main_frames"])

    def test_mc_zero(self):
        """MC=0 means no context, extract == main."""
        results = generate_aligned_segments_with_mc(1440, 240, motion_context_frames=0)
        
        for r in results:
            self.assertEqual(r["context_frames"], 0)
            self.assertEqual(r["extract_start"], r["main_start"])
            self.assertEqual(r["extract_frames"], r["main_frames"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
