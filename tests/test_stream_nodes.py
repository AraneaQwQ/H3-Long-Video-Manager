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

    def test_stream_detection_matches_established_tensor_detection(self):
        from comfyui.video_decode import decode_video
        from core.smart_split import detect_scene_cuts
        path = self.clip(fps=24, duration=2.0)
        video, _audio, _info = decode_video(path)
        expected, _ = detect_scene_cuts(video, video.shape[0], 24, "medium")
        total, actual, _ = self.module._detect_file_cuts(path, "medium", video.shape[0])
        self.assertEqual(total, video.shape[0])
        self.assertEqual(actual, expected)

    def test_v2_ids_and_outputs_are_independent(self):
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
        self.assertFalse(NODES.H3LongVideoManager.define_schema().is_output_node)
        self.assertFalse(NODES.H3SmartSplit.define_schema().is_output_node)


if __name__ == "__main__":
    unittest.main()
