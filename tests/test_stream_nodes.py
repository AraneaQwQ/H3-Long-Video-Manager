"""Real file execution of the independent v2 producer nodes."""
from __future__ import annotations

import importlib
import os
import shutil
import unittest
from unittest import mock

import torch

from tests._media_clip import have_ffmpeg, make_clip
from tests._temp_dir import make_temp_dir
from tests.test_node_schema import NODES


@unittest.skipIf(NODES is None or not have_ffmpeg(), "needs comfy_api and ffmpeg")
class TestStreamNodes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = importlib.import_module(".stream_nodes", package=NODES.__package__)
        cls.store = importlib.import_module(".segment_store", package=NODES.__package__)

    def setUp(self):
        self.tmpdir = make_temp_dir(prefix="h3lvm_stream_nodes_")
        self.store.set_base_dir_override(os.path.join(self.tmpdir, "bin"))
        self.addCleanup(self.store.set_base_dir_override, None)
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        try:
            import av  # noqa: F401
        except ImportError:
            self.skipTest("needs PyAV")

    def clip(self, name="source.mp4", **kwargs):
        return make_clip(os.path.join(self.tmpdir, name), **kwargs)

    def test_manager_v2_stream_saves_uint8_and_outputs_selected_segment(self):
        path = self.clip(fps=60, duration=2.0, audio=True)
        output = NODES.H3LongVideoManagerV2.execute(
            video="", custom_path=path, segment_duration=1.0,
            motion_context_frames="0", segment_id=2, align_to_h3_grid=False,
            project_name="StreamManager", save_enabled=True,
        ).args
        self.assertEqual(output[0].shape[0], 24)
        self.assertEqual(output[2:], (24, 2))
        saved, audio, meta = self.store.load_segment("StreamManager", 2)
        self.assertEqual(saved.shape, output[0].shape)
        self.assertTrue(torch.equal(saved, output[0]))
        self.assertEqual(meta["fps"], 24)
        self.assertIsNotNone(audio)
        self.assertEqual(audio["waveform"].shape[-1], output[1]["waveform"].shape[-1])

    def test_manager_v2_ranges_match_v1_with_motion_context(self):
        path = self.clip(fps=24, duration=3.0)
        with mock.patch.object(self.module, "save_segment") as save:
            output = NODES.H3LongVideoManagerV2.execute(
                video="", custom_path=path, segment_duration=1.0,
                motion_context_frames="5", segment_id=1, align_to_h3_grid=False,
                project_name="StreamMC", save_enabled=True,
            ).args
        self.assertEqual(output[2:], (24, 4))
        ranges = [call.kwargs["meta"] for call in save.call_args_list]
        self.assertEqual([item["main_start"] for item in ranges], [0, 24, 43, 62])
        self.assertEqual([item["context_frames"] for item in ranges], [0, 5, 5, 5])
        self.assertEqual([call.kwargs["video"].dtype for call in save.call_args_list],
                         [self.module.torch.uint8] * 4)

    def test_smart_v2_detects_first_then_streams_known_ranges(self):
        path = self.clip(fps=60, duration=2.0)
        with mock.patch.object(self.module, "_detect_file_cuts",
                               return_value=(48, [24], {"method": "mock"})), \
                mock.patch.object(self.module, "save_segment") as save:
            output = NODES.H3SmartSplitV2.execute(
                video="", custom_path=path, detection_sensitivity="medium",
                motion_context_frames="5", segment_id=2,
                project_name="StreamSmart", save_enabled=True,
            ).args
        self.assertEqual(output[0].shape[0], 29)
        self.assertEqual(output[2:], (29, 2))
        self.assertEqual(save.call_args_list[1].kwargs["thumbnail_frame"], 5)
        self.assertEqual(save.call_args_list[1].kwargs["meta"]["main_start"], 24)

    def test_manager_v2_half_speed_slows_video_audio_and_project_metadata(self):
        path = self.clip(name="manager-slow.mp4", fps=24, duration=2.0, audio=True)
        output = NODES.H3LongVideoManagerV2.execute(
            video="", custom_path=path, segment_duration=1.0,
            motion_context_frames="0", segment_id=2, align_to_h3_grid=False,
            project_name="StreamSlow", save_enabled=True,
            playback_speed="0.5x",
        ).args
        self.assertEqual(output[0].shape[0], 24)
        self.assertEqual(output[2:], (24, 4))
        self.assertEqual(output[1]["waveform"].shape[-1], output[1]["sample_rate"])
        playback = self.store.load_project_index("StreamSlow")["playback"]
        self.assertEqual(playback["playback_speed"], 0.5)
        self.assertEqual(playback["source_frames"], 48)
        self.assertEqual(playback["processed_frames"], 96)
        _video, _audio, segment = self.store.load_segment("StreamSlow", 2)
        self.assertEqual(segment["playback_speed"], 0.5)

    def test_smart_v2_half_speed_detects_on_the_slowed_timeline(self):
        path = self.clip(name="smart-slow.mp4", fps=24, duration=2.0)
        with mock.patch.object(self.module, "_detect_file_cuts",
                               return_value=(96, [48], {"method": "mock"})) as detect:
            output = NODES.H3SmartSplitV2.execute(
                video="", custom_path=path, detection_sensitivity="medium",
                motion_context_frames="0", segment_id=2,
                project_name="StreamSmartSlow", save_enabled=False,
                playback_speed="0.5x",
            ).args
        self.assertEqual(output[0].shape[0], 48)
        self.assertEqual(output[2:], (48, 2))
        self.assertEqual(detect.call_args.kwargs["playback_speed"], 0.5)

    def test_v2_playback_inputs_are_appended_and_cached(self):
        for node in (NODES.H3LongVideoManagerV2, NODES.H3SmartSplitV2):
            schema = node.define_schema()
            ids = [item.id for item in schema.inputs]
            self.assertEqual(ids[-2:], ["playback_speed", "playback_speed_custom"])
            self.assertEqual(schema.inputs[-2].default, "1.0x")
            self.assertEqual(schema.inputs[-1].default, 1.0)
            base = node.fingerprint_inputs(
                save_enabled=False, video="", custom_path="", playback_speed="1.0x")
            slowed = node.fingerprint_inputs(
                save_enabled=False, video="", custom_path="", playback_speed="0.5x")
            self.assertNotEqual(base, slowed)

    def test_stream_detection_matches_established_tensor_detection(self):
        from comfyui.video_decode import decode_video
        from core.smart_split import detect_scene_cuts
        path = self.clip(fps=24, duration=2.0)
        video, _audio, _info = decode_video(path)
        expected, _ = detect_scene_cuts(video, video.shape[0], 24, "medium")
        total, actual, _ = self.module._detect_file_cuts(path, "medium", video.shape[0])
        self.assertEqual(total, video.shape[0])
        self.assertEqual(actual, expected)

    def test_slowed_stream_detection_matches_slowed_tensor_detection(self):
        from comfyui.video_decode import decode_video
        from core.frame_rate import slowdown_video
        from core.smart_split import detect_scene_cuts
        path = self.clip(name="detect-slow.mp4", fps=24, duration=2.0)
        video, _audio, _info = decode_video(path)
        slowed = slowdown_video(video, 0.5)
        expected, _ = detect_scene_cuts(slowed, slowed.shape[0], 24, "medium")
        stats = {}
        total, actual, _ = self.module._detect_file_cuts(
            path, "medium", slowed.shape[0], playback_speed=0.5,
            playback_stats=stats)
        self.assertEqual(total, slowed.shape[0])
        self.assertEqual(actual, expected)
        self.assertEqual(stats["source_frames"], video.shape[0])
        self.assertEqual(stats["processed_frames"], slowed.shape[0])

    def test_producer_ids_outputs_and_standalone_execution(self):
        manager = NODES.H3LongVideoManagerV2.define_schema()
        smart = NODES.H3SmartSplitV2.define_schema()
        self.assertEqual(manager.node_id, "H3 Long Video Manager v2")
        self.assertEqual(smart.node_id, "H3 Smart Split v2")
        self.assertNotEqual(manager.node_id, NODES.H3LongVideoManager.define_schema().node_id)
        self.assertEqual([item.display_name for item in manager.outputs],
                         ["IMAGE", "AUDIO", "frame_count", "total_segments"])
        self.assertEqual([item.display_name for item in smart.outputs],
                         ["IMAGE", "AUDIO", "frame_count", "total_segments"])
        self.assertTrue(manager.is_output_node)
        self.assertTrue(smart.is_output_node)
        self.assertTrue(NODES.H3LongVideoManager.define_schema().is_output_node)
        self.assertTrue(NODES.H3SmartSplit.define_schema().is_output_node)


if __name__ == "__main__":
    unittest.main()
