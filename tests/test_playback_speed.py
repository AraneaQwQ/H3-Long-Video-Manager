"""Playback-speed slowdown: widget parsing, frame math, and the node contract.

The slowdown runs BEFORE segmentation, so everything downstream - the segment
table, the 22-frame Motion Context overlap, the tail - is asserted against the
slowed timeline. 1.0x must be indistinguishable from the old behaviour.
"""

import os
import sys
import unittest
from unittest import mock

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

import torch

from core.frame_rate import (
    PLAYBACK_SPEED_OPTIONS,
    iter_slowed_frames,
    parse_playback_speed,
    slowdown_frame_count,
    slowdown_video,
)
from tests.test_node_schema import NODES


def _identity_video(frames: int) -> torch.Tensor:
    """A video whose only varying pixel says which source frame it came from."""
    return torch.arange(frames, dtype=torch.float32).reshape(frames, 1, 1, 1).expand(frames, 2, 2, 3)


class TestParsePlaybackSpeed(unittest.TestCase):
    def test_presets_keep_their_exact_values(self):
        self.assertEqual(parse_playback_speed("1.0x"), 1.0)
        self.assertEqual(parse_playback_speed("0.75x"), 0.75)  # two decimals stay
        self.assertEqual(parse_playback_speed("0.5x"), 0.5)

    def test_options_list_matches_the_widgets(self):
        self.assertEqual(list(PLAYBACK_SPEED_OPTIONS), ["1.0x", "0.75x", "0.5x", "custom"])

    def test_custom_rounds_to_one_decimal(self):
        self.assertEqual(parse_playback_speed("custom", 0.6), 0.6)
        self.assertEqual(parse_playback_speed("custom", 0.62), 0.6)
        self.assertEqual(parse_playback_speed("custom", 0.9), 0.9)

    def test_custom_must_be_inside_the_range(self):
        for bad in (0.0, -0.5, 1.05):
            with self.assertRaises(ValueError):
                parse_playback_speed("custom", bad)

    def test_custom_must_be_a_number(self):
        with self.assertRaises(ValueError):
            parse_playback_speed("custom", "fast")

    def test_unknown_option_is_refused(self):
        with self.assertRaises(ValueError):
            parse_playback_speed("2.0x")

    def test_missing_choice_defaults_to_original_speed(self):
        self.assertEqual(parse_playback_speed(None), 1.0)


class TestSlowdownMath(unittest.TestCase):
    def test_frame_counts_grow_by_the_inverse_factor(self):
        self.assertEqual(slowdown_frame_count(192, 0.5), 384)
        self.assertEqual(slowdown_frame_count(192, 0.75), 256)
        self.assertEqual(slowdown_frame_count(8, 1.0), 8)

    def test_zero_frames_stay_zero(self):
        self.assertEqual(slowdown_frame_count(0, 0.5), 0)

    def test_invalid_speed_is_refused(self):
        for bad in (0.0, -1.0, 1.5):
            with self.assertRaises(ValueError):
                slowdown_frame_count(10, bad)

    def test_half_speed_holds_every_source_frame_twice(self):
        slowed = slowdown_video(_identity_video(24), 0.5)
        self.assertEqual(slowed.shape[0], 48)
        self.assertEqual(slowed[:6, 0, 0, 0].tolist(), [0, 1, 1, 2, 2, 3])
        self.assertEqual(slowed[-1, 0, 0, 0].item(), 23)

    def test_no_interpolation_only_copies_of_source_frames(self):
        source = _identity_video(10)
        slowed = slowdown_video(source, 0.75)
        # every output frame must be byte-identical to some source frame
        for index in range(slowed.shape[0]):
            source_index = int(slowed[index, 0, 0, 0].item())
            self.assertTrue(torch.equal(slowed[index], source[source_index]))

    def test_original_speed_is_a_passthrough(self):
        source = _identity_video(24)
        self.assertIs(slowdown_video(source, 1.0), source)


class TestStreamingSlowdownMath(unittest.TestCase):
    def test_lazy_stream_matches_tensor_mapping_exactly(self):
        for frames in (1, 2, 8, 24, 25):
            for speed in (0.5, 0.6, 0.75, 1.0):
                with self.subTest(frames=frames, speed=speed):
                    source = _identity_video(frames)
                    expected = slowdown_video(source, speed)
                    stats = {}
                    actual = torch.stack(list(iter_slowed_frames(
                        list(source), speed, stats=stats)))
                    self.assertTrue(torch.equal(actual, expected))
                    self.assertEqual(stats, {
                        "source_frames": frames,
                        "processed_frames": int(expected.shape[0]),
                    })

    def test_stream_stays_lazy_while_producing_frames(self):
        consumed = []

        def source():
            for index in range(100):
                consumed.append(index)
                yield index

        stream = iter_slowed_frames(source(), 0.5)
        self.assertEqual([next(stream) for _ in range(3)], [0, 1, 1])
        self.assertEqual(consumed, [0, 1])
        stream.close()


@unittest.skipIf(NODES is None, "comfy_api unavailable")
class TestNodeSlowdownContract(unittest.TestCase):
    def run_manager(self, **overrides):
        kwargs = dict(
            video=torch.zeros(48, 2, 2, 3), fps=24, segment_duration=1.0,
            motion_context_frames="0", segment_id=1,
            audio={"waveform": torch.zeros(1, 1, 48000), "sample_rate": 24000},
            align_to_h3_grid=False, save_enabled=False,
        )
        kwargs.update(overrides)
        return NODES.H3LongVideoManager.execute(**kwargs).args

    def test_half_speed_slows_the_whole_timeline_before_cutting(self):
        output = self.run_manager(playback_speed="0.5x")
        # 48 frames -> 96 slowed frames, cut into 1s (24f) slices: 4 segments
        self.assertEqual(output[0].shape[0], 24)
        self.assertEqual(output[2:], (24, 4))
        # one second of audio still covers one second of slowed film
        self.assertEqual(output[1]["waveform"].shape[-1], 24000)

    def test_original_speed_keeps_the_historical_result(self):
        output = self.run_manager(playback_speed="1.0x")
        self.assertEqual(output[0].shape[0], 24)
        self.assertEqual(output[2:], (24, 2))
        self.assertEqual(output[1]["waveform"].shape[-1], 24000)

    def test_motion_context_overlap_is_22_real_frames_on_the_slowed_timeline(self):
        # 48 frames at 0.5x -> 96 slowed frames; 2s (48f) slices keep a 22-frame
        # leading overlap: seg 2 extracts 48 frames = 22 context + 26 main.
        output = self.run_manager(
            playback_speed="0.5x", segment_duration=2.0, segment_id=2,
            motion_context_frames="22")
        self.assertEqual(output[0].shape[0], 48)
        self.assertEqual(output[2], 48)
        self.assertEqual(output[3], 3)

    def test_bad_custom_speed_fails_loudly(self):
        with self.assertRaises(ValueError):
            self.run_manager(playback_speed="custom", playback_speed_custom=0.0)


@unittest.skipIf(NODES is None, "comfy_api unavailable")
class TestSmartSplitSlowdown(unittest.TestCase):
    """Smart Split must slow the timeline before it looks for scene cuts."""

    def _run(self, playback_speed, cuts):
        meta = {
            "method": "mock", "sensitivity": "medium", "adaptive_threshold": 3.0,
            "analysis_size": "2x2", "cut_count": len(cuts),
            "scene_count": len(cuts) + 1,
        }
        with mock.patch.object(NODES, "detect_scene_cuts",
                               return_value=(cuts, meta)) as detect:
            output = NODES.H3SmartSplit.execute(
                video=torch.zeros(48, 2, 2, 3), fps=24,
                detection_sensitivity="medium", motion_context_frames="0",
                segment_id=1,
                audio={"waveform": torch.zeros(1, 1, 48000), "sample_rate": 24000},
                save_enabled=False, playback_speed=playback_speed,
            ).args
        return output, detect

    def test_half_speed_slows_the_whole_timeline_before_detection(self):
        output, detect = self._run("0.5x", [48])
        # 48 source frames -> 96 slowed frames; cuts are indices of that timeline.
        self.assertEqual(detect.call_args.args[0].shape[0], 96)
        self.assertEqual(output[2:], (48, 2))
        self.assertEqual(output[1]["waveform"].shape[-1], 48000)

    def test_original_speed_keeps_the_historical_result(self):
        output, detect = self._run("1.0x", [24])
        self.assertEqual(detect.call_args.args[0].shape[0], 48)
        self.assertEqual(output[2:], (24, 2))
        self.assertEqual(output[1]["waveform"].shape[-1], 24000)


class TestProjectPlaybackMeta(unittest.TestCase):
    def setUp(self):
        from tests._temp_dir import make_temp_dir
        from comfyui.segment_store import set_base_dir_override
        self._make_temp_dir = make_temp_dir
        self._override = set_base_dir_override
        self.dir = make_temp_dir("h3lvm_playback")
        set_base_dir_override(self.dir)

    def tearDown(self):
        from comfyui.segment_store import set_base_dir_override
        set_base_dir_override(None)
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_meta_round_trips_and_survives_later_segment_saves(self):
        from comfyui.segment_store import (
            load_project_index, save_segment, set_project_playback_meta,
        )
        save_segment("Proj", 1, torch.zeros(5, 2, 2, 3), None, fps=24)
        set_project_playback_meta("Proj", {
            "playback_speed": 0.5, "source_fps": 24, "working_fps": 24,
            "source_frames": 192, "source_duration_sec": 8.0,
            "processed_frames": 384, "processed_duration_sec": 16.0,
            "motion_context_frames": 22,
        })
        idx = load_project_index("Proj")
        self.assertEqual(idx["playback"]["playback_speed"], 0.5)
        self.assertEqual(idx["playback"]["motion_context_frames"], 22)

        # A later segment save must not drop the block (upsert keeps top-level keys)
        save_segment("Proj", 2, torch.zeros(5, 2, 2, 3), None, fps=24)
        idx = load_project_index("Proj")
        self.assertEqual(idx["playback"]["playback_speed"], 0.5)
        self.assertEqual(idx["total_segments"], 2)

        # Re-cutting at 1.0x replaces the stale slow-motion metadata
        set_project_playback_meta("Proj", {"playback_speed": 1.0})
        self.assertEqual(load_project_index("Proj")["playback"]["playback_speed"], 1.0)

    def test_old_project_index_without_the_block_is_still_readable(self):
        from comfyui.segment_store import load_project_index
        idx = load_project_index("OldProj")
        self.assertNotIn("playback", idx)
        self.assertEqual(idx["total_segments"], 0)


if __name__ == "__main__":
    unittest.main()
