"""Real HTTP checks for the H3 Video Loader server-side file browser."""
from __future__ import annotations

import importlib
import os
import unittest
from unittest import mock

from tests._media_clip import make_clip
from tests.test_node_schema import NODES
from tests.test_upload_api import ApiFixture


@unittest.skipIf(NODES is None, "comfy_api unavailable")
class TestVideoLoaderApi(ApiFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.input_dir = os.path.join(self.case, "input")
        os.makedirs(os.path.join(self.input_dir, "nested"))
        self.loader = importlib.import_module(".video_loader_node", package=NODES.__package__)
        self.preview = importlib.import_module(".source_preview", package=NODES.__package__)
        self.preview.clear_source_previews()
        self.addCleanup(self.preview.clear_source_previews)
        self.cache_dir = os.path.join(self.case, "temp")
        cache_patcher = mock.patch.object(
            self.preview.folder_paths, "get_temp_directory", return_value=self.cache_dir)
        cache_patcher.start()
        self.addCleanup(cache_patcher.stop)
        patcher = mock.patch.object(
            self.loader.folder_paths, "get_input_directory", return_value=self.input_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_list_and_probe_selected_input_video(self):
        path = make_clip(os.path.join(self.input_dir, "nested", "clip.mp4"), fps=60, duration=1.0)
        response = await self.get("/h3_lvm/video_files?directory=nested")
        self.assertEqual(response.status, 200)
        listing = await response.json()
        self.assertEqual([item["path"] for item in listing["files"]], ["nested/clip.mp4"])
        response = await self.get("/h3_lvm/video_file_info?path=nested%2Fclip.mp4")
        self.assertEqual(response.status, 200)
        info = await response.json()
        self.assertEqual(info["path"], "nested/clip.mp4")
        self.assertEqual(info["source_fps"], 60.0)
        self.assertEqual(info["size_bytes"], os.path.getsize(path))

    async def test_browser_routes_refuse_absolute_and_escaping_paths(self):
        for path in ("..%2F", "%2Fetc%2F"):
            response = await self.get(f"/h3_lvm/video_files?directory={path}")
            self.assertEqual(response.status, 400)
        response = await self.get("/h3_lvm/video_file_info?path=..%2Fsecret.mp4")
        self.assertEqual(response.status, 400)

    async def test_source_preview_streams_only_an_authorized_ticket(self):
        path = make_clip(os.path.join(self.input_dir, "nested", "preview.mp4"), duration=1.0)
        created = await self.post_json("/h3_lvm/source_preview", {
            "video": "nested/preview.mp4", "custom_path": "",
        })
        self.assertEqual(created.status, 200)
        data = await created.json()
        self.assertNotIn(path, data["url"])
        response = await self.client.get(data["url"])
        self.assertEqual(response.status, 200)
        with open(path, "rb") as handle:
            self.assertEqual(await response.read(), handle.read())
        self.assertEqual((await self.get("/h3_lvm/source_preview?path=secret.mp4")).status, 404)

    async def test_source_preview_supports_http_range(self):
        path = make_clip(os.path.join(self.input_dir, "range.mp4"), duration=1.0)
        created = await self.post_json("/h3_lvm/source_preview", {"video": "range.mp4"})
        data = await created.json()
        response = await self.client.get(data["url"], headers={"Range": "bytes=10-29"})
        self.assertEqual(response.status, 206)
        self.assertEqual(response.headers["Accept-Ranges"], "bytes")
        self.assertEqual(response.headers["Content-Range"], f"bytes 10-29/{os.path.getsize(path)}")
        with open(path, "rb") as handle:
            handle.seek(10)
            self.assertEqual(await response.read(), handle.read(20))

    async def test_source_preview_ticket_is_same_origin_json(self):
        make_clip(os.path.join(self.input_dir, "secure.mp4"), duration=1.0)
        refused = await self.post_json(
            "/h3_lvm/source_preview", {"video": "secure.mp4"}, origin=False)
        self.assertEqual(refused.status, 403)
        refused = await self.post_json(
            "/h3_lvm/source_preview", {"video": "secure.mp4"}, content_type="text/plain")
        self.assertEqual(refused.status, 415)

    async def test_source_preview_supports_the_explicit_local_path(self):
        path = make_clip(os.path.join(self.case, "outside-input.mp4"), duration=1.0)
        created = await self.post_json("/h3_lvm/source_preview", {
            "video": "", "custom_path": path,
        })
        self.assertEqual(created.status, 200)
        data = await created.json()
        self.assertEqual(data["name"], "outside-input.mp4")
        self.assertEqual((await self.client.get(data["url"])).status, 200)

    async def test_hevc_is_sent_straight_to_the_compatible_preview(self):
        make_clip(os.path.join(self.input_dir, "hevc.mp4"), duration=1.0)
        with mock.patch.object(self.preview, "probe_video", return_value={"codec_name": "hevc"}):
            created = await self.post_json("/h3_lvm/source_preview", {"video": "hevc.mp4"})
        data = await created.json()
        self.assertTrue(data["proxy_recommended"])
        self.assertEqual(data["codec_name"], "hevc")

    async def test_compatible_preview_is_h264_cached_and_never_changes_the_source(self):
        path = make_clip(os.path.join(self.input_dir, "proxy.mp4"), fps=60, duration=1.0, audio=True)
        with open(path, "rb") as handle:
            original = handle.read()
        created = await self.post_json("/h3_lvm/source_preview", {"video": "proxy.mp4"})
        data = await created.json()
        self.assertFalse(data["proxy_recommended"])
        self.assertEqual((await self.client.get(data["url"] + "&proxy=1")).status, 404)
        with mock.patch.object(
                self.preview.subprocess, "run", wraps=self.preview.subprocess.run) as runner:
            converted = await self.post_json(data["proxy_url"], {})
            self.assertEqual(converted.status, 200)
            proxy = await converted.json()
            self.assertTrue(proxy["proxy"])
            response = await self.client.get(proxy["url"])
            self.assertEqual(response.status, 200)
            self.assertGreater(len(await response.read()), 0)
            again = await self.post_json(data["proxy_url"], {})
            self.assertEqual((await again.json())["url"], proxy["url"])
            self.assertEqual(runner.call_count, 1, "an unchanged source reuses its proxy")
        cache = os.path.join(self.cache_dir, "h3-lvm-source-preview")
        files = [os.path.join(cache, name) for name in os.listdir(cache) if name.endswith(".mp4")]
        self.assertEqual(len(files), 1)
        import av
        with av.open(files[0]) as container:
            self.assertEqual(container.streams.video[0].codec_context.name, "h264")
            self.assertEqual(container.streams.video[0].codec_context.pix_fmt, "yuv420p")
            self.assertEqual(container.streams.video[0].average_rate, 60)
            self.assertEqual(len(container.streams.audio), 1)
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), original)

    async def test_compatible_preview_keeps_ticket_and_same_origin_checks(self):
        make_clip(os.path.join(self.input_dir, "proxy-security.mp4"), duration=1.0)
        created = await self.post_json("/h3_lvm/source_preview", {"video": "proxy-security.mp4"})
        data = await created.json()
        refused = await self.post_json(data["proxy_url"], {}, origin=False)
        self.assertEqual(refused.status, 403)
        refused = await self.post_json(data["proxy_url"], {}, content_type="text/plain")
        self.assertEqual(refused.status, 415)
        invalid = await self.post_json("/h3_lvm/source_preview_proxy?ticket=invalid", {})
        self.assertEqual(invalid.status, 400)

    async def test_system_picker_route_returns_an_absolute_path_and_checks_origin(self):
        api_module = importlib.import_module(".server_api", package=NODES.__package__)
        selected = {"cancelled": False, "path": os.path.join(self.case, "anywhere.mp4")}
        with mock.patch.object(api_module, "choose_system_video", return_value=selected) as picker:
            response = await self.client.post(
                "/h3_lvm/system_video_picker", headers={"Origin": self.origin()})
            self.assertEqual(response.status, 200)
            self.assertEqual(await response.json(), selected)
            picker.assert_called_once_with()
        refused = await self.client.post("/h3_lvm/system_video_picker")
        self.assertEqual(refused.status, 403)


if __name__ == "__main__":
    unittest.main()
