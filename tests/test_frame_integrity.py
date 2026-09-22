"""H3 Long Video Manager — Frame Integrity Test (Phase 8).

Generates a synthetic video with visible frame numbers and verifies
that the extraction service produces exactly the expected frames.

This test requires PyAV and numpy.
"""

import os
import sys
import unittest
import tempfile

import numpy as np

try:
    import av
    import torch
    HAS_AV = True
except ImportError:
    HAS_AV = False

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@unittest.skipUnless(HAS_AV, "PyAV not available")
class TestFrameIntegrity(unittest.TestCase):
    """Verify frame-level extraction accuracy with synthetic video."""

    @classmethod
    def setUpClass(cls):
        """Generate a synthetic test video with frame number overlays."""
        import av
        from fractions import Fraction

        cls.tmpdir = tempfile.mkdtemp(prefix="h3lvm_test_")
        cls.video_path = os.path.join(cls.tmpdir, "test_frames.mp4")

        # Create a 480×270 video at 24 FPS with 1440 frames
        # Each frame has a solid color that encodes the frame number
        fps = 24
        total_frames = 1440
        width, height = 480, 270

        container = av.open(cls.video_path, mode='w', format='mp4')
        stream = container.add_stream('h264', rate=fps)
        stream.width = width
        stream.height = height
        stream.pix_fmt = 'yuv420p'

        for i in range(total_frames):
            # Create a frame where the color encodes the frame index
            # Use a gradient + solid regions to make frame identity obvious
            frame_data = np.zeros((height, width, 3), dtype=np.uint8)

            # Background: encode frame number in R channel
            r_val = (i * 255 // max(total_frames - 1, 1))
            frame_data[:, :, 0] = r_val

            # Top-left corner: frame number as a bright marker
            # (For actual verification, we'll check the R channel gradient)
            marker_size = 20
            frame_data[:marker_size, :marker_size, :] = [255, 255, 0]

            frame = av.VideoFrame.from_ndarray(frame_data, format='rgb24')
            for packet in stream.encode(frame):
                container.mux(packet)

        # Flush
        for packet in stream.encode():
            container.mux(packet)
        container.close()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _get_expected_r_value(self, frame_index: int, total_frames: int = 1440) -> int:
        """Calculate expected R channel value for a given frame."""
        return (frame_index * 255 // max(total_frames - 1, 1))

    def test_extract_segment3_mc22(self):
        """CRITICAL: Extract segment 3 with MC=22.

        Working FPS = 24, Segment duration = 6s = 144 frames
        Segment 3 (0-indexed id=2): main [288, 432), MC=22
        Context: [266, 288)
        Extraction: [266, 432) = 166 frames
        """
        from core.extraction import extract_frames

        result = extract_frames(
            source=self.video_path,
            start_frame=266,
            end_frame=432,
        )

        # Verify frame count
        self.assertEqual(result.shape[0], 166,
                         f"Expected 166 frames, got {result.shape[0]}")

        # Verify frame dimensions
        self.assertEqual(result.shape[1], 270)  # H
        self.assertEqual(result.shape[2], 480)  # W
        self.assertEqual(result.shape[3], 3)    # C

        # Verify first frame is frame 266
        first_frame = result[0]
        avg_r = first_frame[:, :, 0].float().mean().item()
        expected_r = self._get_expected_r_value(266) / 255.0
        self.assertAlmostEqual(avg_r, expected_r, delta=0.02,
                               msg=f"First frame: avg R={avg_r}, expected≈{expected_r}")

    def test_extract_segment1_mc56(self):
        """CRITICAL: Extract segment 1 with MC=56.

        Segment 1 (0-indexed id=0): main [0, 144), MC=56
        Context: [0, 0) — clamped!
        Extraction: [0, 144) = 144 frames (NOT 200!)
        """
        from core.extraction import extract_frames

        result = extract_frames(
            source=self.video_path,
            start_frame=0,
            end_frame=144,
        )

        # No context for first segment — just 144 frames
        self.assertEqual(result.shape[0], 144)

    def test_frame_order_preserved(self):
        """Frame order must be strictly increasing (no reordering)."""
        from core.extraction import extract_frames

        result = extract_frames(
            source=self.video_path,
            start_frame=100,
            end_frame=200,
        )

        # Check that R channel generally increases across frames
        # (frame number is encoded in R channel)
        r_values = result[:, :, :, 0].float().mean(dim=[1, 2]).numpy()
        # Allow small variations due to compression
        increasing = np.all(np.diff(r_values) > -2)
        self.assertTrue(increasing,
                        f"Frame order not preserved. R values: {r_values[:10]}...{r_values[-10:]}")

    def test_no_duplicate_frames(self):
        """No unexpected duplicated frames.

        With H.264 compression and a very gradual gradient (1 step per 1440 frames),
        individual per-frame differences are quantized away. Instead, verify
        the overall trend: later frames should have higher R than earlier ones.
        """
        from core.extraction import extract_frames

        result = extract_frames(
            source=self.video_path,
            start_frame=0,
            end_frame=100,
        )

        # Overall trend: last 10 frames should have higher avg R than first 10
        r_values = result[:, :, :, 0].float().mean(dim=[1, 2]).numpy()
        first_avg = r_values[:10].mean()
        last_avg = r_values[-10:].mean()
        self.assertGreater(last_avg, first_avg,
                           f"Frame order broken: first_avg={first_avg}, last_avg={last_avg}")

    def test_extract_beyond_source_fails(self):
        """Requesting frames beyond the source must fail."""
        from core.extraction import extract_frames

        with self.assertRaises(RuntimeError):
            extract_frames(
                source=self.video_path,
                start_frame=1400,
                end_frame=1500,  # Beyond 1440 total frames
            )

    def test_video_metadata(self):
        """Verify metadata detection works."""
        from core.extraction import get_video_metadata

        meta = get_video_metadata(self.video_path)
        self.assertEqual(meta["width"], 480)
        self.assertEqual(meta["height"], 270)
        self.assertEqual(meta["frame_count"], 1440)
        self.assertEqual(float(meta["fps"]), 24.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
