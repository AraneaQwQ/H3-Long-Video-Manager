"""Disk-first H3 Video Loader schema, path, cache and real decode tests."""
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


@unittest.skipIf(NODES is None, "comfy_api unavailable")
class TestVideoLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = importlib.import_module(".video_loader_node", package=NODES.__package__)
        cls.node = NODES.H3VideoLoader

    def setUp(self):
        self.tmpdir = make_temp_dir(prefix="h3lvm_loader_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_schema_has_no_browser_upload_and_exposes_24fps(self):
        schema = self.node.define_schema()
        video = next(item for item in schema.inputs if item.id == "video")
        self.assertIsNone(video.upload)
        self.assertEqual(
            [item.display_name for item in schema.outputs],
            ["IMAGE", "AUDIO", "frame_count", "fps"],
        )
        self.assertIn("H3VideoLoader", [item.__name__ for item in NODES.NODE_LIST])

    def test_input_listing_includes_nested_videos_but_not_documents(self):
        nested = os.path.join(self.tmpdir, "nested")
        os.makedirs(nested)
        for relative in ("b.mp4", "nested/a.webm"):
            with open(os.path.join(self.tmpdir, relative), "wb") as handle:
                handle.write(b"video")
        with open(os.path.join(self.tmpdir, "notes.txt"), "w", encoding="utf-8") as handle:
            handle.write("not a video")
        with mock.patch.object(self.module.folder_paths, "get_input_directory", return_value=self.tmpdir), \
                mock.patch.object(self.module.folder_paths, "filter_files_content_types",
                                  side_effect=lambda names, _types: [
                                      name for name in names
                                      if os.path.splitext(name)[1].lower() in (".mp4", ".webm")
                                  ]):
            self.assertEqual(self.module.list_input_videos(), ["b.mp4", "nested/a.webm"])

    def test_explicit_absolute_path_wins_over_the_combo(self):
        path = os.path.join(self.tmpdir, "large.mp4")
        with open(path, "wb") as handle:
            handle.write(b"video")
        self.assertEqual(self.module.resolve_video_path("missing.mp4", f'"{path}"'), path)

    def test_missing_file_is_a_chinese_validation_error(self):
        result = self.node.validate_inputs(custom_path=os.path.join(self.tmpdir, "missing.mp4"))
        self.assertIsInstance(result, str)
        self.assertIn("不存在", result)

    def test_directory_browser_lists_only_immediate_entries_and_blocks_escape(self):
        os.makedirs(os.path.join(self.tmpdir, "nested"))
        for relative in ("root.mp4", "nested/child.mp4", "nested/ignore.txt"):
            with open(os.path.join(self.tmpdir, relative), "wb") as handle:
                handle.write(b"video")
        with mock.patch.object(self.module.folder_paths, "get_input_directory", return_value=self.tmpdir), \
                mock.patch.object(self.module, "_is_video_name",
                                  side_effect=lambda name: name.lower().endswith(".mp4")):
            root = self.module.list_video_directory()
            nested = self.module.list_video_directory("nested")
            with self.assertRaisesRegex(ValueError, "不能离开"):
                self.module.list_video_directory("..")
        self.assertEqual([item["name"] for item in root["directories"]], ["nested"])
        self.assertEqual([item["path"] for item in root["files"]], ["root.mp4"])
        self.assertEqual(root["parent"], None)
        self.assertEqual([item["path"] for item in nested["files"]], ["nested/child.mp4"])
        self.assertEqual(nested["parent"], "")

    def test_file_info_is_limited_to_input_videos(self):
        path = os.path.join(self.tmpdir, "info.mp4")
        with open(path, "wb") as handle:
            handle.write(b"video")
        with mock.patch.object(self.module.folder_paths, "get_input_directory", return_value=self.tmpdir), \
                mock.patch.object(self.module, "_is_video_name", return_value=True), \
                mock.patch.object(self.module, "probe_video", return_value={"width": 64}) as probe:
            info = self.module.video_file_info("info.mp4")
            with self.assertRaises(ValueError):
                self.module.video_file_info(path)
        self.assertEqual(info["path"], "info.mp4")
        self.assertEqual(info["width"], 64)
        probe.assert_called_once_with(path)

    def test_fingerprint_tracks_file_changes_and_decode_size(self):
        path = os.path.join(self.tmpdir, "cache.mp4")
        with open(path, "wb") as handle:
            handle.write(b"one")
        first = self.node.fingerprint_inputs(custom_path=path)
        second = self.node.fingerprint_inputs(custom_path=path, output_size="最长边 1280")
        self.assertNotEqual(first, second)
        with open(path, "ab") as handle:
            handle.write(b"two")
        self.assertNotEqual(first, self.node.fingerprint_inputs(custom_path=path))

    def test_execute_returns_real_frame_count_24fps_and_silent_audio(self):
        path = os.path.join(self.tmpdir, "silent.mp4")
        with open(path, "wb") as handle:
            handle.write(b"video")
        image = torch.zeros(48, 2, 2, 3)
        info = {"source_fps": 60.0, "has_audio": False}
        with mock.patch.object(self.module, "decode_video", return_value=(image, None, info)) as decode:
            output = self.node.execute(custom_path=path).args
        self.assertEqual(output[2:], (48, 24))
        self.assertEqual(output[1]["waveform"].shape[-1], 88200)
        self.assertEqual(output[1]["sample_rate"], 44100)
        decode.assert_called_once_with(path, target_fps=24, max_side=0)


@unittest.skipIf(NODES is None or not have_ffmpeg(), "needs comfy_api and ffmpeg")
class TestVideoLoaderRealDecode(unittest.TestCase):
    def test_60fps_file_becomes_one_second_of_24fps_without_an_upload(self):
        tmpdir = make_temp_dir(prefix="h3lvm_loader_real_")
        self.addCleanup(shutil.rmtree, tmpdir, True)
        path = make_clip(os.path.join(tmpdir, "60fps.mp4"), fps=60, duration=1.0, audio=True)
        try:
            import av  # noqa: F401
        except ImportError:
            self.skipTest("needs PyAV")
        output = NODES.H3VideoLoader.execute(custom_path=path).args
        self.assertEqual(output[0].shape[0], 24)
        self.assertEqual(output[2:], (24, 24))
        audio_seconds = output[1]["waveform"].shape[-1] / output[1]["sample_rate"]
        self.assertAlmostEqual(audio_seconds, 1.0, places=3)


if __name__ == "__main__":
    unittest.main()
