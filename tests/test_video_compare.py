"""Backend behaviour for the independent H3 video comparison node."""
from __future__ import annotations

import asyncio
import io
import os
import shutil
import unittest
from unittest import mock

from tests.test_node_schema import LOAD_ERROR, NODES

_TEST_TEMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".tmp_tests")


@unittest.skipIf(NODES is None, f"comfy_api unavailable: {LOAD_ERROR}")
class TestVideoCompare(unittest.TestCase):
    def setUp(self):
        from h3lvm.comfyui import video_compare
        self.module = video_compare
        self.case = os.path.join(_TEST_TEMP, "virtual_compare")
        os.makedirs(self.case, exist_ok=True)
        self.before = os.path.join(self.case, "before.mp4")
        self.after = os.path.join(self.case, "after.mp4")
        self.isfile = mock.patch.object(self.module.os.path, "isfile", return_value=True)
        self.isfile.start()

    def tearDown(self):
        self.isfile.stop()
        shutil.rmtree(self.case, ignore_errors=True)

    def test_nested_vhs_filename_values_resolve(self):
        value = (True, [{"filenames": [{"fullpath": self.before}]}])
        self.assertEqual(self.module._find_video(value, "原"), self.before)

    def test_execute_returns_vhs_outputs_and_ui_payload(self):
        output = self.module.H3VideoCompareSlider.execute(
            slider_position=0.4,
            before_label="A",
            after_label="B",
            show_labels=True,
            loop=False,
            muted=True,
            record_duration=3,
            before_video=self.before,
            after_video=self.after,
        )
        self.assertEqual(output.result, ((True, [self.before]), (True, [self.after])))
        self.assertEqual(output.ui["h3_video_compare"][0]["role"], "before")
        self.assertEqual(output.ui["h3_video_compare_settings"]["fps"], 24.0)

    def test_image_inputs_use_the_streaming_mp4_encoder(self):
        images = mock.Mock(ndim=4)
        images.shape = (2, 8, 8, 3)
        with mock.patch.object(self.module, "_encode_images_mp4", return_value=True) as encode:
            with mock.patch.object(self.module.folder_paths, "get_temp_directory", return_value=self.case):
                with mock.patch.object(self.module.os, "makedirs"):
                    output = self.module.H3VideoCompareSlider.execute(
                        0.5, "A", "B", True, True, True, 5,
                        fps=30, before_images=images, after_images=images,
                    )
        self.assertEqual(encode.call_count, 2)
        self.assertEqual(encode.call_args.args[1], 30.0)
        self.assertTrue(output.ui["h3_video_compare"][0]["path"].endswith(".mp4"))

    def test_image_encoder_writes_one_frame_at_a_time(self):
        class InputPipe:
            def __init__(self):
                self.writes = []

            def write(self, data):
                self.writes.append(data)

            def close(self):
                pass

        class Process:
            def __init__(self):
                self.stdin = InputPipe()
                self.stderr = io.BytesIO()

            def wait(self, timeout=None):
                return 0

            def kill(self):
                pass

        images = self.module.torch.zeros((3, 9, 11, 3), dtype=self.module.torch.float32)
        process = Process()
        with mock.patch.object(self.module, "_ffmpeg_executable", return_value="ffmpeg"):
            with mock.patch.object(self.module.subprocess, "Popen", return_value=process) as popen:
                with mock.patch.object(self.module.os.path, "getsize", return_value=100):
                    result = self.module._encode_images_mp4(images, 24.0, self.before)
        self.assertTrue(result)
        self.assertEqual(len(process.stdin.writes), 3)
        self.assertTrue(all(len(data) == 10 * 8 * 3 for data in process.stdin.writes))
        self.assertIn("10x8", popen.call_args.args[0])

    def test_upload_limit_stops_before_writing_the_excess_chunk(self):
        class Part:
            def __init__(self, chunks):
                self.chunks = iter(chunks)

            async def read_chunk(self, size):
                return next(self.chunks, b"")

        path = os.path.join(self.case, "limited.mp4")
        with self.assertRaisesRegex(ValueError, "限制"):
            asyncio.run(self.module._write_part_limited(Part([b"ab", b"cde"]), path, 4, "视频"))
        with open(path, "rb") as stream:
            self.assertEqual(stream.read(), b"ab")

    def test_empty_upload_is_rejected(self):
        class Part:
            async def read_chunk(self, size):
                return b""

        path = os.path.join(self.case, "empty.mp4")
        with self.assertRaisesRegex(ValueError, "空文件"):
            asyncio.run(self.module._write_part_limited(Part(), path, 4, "视频"))

    def test_recording_transcode_has_a_timeout(self):
        with mock.patch.object(self.module, "_ffmpeg_executable", return_value="ffmpeg"):
            with mock.patch.object(
                self.module.subprocess, "run",
                side_effect=self.module.subprocess.TimeoutExpired("ffmpeg", 1),
            ):
                with self.assertRaisesRegex(RuntimeError, "超过 15 分钟"):
                    self.module._convert_recording("in.webm", "out.mp4")

    def test_preview_cleanup_is_bounded_and_leaves_other_files(self):
        keep = os.path.join(self.case, "h3_compare_keep.mp4")
        recent = os.path.join(self.case, "h3_compare_recent.mp4")
        extra = os.path.join(self.case, "h3_compare_extra.mp4")
        old = os.path.join(self.case, "h3_compare_old.mp4")
        unrelated = os.path.join(self.case, "unrelated.mp4")
        for path in (keep, recent, extra, old, unrelated):
            with open(path, "wb") as stream:
                stream.write(b"x")
        for path, modified in ((keep, 800), (recent, 990), (extra, 980), (old, 0)):
            os.utime(path, (modified, modified))
        with mock.patch.object(self.module.folder_paths, "get_temp_directory", return_value=self.case):
            with mock.patch.object(self.module, "PREVIEW_MAX_FILES", 1):
                self.module._cleanup_compare_previews(keep=[keep], now=1000)
        self.assertTrue(os.path.exists(keep))
        self.assertTrue(os.path.exists(recent))
        self.assertFalse(os.path.exists(extra))
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(unrelated))

    def test_media_route_only_reads_comfy_directories(self):
        with mock.patch.multiple(
            self.module.folder_paths,
            get_input_directory=mock.Mock(return_value=self.case),
            get_output_directory=mock.Mock(return_value=self.case),
            get_temp_directory=mock.Mock(return_value=self.case),
        ):
            self.assertEqual(self.module._readable_media(self.before), self.before)
            outside = os.path.join(os.path.dirname(self.case), "outside.mp4")
            with self.assertRaises(PermissionError):
                self.module._readable_media(outside)

    def test_media_route_resolves_links_before_checking_the_boundary(self):
        linked = os.path.join(self.case, "linked", "secret.mp4")
        outside = os.path.join(os.path.dirname(self.case), "outside", "secret.mp4")
        realpath = self.module.os.path.realpath

        def resolve(path):
            if os.path.normcase(os.path.normpath(path)) == os.path.normcase(os.path.normpath(linked)):
                return outside
            return realpath(path)

        with mock.patch.multiple(
            self.module.folder_paths,
            get_input_directory=mock.Mock(return_value=self.case),
            get_output_directory=mock.Mock(return_value=self.case),
            get_temp_directory=mock.Mock(return_value=self.case),
        ):
            with mock.patch.object(self.module.os.path, "realpath", side_effect=resolve):
                with self.assertRaises(PermissionError):
                    self.module._readable_media(linked)


if __name__ == "__main__":
    unittest.main()
