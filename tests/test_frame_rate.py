"""Source-fps inputs become a real 24 fps timeline before either producer cuts."""

import unittest
from unittest import mock

import torch

from core.frame_rate import converted_frame_count, resample_video
from tests.test_node_schema import NODES


class TestFrameRateConversion(unittest.TestCase):
    def test_60fps_keeps_wall_clock_time_and_uses_nearest_frames(self):
        video = torch.arange(120, dtype=torch.float32).reshape(120, 1, 1, 1).expand(120, 2, 2, 3)
        converted = resample_video(video, 60)
        self.assertEqual(converted.shape, (48, 2, 2, 3))
        self.assertEqual(converted_frame_count(120, 60), 48)
        self.assertEqual(converted[:6, 0, 0, 0].tolist(), [0, 3, 5, 8, 10, 13])
        self.assertEqual(converted[-1, 0, 0, 0].item(), 118)

    def test_12fps_repeats_frames_instead_of_playing_twice_as_fast(self):
        video = torch.arange(24).reshape(24, 1, 1, 1).expand(24, 2, 2, 3)
        converted = resample_video(video, 12)
        self.assertEqual(converted.shape[0], 48)
        self.assertEqual(converted[:6, 0, 0, 0].tolist(), [0, 1, 1, 2, 2, 3])

    def test_24fps_is_a_zero_copy_passthrough(self):
        video = torch.zeros(24, 2, 2, 3)
        self.assertIs(resample_video(video, 24), video)


class TestNodeFrameRateContract(unittest.TestCase):
    def test_manager_turns_one_second_at_60fps_into_one_second_at_24fps(self):
        audio = {"waveform": torch.zeros(1, 1, 60000), "sample_rate": 60000}
        output = NODES.H3LongVideoManager.execute(
            video=torch.zeros(60, 2, 2, 3), fps=60, segment_duration=1.0,
            motion_context_frames="0", segment_id=1, audio=audio,
            align_to_h3_grid=False, save_enabled=False,
        ).args
        self.assertEqual(output[0].shape[0], 24)
        self.assertEqual(output[1]["waveform"].shape[-1], 60000)
        self.assertEqual(output[2:], (24, 1))

    def test_smart_split_detects_and_cuts_the_converted_timeline(self):
        audio = {"waveform": torch.zeros(1, 1, 48000), "sample_rate": 24000}
        detected = {
            "method": "mock", "sensitivity": "medium", "adaptive_threshold": 3.0,
            "analysis_size": "2x2", "cut_count": 1, "scene_count": 2,
        }
        with mock.patch.object(NODES, "detect_scene_cuts", return_value=([24], detected)) as detect:
            output = NODES.H3SmartSplit.execute(
                video=torch.zeros(120, 2, 2, 3), fps=60, detection_sensitivity="medium",
                motion_context_frames="0", segment_id=1, audio=audio, save_enabled=False,
            ).args
        self.assertEqual(detect.call_args.args[0].shape[0], 48)
        self.assertEqual(detect.call_args.args[1:3], (48, 24))
        self.assertEqual(output[0].shape[0], 24)
        self.assertEqual(output[1]["waveform"].shape[-1], 24000)
        self.assertEqual(output[2:], (24, 2))


if __name__ == "__main__":
    unittest.main()
