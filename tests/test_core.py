"""H3 Long Video Manager — Core Unit Tests (Updated for Seamless Segmentation).

Verifies:
- Seamless segmentation: contiguous, each 17n+5, carry-forward
- Motion Context: extends backward correctly
- Final segment: no frames beyond source
- Manifest consistency
"""

import sys
import os
import unittest
from fractions import Fraction

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import (
    MotionContextConfig,
    SourceVideoInfo,
    WorkingVideoConfig,
    WorkingVideoInfo,
)
from core.manifest import build_manifest
from core.segmentation import compute_segment_duration_frames
from core.h3_grid import is_valid_h3_frame_count, align_down_to_h3_grid, generate_aligned_segments


# ---------------------------------------------------------------------------
# Helper: Create test source videos
# ---------------------------------------------------------------------------


def make_source(
    width=1920,
    height=1080,
    fps=30,
    duration_seconds=61.42,
) -> SourceVideoInfo:
    """Create a synthetic source video info for testing."""
    frame_count = round(duration_seconds * fps)
    return SourceVideoInfo(
        file_path="test_source.mp4",
        width=width,
        height=height,
        fps=Fraction(fps, 1),
        frame_count=frame_count,
        duration_seconds=duration_seconds,
        codec="h264",
        container="mp4",
        is_cfr=True,
    )


def make_source_exact_frames(
    total_frames_at_24fps: int,
) -> SourceVideoInfo:
    """Create a source that produces EXACTLY total_frames at 24 FPS."""
    duration = total_frames_at_24fps / 24.0
    return SourceVideoInfo(
        file_path="test_exact.mp4",
        width=1920,
        height=1080,
        fps=Fraction(30, 1),
        frame_count=round(duration * 30),
        duration_seconds=duration,
        codec="h264",
        container="mp4",
        is_cfr=True,
    )


# ---------------------------------------------------------------------------
# Segmentation Tests (old generate_segments — still valid for non-H3 mode)
# ---------------------------------------------------------------------------


class TestSegmentation(unittest.TestCase):
    """Basic segmentation (non-H3 aligned) tests."""

    def test_exact_division(self):
        from core.segmentation import generate_segments
        segs = generate_segments(1440, 144)
        self.assertEqual(len(segs), 10)
        self.assertEqual(segs[0], (0, 144))
        self.assertEqual(segs[9], (1296, 1440))

    def test_segment_duration_calc(self):
        self.assertEqual(compute_segment_duration_frames(6.0, 24), 144)
        self.assertEqual(compute_segment_duration_frames(5.0, 24), 120)
        self.assertEqual(compute_segment_duration_frames(10.0, 24), 240)

    def test_invalid_duration(self):
        with self.assertRaises(ValueError):
            compute_segment_duration_frames(0, 24)


# ---------------------------------------------------------------------------
# Motion Context Tests
# ---------------------------------------------------------------------------


class TestMotionContext(unittest.TestCase):
    """Motion Context range calculation."""

    def test_context_start_middle_segment(self):
        mc = MotionContextConfig(context_frames=22)
        self.assertEqual(mc.context_start(288), 266)
        self.assertEqual(mc.context_end(288), 288)

    def test_context_start_first_segment(self):
        mc = MotionContextConfig(context_frames=22)
        self.assertEqual(mc.context_start(0), 0)
        self.assertEqual(mc.context_end(0), 0)

    def test_all_valid_mc_values(self):
        # RAFOLIE 2026-09-28: zero disables context in the current upstream model.
        for v in (0, 5, 22, 39, 56):
            mc = MotionContextConfig(context_frames=v)
            self.assertEqual(mc.context_frames, v)

    def test_invalid_mc_value(self):
        for v in (10, 100, -5):
            with self.assertRaises(ValueError):
                MotionContextConfig(context_frames=v)


# ---------------------------------------------------------------------------
# Manifest Tests (NEW: Seamless Segmentation)
# ---------------------------------------------------------------------------


class TestManifestSeamless(unittest.TestCase):
    """Manifest with fixed-length H3-aligned segmentation."""

    def _build_manifest(self, total_frames_24fps: int, mc: int = 22, seg_dur: float = 6.0):
        source = make_source_exact_frames(total_frames_24fps)
        config = WorkingVideoConfig(target_fps=24)
        manifest = build_manifest(
            source=source,
            working_config=config,
            segment_duration_seconds=seg_dur,
            motion_context=MotionContextConfig(context_frames=mc),
            align_to_h3=True,
        )
        return manifest

    def test_main_segments_contiguous(self):
        """CRITICAL: content is contiguous - no gap, no repeat, nothing lost."""
        manifest = self._build_manifest(total_frames_24fps=1440, mc=22, seg_dur=6.0)
        segs = manifest.segments
        total = manifest.working_info.total_frames

        self.assertEqual(segs[0].main_start_frame, 0)
        for i in range(len(segs) - 1):
            self.assertEqual(
                segs[i + 1].main_start_frame, segs[i].main_end_frame,
                f"Gap or repeated content between segment {i} and {i+1}"
            )
        self.assertEqual(segs[-1].main_end_frame, total)
        self.assertEqual(sum(s.main_frame_count for s in segs), total)

    def test_segments_fixed_length(self):
        """CRITICAL: the full-length segments are identical and <= the request.

        The tail takes whatever is left and is deliberately NOT rounded to
        17n+5 - that odd length is handed to H3 as-is.
        """
        manifest = self._build_manifest(total_frames_24fps=1440, mc=22, seg_dur=6.0)
        requested = compute_segment_duration_frames(6.0, 24)  # 144
        segs = manifest.segments
        for seg in segs[:-1]:
            self.assertEqual(seg.extraction_frame_count, 141)  # 144 -> 17n+5
            self.assertTrue(is_valid_h3_frame_count(seg.extraction_frame_count))
        for seg in segs:
            self.assertLessEqual(seg.extraction_frame_count, requested)

        tail = segs[-1]
        self.assertEqual(tail.context_length, 22)
        self.assertEqual(tail.main_frame_count, 109)
        self.assertEqual(tail.extraction_frame_count, 131)
        self.assertLess(tail.extraction_frame_count, 141)
        self.assertFalse(is_valid_h3_frame_count(tail.extraction_frame_count))

    def test_no_frames_beyond_source(self):
        """No segment should exceed total frames."""
        manifest = self._build_manifest(total_frames_24fps=1000, mc=22)
        total = manifest.working_info.total_frames
        
        for seg in manifest.segments:
            self.assertLessEqual(seg.main_end_frame, total)
            self.assertLessEqual(seg.extraction_end_frame, total)

    def test_first_segment_starts_at_zero(self):
        manifest = self._build_manifest(total_frames_24fps=1440, mc=22)
        self.assertEqual(manifest.segments[0].main_start_frame, 0)

    def test_first_segment_mc_clamped(self):
        """First segment: MC clamped to 0 (no negative frames)."""
        manifest = self._build_manifest(total_frames_24fps=1440, mc=22)
        seg0 = manifest.segments[0]
        self.assertEqual(seg0.context_start_frame, 0)
        self.assertEqual(seg0.context_end_frame, 0)
        self.assertEqual(seg0.context_length, 0)
        self.assertEqual(seg0.extraction_start_frame, 0)

    def test_middle_segment_mc_extends_backward(self):
        """Middle segments: MC extends into previous segment."""
        manifest = self._build_manifest(total_frames_24fps=1440, mc=22)
        
        # Segment 1 (index 1) should have MC extending backward
        seg1 = manifest.segments[1]
        self.assertEqual(seg1.context_start_frame, seg1.main_start_frame - 22)
        self.assertEqual(seg1.context_end_frame, seg1.main_start_frame)
        self.assertEqual(seg1.context_length, 22)
        self.assertEqual(seg1.extraction_start_frame, seg1.main_start_frame - 22)
        self.assertEqual(seg1.extraction_end_frame, seg1.main_end_frame)

    def test_extraction_range_correct(self):
        """Extraction = [main_start - MC, main_end)."""
        manifest = self._build_manifest(total_frames_24fps=1440, mc=22)
        
        for seg in manifest.segments:
            expected_extract_start = max(0, seg.main_start_frame - 22)
            self.assertEqual(seg.extraction_start_frame, expected_extract_start)
            self.assertEqual(seg.extraction_end_frame, seg.main_end_frame)

    def test_segment_count_reasonable(self):
        """1440 frames / 144 target → should give ~10 segments."""
        manifest = self._build_manifest(total_frames_24fps=1440, mc=22, seg_dur=6.0)
        count = len(manifest.segments)
        self.assertGreaterEqual(count, 8)
        self.assertLessEqual(count, 12)

    def test_all_mc_values(self):
        """Every MC option keeps the same fixed physical length."""
        for mc_value in (0, 5, 22, 39, 56):
            manifest = self._build_manifest(total_frames_24fps=1440, mc=mc_value)
            segs = manifest.segments
            for seg in segs[:-1]:
                self.assertEqual(seg.extraction_frame_count, 141,
                                 f"MC={mc_value}, seg {seg.segment_id}: length differs")
            for seg in segs:
                self.assertLessEqual(seg.context_length, mc_value)
            # Content is contiguous and complete whatever MC is used.
            total = manifest.working_info.total_frames
            for i in range(len(segs) - 1):
                self.assertEqual(
                    segs[i + 1].main_start_frame, segs[i].main_end_frame,
                    f"MC={mc_value}: gap or overlap at segment {i}")
            self.assertEqual(segs[-1].main_end_frame, total, f"MC={mc_value}: frames lost")
            self.assertEqual(sum(s.main_frame_count for s in segs), total,
                             f"MC={mc_value}: frames lost or duplicated")

    def test_slice_frames_identical_across_mc_values(self):
        """The physical length never depends on MC; MC is taken out of it.
        
        A bigger MC means less new content per segment, not a longer file —
        that is what keeps every clip at the duration the user asked for.
        """
        for mc in (0, 5, 22, 39, 56):
            manifest = self._build_manifest(total_frames_24fps=1440, mc=mc)
            self.assertEqual(manifest.slice_frames, 141, f"MC={mc}: slice changed")
            lengths = [s.extraction_frame_count for s in manifest.segments[:-1]]
            self.assertEqual(set(lengths), {141}, f"MC={mc}: a segment differs")

    def test_short_video(self):
        """Video shorter than one clip → one segment holding every frame."""
        manifest = self._build_manifest(total_frames_24fps=100, mc=22)
        self.assertEqual(len(manifest.segments), 1)
        seg = manifest.segments[0]
        self.assertEqual(seg.main_start_frame, 0)
        self.assertEqual(seg.main_end_frame, 100)
        self.assertEqual(seg.extraction_frame_count, 100)

    def test_align_to_h3_false(self):
        """align_to_h3=False keeps the exact duration, but still equal length."""
        source = make_source_exact_frames(1440)
        config = WorkingVideoConfig(target_fps=24)
        manifest = build_manifest(
            source=source,
            working_config=config,
            segment_duration_seconds=6.0,
            motion_context=MotionContextConfig(context_frames=22),
            align_to_h3=False,
        )
        self.assertEqual(manifest.slice_frames, 144)
        for seg in manifest.segments[:-1]:
            self.assertEqual(seg.extraction_frame_count, 144)
        # No grid rounding means nothing is left over: the tail is exact.
        self.assertEqual(manifest.segments[-1].main_end_frame, 1440)
        for i in range(len(manifest.segments) - 1):
            self.assertEqual(manifest.segments[i + 1].main_start_frame,
                             manifest.segments[i].main_end_frame)

    def test_working_fps_is_24(self):
        manifest = self._build_manifest(total_frames_24fps=1440)
        self.assertEqual(manifest.working_info.fps, 24)

    def test_resolution_preservation(self):
        source = make_source_exact_frames(1440)
        config = WorkingVideoConfig(target_fps=24, scale_percent=50.0)
        manifest = build_manifest(
            source=source,
            working_config=config,
            segment_duration_seconds=6.0,
            motion_context=MotionContextConfig(context_frames=22),
        )
        self.assertEqual(manifest.working_info.width, 960)
        self.assertEqual(manifest.working_info.height, 540)


# ---------------------------------------------------------------------------
# WorkingVideoInfo Tests
# ---------------------------------------------------------------------------


class TestWorkingVideoInfo(unittest.TestCase):
    """Phase 3: Working video conform tests."""

    def test_fps_conform(self):
        source = make_source_exact_frames(1440)
        config = WorkingVideoConfig(target_fps=24)
        info = WorkingVideoInfo.from_source(source, config)
        self.assertEqual(info.fps, 24)

    def test_frame_count_scaling(self):
        source = make_source(width=1920, height=1080, fps=30, duration_seconds=61.4)
        config = WorkingVideoConfig(target_fps=24)
        info = WorkingVideoInfo.from_source(source, config)
        self.assertEqual(info.total_frames, round(61.4 * 24))

    def test_scale_percent(self):
        source = make_source(width=3840, height=2160)
        config = WorkingVideoConfig(target_fps=24, scale_percent=50.0)
        w, h = config.compute_working_dimensions(3840, 2160)
        self.assertEqual(w, 1920)
        self.assertEqual(h, 1080)


if __name__ == "__main__":
    unittest.main(verbosity=2)
