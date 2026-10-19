"""Tests for H3 Long Video Manager - the /h3_lvm/* HTTP routes (upload mode).

These run the real aiohttp handlers over a real socket, because the questions worth
asking are HTTP questions: what status does a bad scope get, does a half-uploaded file
stay out of the index, and does an older panel request still work.

Run with:
    cd H3-Long-Video-Manager
    python -m tests.test_upload_api
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import types
import unittest
import urllib.parse
from unittest import mock

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from tests._media_clip import have_ffmpeg, make_broken, make_clip

try:
    import av  # noqa: F401
    import numpy  # noqa: F401
    HAS_AV = True
except ImportError:
    HAS_AV = False

READY = have_ffmpeg() and HAS_AV


class _FakePromptServer:
    """Just enough of ComfyUI's PromptServer for register_h3lvm_routes()."""

    def __init__(self):
        self.routes = web.RouteTableDef()
        self.events = []

    def send_sync(self, event, payload):
        self.events.append((event, payload))


_fake_server = types.ModuleType("server")
_fake_server.PromptServer = type("PromptServer", (), {"instance": _FakePromptServer()})

from tests._plugin_import import load as _load_plugin

segment_store = _load_plugin("comfyui.segment_store")
server_api = _load_plugin("comfyui.server_api")
uvs = _load_plugin("comfyui.uploaded_video_store")
vd = _load_plugin("comfyui.video_decode")


def _register_on_fake_server():
    """Register the routes on our own PromptServer, then put the real one back.

    With COMFYUI_ROOT on sys.path the real ComfyUI ``server`` module is importable, and
    its PromptServer.instance is None until ComfyUI starts - register_h3lvm_routes()
    would then skip quietly and every request would answer 404. The fake only has to be
    in place while the handlers are attached; afterwards the routes already live in our
    own RouteTableDef, so the global name is restored as we found it.
    """
    previous = sys.modules.get("server")
    sys.modules["server"] = _fake_server
    try:
        server_api.register_h3lvm_routes()
    finally:
        if previous is not None:
            sys.modules["server"] = previous
        else:
            sys.modules.pop("server", None)


_register_on_fake_server()
ROUTES = _fake_server.PromptServer.instance.routes
EVENTS = _fake_server.PromptServer.instance.events
if not ROUTES:
    raise RuntimeError("the /h3_lvm/* routes were not registered; the tests would all 404")


@unittest.skipUnless(READY, "needs PyAV and aiohttp and ffmpeg on PATH")
class ApiFixture(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.case = tempfile.mkdtemp(prefix="h3lvm_api_")
        uvs.set_base_dir_override(os.path.join(self.case, "uploads"))
        segment_store.set_base_dir_override(os.path.join(self.case, "bin"))
        self.app = web.Application()
        self.app.add_routes(ROUTES)
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        uvs.set_base_dir_override(None)
        segment_store.set_base_dir_override(None)
        shutil.rmtree(self.case, ignore_errors=True)
        EVENTS.clear()

    def origin(self):
        return str(self.client.make_url("/"))

    async def get(self, path, **kwargs):
        return await self.client.get(path, headers={"Origin": self.origin()}, **kwargs)

    async def post_json(self, path, payload, origin=True, content_type="application/json"):
        headers = {"Origin": self.origin()} if origin else {}
        # aiohttp sets application/json itself when json= is used, so an override has
        # to go through the headers to test a route that refuses the wrong type.
        headers["Content-Type"] = content_type
        return await self.client.post(path, json=payload, headers=headers)

    async def upload(self, project, path, origin=True, extra=None):
        form = aiohttp.FormData()
        if extra is not None:
            for key, value in extra:
                form.add_field(key, value)
        form.add_field("project", project)
        if path is not None:
            form.add_field("file", open(path, "rb"), filename=os.path.basename(path))
        else:
            # What a browser sends when the file input was left empty: the part is still
            # there, with no filename and no bytes.
            form.add_field("file", b"", filename="")
        headers = {"Origin": self.origin()} if origin else {}
        return await self.client.post("/h3_lvm/uploads/import", data=form, headers=headers)

    def clip(self, name="clip.mp4", **kwargs):
        return make_clip(os.path.join(self.case, name), fps=24, duration=1.0, **kwargs)

class TestProjectScope(ApiFixture):
    async def test_uploads_scope_lists_its_own_projects(self):
        created = await self.post_json("/h3_lvm/project", {"project": "show", "scope": "uploads"})
        self.assertEqual(created.status, 200)
        body = await self.get("/h3_lvm/projects?scope=uploads")
        data = await body.json()
        self.assertEqual(data["scope"], "uploads")
        self.assertEqual([row["name"] for row in data["projects"]], ["show"])
        self.assertEqual(data["projects"][0]["videos"], 0)

    async def test_a_missing_scope_still_means_the_cut_bin(self):
        await self.post_json("/h3_lvm/project", {"project": "legacy"})
        data = await (await self.get("/h3_lvm/projects")).json()
        self.assertEqual(data["scope"], "segments")
        self.assertEqual([row["name"] for row in data["projects"]], ["legacy"])
        self.assertEqual((await self.get("/h3_lvm/projects?scope=segments")).status, 200)

    async def test_reading_an_unknown_scope_falls_back_but_writes_are_refused(self):
        data = await (await self.get("/h3_lvm/projects?scope=whatever")).json()
        self.assertEqual(data["scope"], "segments")
        refused = await self.post_json("/h3_lvm/project", {"project": "x", "scope": "whatever"})
        self.assertEqual(refused.status, 400)
        self.assertIn("素材库类型", (await refused.json())["error"])

    async def test_two_libraries_same_name_do_not_see_each_other(self):
        await self.post_json("/h3_lvm/project", {"project": "same", "scope": "uploads"})
        await self.post_json("/h3_lvm/project", {"project": "same", "scope": "segments"})
        uploads = (await (await self.get("/h3_lvm/projects?scope=uploads")).json())["projects"]
        bins = (await (await self.get("/h3_lvm/projects?scope=segments")).json())["projects"]
        self.assertEqual(uploads[0]["videos"], 0)
        self.assertEqual(bins[0]["segments"], 0)
        self.assertNotEqual(uvs.index_path("same"),
                            os.path.join(self.case, "bin", "same", segment_store.INDEX_NAME))

    async def test_deleting_an_upload_project_needs_confirmation(self):
        await self.post_json("/h3_lvm/project", {"project": "careful", "scope": "uploads"})
        refused = await self.post_json("/h3_lvm/project/delete",
                                       {"project": "careful", "scope": "uploads", "confirm": "no"})
        self.assertEqual(refused.status, 400)
        ok = await self.post_json("/h3_lvm/project/delete",
                                  {"project": "careful", "scope": "uploads", "confirm": "careful"})
        self.assertEqual(ok.status, 200)
        self.assertTrue((await ok.json())["deleted"])
        self.assertEqual((await (await self.get("/h3_lvm/projects?scope=uploads")).json())["projects"], [])

    async def test_mutating_requests_need_the_same_origin(self):
        refused = await self.post_json("/h3_lvm/project", {"project": "x", "scope": "uploads"},
                                       origin=False)
        self.assertEqual(refused.status, 403)
        refused = await self.upload("x", self.clip(), origin=False)
        self.assertEqual(refused.status, 403)

    async def test_a_json_route_rejects_other_content_types(self):
        refused = await self.post_json("/h3_lvm/project", {"project": "x", "scope": "uploads"},
                                       content_type="text/plain")
        self.assertEqual(refused.status, 415)


class TestUploadRoutes(ApiFixture):
    async def test_import_registers_a_card_and_broadcasts_it(self):
        response = await self.upload("show", self.clip(audio=True))
        self.assertEqual(response.status, 200)
        record = await response.json()
        self.assertEqual(record["segment_id"], 1)
        self.assertEqual(record["original_name"], "clip.mp4")
        self.assertEqual(EVENTS, [("h3_lvm/uploads_changed",
                                   {"scope": "uploads", "project": "show",
                                    "segment_id": 1, "action": "import"})])
        cards = (await (await self.get("/h3_lvm/uploads?project=show")).json())["videos"]
        self.assertEqual(len(cards), 1)
        self.assertTrue(cards[0]["cover_url"].startswith("/view?"))
        self.assertTrue(cards[0]["browser_preview"])

    async def test_import_needs_a_file(self):
        refused = await self.upload("show", None)
        self.assertEqual(refused.status, 400)
        self.assertIn("没有收到视频文件", (await refused.json())["error"])

    async def test_import_needs_a_project_field(self):
        form = aiohttp.FormData()
        form.add_field("file", open(self.clip(), "rb"), filename="clip.mp4")
        refused = await self.client.post("/h3_lvm/uploads/import", data=form,
                                         headers={"Origin": self.origin()})
        self.assertEqual(refused.status, 400)
        self.assertIn("项目名", (await refused.json())["error"])

    async def test_import_rejects_a_broken_file_and_leaves_nothing_behind(self):
        broken = make_broken(os.path.join(self.case, "notes.mp4"))
        refused = await self.upload("clean", broken)
        self.assertEqual(refused.status, 400)
        self.assertEqual((await (await self.get("/h3_lvm/uploads?project=clean")).json())["videos"], [])
        self.assertEqual(os.listdir(uvs.get_files_dir("clean")), [])

    async def test_import_rejects_a_bad_project_name(self):
        refused = await self.upload("...", self.clip())
        self.assertEqual(refused.status, 400)

    async def test_import_needs_multipart(self):
        refused = await self.post_json("/h3_lvm/uploads/import", {"project": "show"})
        self.assertEqual(refused.status, 415)

    async def test_the_size_cap_leaves_no_partial_file(self):
        with mock.patch.object(server_api, "MAX_UPLOAD_BYTES", 64):
            refused = await self.upload("capped", self.clip())
        self.assertEqual(refused.status, 413)
        self.assertIn("上限", (await refused.json())["error"])
        self.assertEqual(uvs.count_uploads("capped"), 0)
        self.assertEqual(os.listdir(uvs.get_files_dir("capped")), [])

    async def test_delete_removes_the_card_then_reports_missing(self):
        record = await (await self.upload("bye", self.clip())).json()
        gone = await self.post_json("/h3_lvm/uploads/delete",
                                    {"project": "bye", "segment_id": record["segment_id"]})
        self.assertEqual(gone.status, 200)
        self.assertEqual((await (await self.get("/h3_lvm/uploads?project=bye")).json())["videos"], [])
        self.assertEqual(os.listdir(uvs.get_files_dir("bye")), [])
        again = await self.post_json("/h3_lvm/uploads/delete",
                                     {"project": "bye", "segment_id": record["segment_id"]})
        self.assertEqual(again.status, 404)
        self.assertEqual(EVENTS[-1][1]["action"], "delete")

    async def test_delete_needs_a_usable_segment_id(self):
        for bad in (None, "abc", 0):
            refused = await self.post_json("/h3_lvm/uploads/delete",
                                           {"project": "any", "segment_id": bad})
            self.assertEqual(refused.status, 400)

    async def test_a_damaged_index_answers_400_not_an_empty_library(self):
        await self.post_json("/h3_lvm/project", {"project": "hurt", "scope": "uploads"})
        with open(uvs.index_path("hurt"), "w", encoding="utf-8") as stream:
            stream.write("{ not json")
        refused = await self.get("/h3_lvm/uploads?project=hurt")
        self.assertEqual(refused.status, 400)
        self.assertIn(uvs.INDEX_NAME, (await refused.json())["error"])


class TestOldRoutesStillWork(ApiFixture):
    """The cut bin keeps its contract; a new library must not disturb it."""

    async def test_segment_listing_and_project_creation_are_unchanged(self):
        await self.post_json("/h3_lvm/project", {"project": "bin"})
        body = await (await self.get("/h3_lvm/segments?project=bin")).json()
        self.assertEqual(body["project_name"], "bin")
        self.assertEqual(body["segments"], [])
        self.assertEqual((await self.get("/h3_lvm/segments?project=nope")).status, 200)

    async def test_reference_scopes_are_untouched(self):
        for kind in ("image", "audio"):
            created = await self.post_json("/h3_lvm/project", {"project": "refs", "scope": kind})
            self.assertEqual(created.status, 200)
            data = await (await self.get("/h3_lvm/projects?scope=" + kind)).json()
            self.assertEqual([row["name"] for row in data["projects"]], ["refs"])
        self.assertEqual((await (await self.get("/h3_lvm/projects?scope=uploads")).json())["projects"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
@unittest.skipUnless(READY, "needs PyAV and ffmpeg on PATH")
class TestUploadReorder(ApiFixture):
    """The panel's drag handle: POST the new card order, get the new numbering back."""

    async def three(self, project="show"):
        for name in ("a.mp4", "b.mp4", "c.mp4"):
            self.assertEqual((await self.upload(project, self.clip(name))).status, 200)

    async def listed(self, project="show"):
        data = await (await self.get("/h3_lvm/uploads?project=" + project)).json()
        return ([v["segment_id"] for v in data["videos"]],
                [v["original_name"] for v in data["videos"]])

    async def test_the_order_the_panel_sends_becomes_the_numbering(self):
        await self.three()
        response = await self.post_json("/h3_lvm/uploads/reorder",
                                        {"project": "show", "order": [3, 1, 2]})
        self.assertEqual(response.status, 200)
        body = await response.json()
        self.assertEqual(body["order"], [1, 2, 3])
        self.assertEqual(body["videos"], 3)
        ids, names = await self.listed()
        self.assertEqual(ids, [1, 2, 3])
        self.assertEqual(names, ["c.mp4", "a.mp4", "b.mp4"])

    async def test_other_tabs_are_told_the_library_changed(self):
        await self.three()
        await self.post_json("/h3_lvm/uploads/reorder", {"project": "show", "order": [2, 3, 1]})
        events = [payload for name, payload in EVENTS
                  if name == "h3_lvm/uploads_changed" and payload.get("action") == "reorder"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["scope"], "uploads")
        self.assertEqual(events[0]["project"], "show")

    async def test_a_half_order_is_refused(self):
        await self.three()
        response = await self.post_json("/h3_lvm/uploads/reorder", {"project": "show", "order": [2]})
        self.assertEqual(response.status, 400)
        self.assertIn("对不上", (await response.json())["error"])
        ids, _ = await self.listed()
        self.assertEqual(ids, [1, 2, 3])

    async def test_a_missing_order_is_refused(self):
        await self.three()
        response = await self.post_json("/h3_lvm/uploads/reorder", {"project": "show"})
        self.assertEqual(response.status, 400)
        self.assertIn("编号", (await response.json())["error"])

    async def test_reorder_needs_json(self):
        await self.three()
        response = await self.post_json("/h3_lvm/uploads/reorder",
                                        {"project": "show", "order": [2, 1, 3]},
                                        content_type="text/plain")
        self.assertEqual(response.status, 415)

    async def test_reorder_is_same_origin_only(self):
        await self.three()
        response = await self.post_json("/h3_lvm/uploads/reorder",
                                        {"project": "show", "order": [2, 1, 3]}, origin=False)
        self.assertEqual(response.status, 403)
        ids, _ = await self.listed()
        self.assertEqual(ids, [1, 2, 3])

    async def test_another_project_keeps_its_own_order(self):
        await self.three("show")
        await self.three("other")
        await self.post_json("/h3_lvm/uploads/reorder", {"project": "show", "order": [3, 2, 1]})
        _, names = await self.listed("other")
        self.assertEqual(names, ["a.mp4", "b.mp4", "c.mp4"])

class TestUploadOutputSize(ApiFixture):
    """The card must show the size the node will decode, not only the file's size."""

    async def cards(self, project="show", output_size=None, custom_max_side=None):
        path = "/h3_lvm/uploads?project=" + urllib.parse.quote(project)
        if output_size is not None:
            path += "&output_size=" + urllib.parse.quote(output_size)
        if custom_max_side is not None:
            path += "&custom_max_side=" + urllib.parse.quote(str(custom_max_side))
        response = await self.get(path)
        self.assertEqual(response.status, 200)
        return (await response.json())["videos"]

    async def one(self, size="64x36", project="show"):
        self.assertEqual((await self.upload(project, self.clip("a.mp4", size=size))).status, 200)
        return (await self.cards(project))[0]

    async def test_no_setting_leaves_the_source_size(self):
        await self.one()
        card = (await self.cards("show"))[0]
        self.assertEqual((card["out_width"], card["out_height"]), (64, 36))
        self.assertFalse(card["out_scaled"])

    async def test_a_cap_plans_the_size_the_node_will_decode(self):
        await self.one()
        card = (await self.cards("show", "最长边 32"))[0]
        self.assertEqual((card["out_width"], card["out_height"]), (32, 18))
        self.assertTrue(card["out_scaled"])

    async def test_the_stored_file_is_never_rescaled(self):
        card = await self.one()
        self.assertEqual((card["width"], card["height"]), (64, 36))
        stored = uvs.checked_upload_file("show", card["storage_name"])
        self.assertEqual(vd.probe_video(stored)["width"], 64)

    async def test_a_vertical_video_is_capped_on_its_long_edge(self):
        await self.one(size="36x64")
        card = (await self.cards("show", "最长边 32"))[0]
        self.assertEqual((card["out_width"], card["out_height"]), (18, 32))
        self.assertTrue(card["out_scaled"])

    async def test_a_cap_above_the_source_changes_nothing(self):
        await self.one()
        card = (await self.cards("show", "最长边 3840"))[0]
        self.assertEqual((card["out_width"], card["out_height"]), (64, 36))
        self.assertFalse(card["out_scaled"])

    async def test_an_unreadable_value_is_the_same_as_no_setting(self):
        await self.one()
        for value in ("", "nonsense", "最长边 4"):
            card = (await self.cards("show", value))[0]
            self.assertFalse(card["out_scaled"])

    async def test_a_typed_custom_size_plans_the_card(self):
        # 30 is not one of the presets, so this proves the card follows the typed number
        # rather than a second list the panel would have to keep in sync.
        await self.one()
        card = (await self.cards("show", vd.RESIZE_CUSTOM, 30))[0]
        self.assertEqual((card["out_width"], card["out_height"]), (30, 16))
        self.assertTrue(card["out_scaled"])

    async def test_a_custom_option_without_a_number_is_no_scaling(self):
        await self.one()
        for value in (None, "", "abc"):
            card = (await self.cards("show", vd.RESIZE_CUSTOM, value))[0]
            self.assertEqual((card["out_width"], card["out_height"]), (64, 36))
            self.assertFalse(card["out_scaled"])

    async def test_a_preset_option_ignores_the_typed_number(self):
        await self.one()
        card = (await self.cards("show", "最长边 32", 16))[0]
        self.assertEqual((card["out_width"], card["out_height"]), (32, 18))

    async def test_a_custom_number_outside_the_range_is_clamped(self):
        await self.one()
        card = (await self.cards("show", vd.RESIZE_CUSTOM, 99999))[0]
        self.assertFalse(card["out_scaled"])
        card = (await self.cards("show", vd.RESIZE_CUSTOM, 4))[0]
        # clamped up to the 16 px floor, and the height stays even
        self.assertEqual((card["out_width"], card["out_height"]), (16, 8))
        self.assertTrue(card["out_scaled"])
