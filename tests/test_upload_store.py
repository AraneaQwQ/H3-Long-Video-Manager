"""Tests for H3 Long Video Manager - uploaded_video_store (upload mode).

The library being tested is deliberately a second one: the cut bin keeps its own root, its
own index file, and its own ids. These tests are mostly about that separation, because a
user who names a project the same way in both places must get two independent libraries.

Run with:
    cd H3-Long-Video-Manager
    python -m tests.test_upload_store
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from tests._media_clip import (have_ffmpeg, make_audio_only, make_broken, make_clip,
                               make_gradient)
from tests._temp_dir import make_temp_dir

try:
    import av  # noqa: F401
    import numpy  # noqa: F401
    HAS_AV = True
except ImportError:
    HAS_AV = False

READY = have_ffmpeg() and HAS_AV

from comfyui import segment_store
from comfyui.uploaded_video_store import (ALLOWED_SUFFIXES, BIN_DIR_NAME, INDEX_NAME,
                                          MAX_SEGMENT_ID, checked_upload_file,
                                          count_uploads, create_upload_project, delete_upload,
                                          delete_upload_project, find_upload, get_base_dir,
                                          get_files_dir, import_upload, index_path,
                                          list_upload_projects, list_uploads,
                                          load_upload_index, open_partial, reorder_uploads,
                                          resolve_upload,
                                          safe_suffix, set_base_dir_override)


class StoreFixture(unittest.TestCase):
    """A temp upload root, plus a cut bin beside it for the separation checks."""

    @classmethod
    def setUpClass(cls):
        cls.parent = make_temp_dir(prefix="h3lvm_uploads_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.parent, ignore_errors=True)

    def setUp(self):
        # A fresh root per test: "the library is empty" is a claim worth testing.
        self.case = make_temp_dir(prefix="case_", parent=self.parent)
        self.root = os.path.join(self.case, "uploads")
        self.bin = os.path.join(self.case, "bin")
        set_base_dir_override(self.root)
        segment_store.set_base_dir_override(self.bin)

    def tearDown(self):
        set_base_dir_override(None)
        segment_store.set_base_dir_override(None)
        shutil.rmtree(self.case, ignore_errors=True)

    def video(self, name="clip.mp4", **kwargs):
        path = os.path.join(self.parent, name)
        return make_clip(path, fps=24, duration=1.0, **kwargs)

    def upload(self, project, source, original_name=None):
        _, partial = open_partial(project)
        shutil.copyfile(source, partial)
        return import_upload(project, partial, original_name or os.path.basename(source))


@unittest.skipUnless(READY, "needs PyAV and ffmpeg on PATH")
class TestTwoLibraries(StoreFixture):
    def test_the_upload_root_is_not_inside_the_cut_bin(self):
        self.assertEqual(BIN_DIR_NAME, "h3-lvm-video-uploads")
        self.assertNotEqual(BIN_DIR_NAME, segment_store.BIN_DIR_NAME)
        self.assertNotEqual(INDEX_NAME, segment_store.INDEX_NAME)
        set_base_dir_override(None)
        segment_store.set_base_dir_override(None)
        try:
            uploads, bins = get_base_dir(), segment_store.get_base_dir()
        finally:
            set_base_dir_override(self.root)
            segment_store.set_base_dir_override(self.bin)
        self.assertEqual(os.path.normcase(os.path.dirname(uploads)),
                         os.path.normcase(os.path.dirname(bins)),
                         "both libraries sit in the output directory")
        self.assertNotEqual(os.path.normcase(uploads), os.path.normcase(bins))
        self.assertFalse(os.path.normcase(uploads).startswith(os.path.normcase(bins) + os.sep),
                         "the upload library must not be a folder inside the cut bin")

    def test_same_project_name_means_two_different_folders(self):
        create_upload_project("story")
        self.assertTrue(os.path.isdir(get_base_dir()))
        self.assertEqual(os.path.normcase(index_path("story")),
                         os.path.normcase(os.path.join(self.root, "story", INDEX_NAME)))
        self.assertNotEqual(index_path("story"),
                            os.path.join(self.bin, "story", segment_store.INDEX_NAME))

    def test_a_project_in_one_library_is_invisible_in_the_other(self):
        self.upload("only-uploads", self.video())
        self.assertEqual([row["name"] for row in list_upload_projects()], ["only-uploads"])
        self.assertEqual([row["name"] for row in segment_store.list_projects()], [])
        segment_store.list_project("only-uploads")
        self.assertEqual(count_uploads("only-uploads"), 1)

    def test_deleting_an_upload_project_leaves_the_cut_bin_alone(self):
        self.upload("shared-name", self.video())
        segment_dir = os.path.join(self.bin, "shared-name")
        os.makedirs(segment_dir)
        with open(os.path.join(segment_dir, "keep.txt"), "w", encoding="utf-8") as stream:
            stream.write("not mine")
        result = delete_upload_project("shared-name", confirm="shared-name")
        self.assertTrue(result["deleted"])
        self.assertEqual(result["videos"], 1)
        self.assertFalse(os.path.isdir(os.path.join(self.root, "shared-name")))
        self.assertTrue(os.path.isfile(os.path.join(segment_dir, "keep.txt")))

    def test_deleting_needs_the_name_repeated(self):
        create_upload_project("careful")
        with self.assertRaises(ValueError):
            delete_upload_project("careful", confirm="carefu")
        self.assertTrue(os.path.isdir(os.path.join(self.root, "careful")))

    def test_deleting_cannot_escape_the_library(self):
        create_upload_project("one")
        with self.assertRaises(ValueError):
            delete_upload_project("..", confirm="..")


@unittest.skipUnless(READY, "needs PyAV and ffmpeg on PATH")
class TestImport(StoreFixture):
    def test_import_registers_one_card_with_facts(self):
        record = self.upload("show", self.video(audio=True))
        self.assertEqual(record["segment_id"], 1)
        self.assertEqual(record["storage_name"], "vid001.mp4")
        self.assertEqual(record["original_name"], "clip.mp4")
        self.assertEqual((record["width"], record["height"]), (64, 36))
        self.assertEqual(record["source_fps"], 24.0)
        self.assertEqual(record["out_fps"], 24)
        self.assertTrue(record["has_audio"])
        self.assertTrue(record["duration_sec"] > 0)
        self.assertTrue(os.path.isfile(os.path.join(get_files_dir("show"), "vid001.mp4")))
        self.assertTrue(os.path.isfile(os.path.join(get_files_dir("show"), "vid001_cover.jpg")))

    def test_the_numbers_are_the_card_order(self):
        # The number is the card's place in the deck, so it is always 1..N with no gap:
        # an import appends at the end and a delete moves the later cards up one.
        for _ in range(3):
            self.upload("ids", self.video())
        self.assertTrue(delete_upload("ids", 2))
        self.assertEqual([v["segment_id"] for v in list_uploads("ids")["videos"]], [1, 2])
        self.assertEqual(self.upload("ids", self.video())["segment_id"], 3)

    def test_the_same_file_name_twice_is_two_cards(self):
        source = self.video("dup.mp4")
        first = self.upload("dupes", source)
        second = self.upload("dupes", source)
        self.assertNotEqual(first["segment_id"], second["segment_id"])
        self.assertNotEqual(first["storage_name"], second["storage_name"])
        self.assertEqual(count_uploads("dupes"), 2)

    def test_a_non_video_never_becomes_a_card(self):
        broken = make_broken(os.path.join(self.parent, "notes.mp4"))
        with self.assertRaises(ValueError):
            self.upload("clean", broken)
        self.assertEqual(count_uploads("clean"), 0)
        self.assertEqual(os.listdir(get_files_dir("clean")), [])

    def test_an_audio_only_file_named_mp4_is_refused(self):
        # The extension is a lie here; the probe is what has to catch it.
        audio = make_audio_only(os.path.join(self.parent, "voice.mp4"))
        with self.assertRaises(ValueError) as caught:
            self.upload("clean2", audio)
        self.assertIn("没有视频流", str(caught.exception))
        self.assertEqual(count_uploads("clean2"), 0)

    def test_unsupported_extension_is_refused_before_writing(self):
        with self.assertRaises(ValueError):
            safe_suffix("clip.avi.bak")
        self.assertEqual(safe_suffix("Movie.MP4"), ".mp4")
        for suffix in (".mp4", ".mov", ".mkv", ".webm", ".avi"):
            self.assertIn(suffix, ALLOWED_SUFFIXES)

    def test_the_card_cap_says_what_to_do(self):
        # The cap is on how many cards one project holds. Fake cards keep the test fast;
        # the point is the count, not 999 real imports.
        create_upload_project("full")
        with open(index_path("full"), "r", encoding="utf-8") as stream:
            index = json.load(stream)
        index["videos"] = [{"segment_id": n, "storage_name": "vid%03d.mp4" % n}
                           for n in range(1, MAX_SEGMENT_ID + 1)]
        with open(index_path("full"), "w", encoding="utf-8") as stream:
            json.dump(index, stream)
        with self.assertRaises(ValueError) as caught:
            self.upload("full", self.video())
        self.assertIn("上限", str(caught.exception))
        self.assertEqual(count_uploads("full"), MAX_SEGMENT_ID)

    def test_the_storage_counter_never_caps_a_card(self):
        # next_id only names files, so a high one must not stop a first card.
        create_upload_project("names")
        with open(index_path("names"), "r", encoding="utf-8") as stream:
            index = json.load(stream)
        index["next_id"] = MAX_SEGMENT_ID + 7
        with open(index_path("names"), "w", encoding="utf-8") as stream:
            json.dump(index, stream)
        record = self.upload("names", self.video())
        self.assertEqual(record["segment_id"], 1)
        self.assertEqual(record["storage_name"], "vid%d.mp4" % (MAX_SEGMENT_ID + 7))

    def test_a_damaged_index_is_reported_not_hidden(self):
        create_upload_project("hurt")
        with open(index_path("hurt"), "w", encoding="utf-8") as stream:
            stream.write("{ not json")
        with self.assertRaises(ValueError) as caught:
            load_upload_index("hurt")
        self.assertIn(INDEX_NAME, str(caught.exception))
        self.assertEqual([row["videos"] for row in list_upload_projects()], [0],
                         "the menu still lists the other projects")


@unittest.skipUnless(READY, "needs PyAV and ffmpeg on PATH")
class TestReadPaths(StoreFixture):
    def test_listing_adds_playable_urls(self):
        self.upload("cards", self.video())
        cards = list_uploads("cards")["videos"]
        self.assertEqual(len(cards), 1)
        self.assertTrue(cards[0]["cover_url"].startswith("/view?"))
        self.assertTrue(cards[0]["video_url"].startswith("/view?"))
        self.assertTrue(cards[0]["browser_preview"])
        self.assertFalse(cards[0]["missing_file"])

    def test_a_file_deleted_outside_comfyui_is_shown_as_missing(self):
        record = self.upload("gone", self.video())
        os.remove(os.path.join(get_files_dir("gone"), record["storage_name"]))
        cards = list_uploads("gone")["videos"]
        self.assertTrue(cards[0]["missing_file"])
        self.assertEqual(cards[0]["video_url"], "")
        with self.assertRaises(ValueError) as caught:
            resolve_upload("gone", record["segment_id"])
        self.assertIn("已不在磁盘上", str(caught.exception))

    def test_resolve_names_the_project_and_the_id(self):
        create_upload_project("empty")
        with self.assertRaises(ValueError) as caught:
            resolve_upload("empty", 7)
        self.assertIn("empty", str(caught.exception))
        self.assertIn("7", str(caught.exception))

    def test_segment_id_must_be_a_positive_integer(self):
        for bad in (0, -1, "1", True, None):
            with self.assertRaises(ValueError):
                find_upload("any", bad)

    def test_storage_names_cannot_escape_the_files_folder(self):
        create_upload_project("safe")
        get_files_dir("safe")
        for bad in ("", "../outside.mp4", "sub/vid001.mp4", os.path.join(self.parent, "x.mp4")):
            with self.assertRaises(ValueError):
                checked_upload_file("safe", bad)
        self.assertEqual(os.path.basename(checked_upload_file("safe", "vid001.mp4")),
                         "vid001.mp4")

    def test_delete_removes_the_card_and_its_files(self):
        record = self.upload("bye", self.video())
        files_dir = get_files_dir("bye")
        self.assertTrue(delete_upload("bye", record["segment_id"]))
        self.assertFalse(os.path.exists(os.path.join(files_dir, record["storage_name"])))
        self.assertFalse(os.path.exists(os.path.join(files_dir, record["thumbnail"])))
        self.assertEqual(count_uploads("bye"), 0)
        self.assertFalse(delete_upload("bye", record["segment_id"]))

    def test_a_card_can_be_read_back_as_a_file(self):
        record = self.upload("use", self.video())
        path, found = resolve_upload("use", record["segment_id"])
        self.assertEqual(found["segment_id"], record["segment_id"])
        self.assertTrue(os.path.isfile(path))

    def test_listing_never_creates_a_folder(self):
        self.assertEqual(list_upload_projects(), [])
        self.assertFalse(os.path.isdir(os.path.join(self.root, "ghost")))
        self.assertEqual(count_uploads("ghost"), 0)


@unittest.skipUnless(READY, "needs PyAV and ffmpeg on PATH")
class TestProjectNames(StoreFixture):
    def test_a_name_needs_something_readable(self):
        for bad in ("", "   ", "...", "///"):
            with self.assertRaises(ValueError):
                create_upload_project(bad)

    def test_path_separators_are_cleaned(self):
        created = create_upload_project("a/b:c")
        self.assertEqual(created["name"], "a_b_c")
        self.assertTrue(os.path.isfile(index_path("a_b_c")))

    def test_creating_twice_selects_the_same_project(self):
        first = create_upload_project("twice")
        second = create_upload_project("twice")
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(second["name"], first["name"])

    def test_a_new_project_is_listed_so_the_menu_can_show_it(self):
        create_upload_project("fresh")
        self.assertEqual([row["name"] for row in list_upload_projects()], ["fresh"])
        self.assertEqual(list_upload_projects()[0]["videos"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
@unittest.skipUnless(READY, "needs PyAV and ffmpeg on PATH")
class TestCardOrder(StoreFixture):
    """Dragging cards in the panel: the order becomes the numbering, the bytes stay put."""

    def three(self, project="story"):
        for name in ("a.mp4", "b.mp4", "c.mp4"):
            self.upload(project, self.video(name), original_name=name)

    def listed(self, project="story"):
        return [v["segment_id"] for v in list_uploads(project)["videos"]]

    def names(self, project="story"):
        return [v["original_name"] for v in list_uploads(project)["videos"]]

    def test_the_new_order_becomes_the_numbering(self):
        self.three()
        result = reorder_uploads("story", [3, 1, 2])
        self.assertEqual(result["order"], [1, 2, 3])
        self.assertEqual(result["videos"], 3)
        self.assertEqual(self.listed(), [1, 2, 3])
        self.assertEqual(self.names(), ["c.mp4", "a.mp4", "b.mp4"])

    def test_no_file_is_moved_or_renamed(self):
        self.three()
        files_dir = get_files_dir("story")
        before = sorted(os.listdir(files_dir))
        reorder_uploads("story", [3, 2, 1])
        self.assertEqual(sorted(os.listdir(files_dir)), before)
        record = find_upload("story", 1)
        self.assertEqual(record["original_name"], "c.mp4")
        path, _ = resolve_upload("story", 1)
        self.assertEqual(os.path.basename(path), record["storage_name"])
        self.assertTrue(os.path.isfile(path))

    def test_the_node_reads_the_card_its_number_now_points_at(self):
        self.three()
        reorder_uploads("story", [2, 3, 1])
        _, record = resolve_upload("story", 1)
        self.assertEqual(record["original_name"], "b.mp4")
        _, record = resolve_upload("story", 3)
        self.assertEqual(record["original_name"], "a.mp4")

    def test_a_partial_order_is_refused_and_changes_nothing(self):
        self.three()
        with self.assertRaises(ValueError) as caught:
            reorder_uploads("story", [3, 1])
        self.assertIn("对不上", str(caught.exception))
        self.assertEqual(self.listed(), [1, 2, 3])

    def test_an_id_that_is_not_in_the_library_is_refused(self):
        self.three()
        with self.assertRaises(ValueError):
            reorder_uploads("story", [3, 1, 4])

    def test_a_repeated_id_is_refused(self):
        self.three()
        with self.assertRaises(ValueError) as caught:
            reorder_uploads("story", [1, 1, 2])
        self.assertIn("重复", str(caught.exception))

    def test_an_order_that_is_not_a_list_of_ids_is_refused(self):
        self.three()
        for value in (None, "123", {"order": [1]}, [0], [True], ["2", "1", "3"]):
            with self.assertRaises(ValueError):
                reorder_uploads("story", value)
        self.assertEqual(self.listed(), [1, 2, 3])

    def test_the_same_order_writes_nothing(self):
        self.three()
        with open(index_path("story"), "r", encoding="utf-8") as stream:
            before = stream.read()
        result = reorder_uploads("story", [1, 2, 3])
        self.assertEqual(result["videos"], 3)
        with open(index_path("story"), "r", encoding="utf-8") as stream:
            self.assertEqual(stream.read(), before)

    def test_the_next_upload_still_gets_a_free_number(self):
        self.three()
        reorder_uploads("story", [3, 2, 1])
        record = self.upload("story", self.video("d.mp4"), original_name="d.mp4")
        self.assertEqual(record["segment_id"], 4)
        self.assertEqual(self.names(), ["c.mp4", "b.mp4", "a.mp4", "d.mp4"])

    def test_a_delete_already_closes_the_gap(self):
        self.three()
        self.assertTrue(delete_upload("story", 2))
        self.assertEqual(self.listed(), [1, 2])
        self.assertEqual(self.names(), ["a.mp4", "c.mp4"])
        reorder_uploads("story", [2, 1])
        self.assertEqual(self.listed(), [1, 2])
        self.assertEqual(self.names(), ["c.mp4", "a.mp4"])

    def test_a_delete_moves_the_later_cards_up(self):
        self.three()
        self.assertTrue(delete_upload("story", 1))
        self.assertEqual(self.listed(), [1, 2])
        self.assertEqual(self.names(), ["b.mp4", "c.mp4"])
        # The node reads the number it has, so the number has to reach the right video.
        _, record = resolve_upload("story", 1)
        self.assertEqual(record["original_name"], "b.mp4")

    def test_closing_a_gap_never_reuses_a_file_name(self):
        # ids 1,2,3 minus card 1 leaves the old vid003 sitting at number 2; a new import
        # must not be handed the number 3 file name and overwrite it.
        self.three()
        self.assertTrue(delete_upload("story", 1))
        moved = find_upload("story", 2)
        self.assertEqual((moved["original_name"], moved["storage_name"]),
                         ("c.mp4", "vid003.mp4"))
        added = self.upload("story", self.video("d.mp4"), original_name="d.mp4")
        self.assertEqual((added["segment_id"], added["storage_name"]), (3, "vid004.mp4"))
        self.assertEqual(self.names(), ["b.mp4", "c.mp4", "d.mp4"])
        for name in ("vid003.mp4", "vid004.mp4"):
            self.assertTrue(os.path.isfile(os.path.join(get_files_dir("story"), name)))

    def test_an_empty_library_starts_at_one_again(self):
        # The reported case: one card, delete it, the next upload is 视频 1 again.
        first = self.upload("story", self.video("a.mp4"), original_name="a.mp4")
        self.assertTrue(delete_upload("story", first["segment_id"]))
        second = self.upload("story", self.video("b.mp4"), original_name="b.mp4")
        self.assertEqual(second["segment_id"], 1)
        self.assertEqual(self.names(), ["b.mp4"])
        self.assertEqual(second["storage_name"], "vid002.mp4")

    def test_a_hand_shuffled_index_still_lists_in_number_order(self):
        self.three()
        with open(index_path("story"), "r", encoding="utf-8") as stream:
            idx = json.load(stream)
        idx["videos"] = list(reversed(idx["videos"]))
        with open(index_path("story"), "w", encoding="utf-8") as stream:
            json.dump(idx, stream, ensure_ascii=False)
        self.assertEqual(self.listed(), [1, 2, 3])

    def test_an_index_with_a_card_that_has_no_number_is_refused(self):
        self.three()
        with open(index_path("story"), "r", encoding="utf-8") as stream:
            idx = json.load(stream)
        del idx["videos"][1]["segment_id"]
        with open(index_path("story"), "w", encoding="utf-8") as stream:
            json.dump(idx, stream, ensure_ascii=False)
        with self.assertRaises(ValueError) as caught:
            reorder_uploads("story", [1, 2, 3])
        self.assertIn("没有有效编号", str(caught.exception))

    def test_reordering_never_touches_the_cut_bin(self):
        self.three()
        reorder_uploads("story", [3, 1, 2])
        self.assertFalse(os.path.isdir(os.path.join(self.bin, "story")))
        self.assertEqual([s.get("segment_id")
                          for s in segment_store.list_project("story").get("segments", [])], [])
