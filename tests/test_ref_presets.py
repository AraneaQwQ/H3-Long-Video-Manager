"""Reference libraries: one per kind, image and audio, each with its own bins.

A preset is only worth having if it is cheap (paths, never a copy of the media) and
still usable when the file is half-written or points at files that have moved. It is
also only worth having if the audio loader never offers the image loader's projects:
a bin named for a story says which character sheets belong to it, not which voice
clips do. So each kind has its own library root, its own project list, and its own
one-list file. These tests drive that real JSON against a throwaway output folder,
including the one-time copy out of the shared file the split replaced.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import tempfile
import types
import unittest

# Ensure plugin root is importable
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)


def _plugin_module(name: str):
    """Import a plugin module the way ComfyUI does, i.e. as h3lvm.*.

    ref_presets lives in the comfyui package and reaches the pure layer with a
    relative import, which only resolves inside that package. The synthetic package
    here keeps this file independent of comfy_api and torch; when the node tests
    already loaded the real package, their module is reused so the base-dir
    override is shared rather than duplicated.
    """
    if "h3lvm" not in sys.modules:
        package = types.ModuleType("h3lvm")
        package.__path__ = [REPO]
        sys.modules["h3lvm"] = package
    return importlib.import_module("h3lvm." + name)


ref_presets = _plugin_module("comfyui.ref_presets")
segment_store = _plugin_module("comfyui.segment_store")
ref_media = _plugin_module("core.ref_media")

IMAGE = "image"
AUDIO = "audio"
KIND_ROOTS = ref_presets.KIND_ROOTS
LIST_KEY = ref_presets.LIST_KEY
PRESET_NAME = ref_presets.PRESET_NAME
count_references = ref_presets.count_references
create_reference_project = ref_presets.create_reference_project
delete_reference_project = ref_presets.delete_reference_project
library_dir = ref_presets.library_dir
list_reference_projects = ref_presets.list_reference_projects
load_references = ref_presets.load_references
preset_path = ref_presets.preset_path
ref_project_dir = ref_presets.ref_project_dir
save_references = ref_presets.save_references
DEFAULT_PROJECT = segment_store.DEFAULT_PROJECT
create_project = segment_store.create_project
get_project_dir = segment_store.get_project_dir
set_base_dir_override = segment_store.set_base_dir_override
MAX_REF_AUDIOS = ref_media.MAX_REF_AUDIOS
MAX_REF_IMAGES = ref_media.MAX_REF_IMAGES


def entries_for(*names):
    return [{"filename": name, "subfolder": "", "type": "input"} for name in names]


def card_names(preset):
    return [item["filename"] for item in preset[LIST_KEY]]


class LibraryFixture(unittest.TestCase):
    """A throwaway output folder; nothing here touches the real media folders."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="h3lvm_refs_")
        set_base_dir_override(self._tmpdir)

    def tearDown(self):
        set_base_dir_override(None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def raw(self, kind=IMAGE, project="P"):
        with open(preset_path(kind, project), "r", encoding="utf-8") as stream:
            return json.load(stream)

    def write_raw(self, text, kind=IMAGE, project="P"):
        os.makedirs(os.path.dirname(preset_path(kind, project)), exist_ok=True)
        with open(preset_path(kind, project), "w", encoding="utf-8") as stream:
            stream.write(text)

    def write_legacy(self, payload, project="P"):
        """Write the shared pre-split file, i.e. the one inside the video bin."""
        bin_dir = get_project_dir(project, create=False)
        os.makedirs(bin_dir, exist_ok=True)
        path = os.path.join(bin_dir, PRESET_NAME)
        with open(path, "w", encoding="utf-8") as stream:
            if isinstance(payload, str):
                stream.write(payload)
            else:
                json.dump(payload, stream, ensure_ascii=False)
        return path


class TestPresetRoundTrip(LibraryFixture):
    def test_a_saved_preset_loads_back_in_card_order(self):
        result = save_references(IMAGE, "科幻短片", entries_for("b.png", "a.png"))
        self.assertEqual(result["name"], "科幻短片")
        self.assertEqual(result["kind"], "image")
        self.assertEqual(result["saved"], 2)
        self.assertEqual(card_names(load_references(IMAGE, "科幻短片")), ["b.png", "a.png"])

    def test_a_preset_is_paths_only_and_costs_one_small_file(self):
        save_references(IMAGE, "P", entries_for("a.png"))
        self.assertEqual(sorted(os.listdir(library_dir(IMAGE))), ["P"])
        self.assertEqual(
            sorted(os.listdir(ref_project_dir(IMAGE, "P", create=False))), [PRESET_NAME],
            "no media copy and no leftover temp file may sit in the bin")
        raw = json.dumps(self.raw(), ensure_ascii=False)
        self.assertLess(len(raw.encode("utf-8")), 400, "a preset is a path list, not the media")
        self.assertEqual(sorted(self.raw()[LIST_KEY][0].keys()),
                         ["filename", "subfolder", "type"])
        self.assertEqual(set(self.raw().keys()), {LIST_KEY, "project_name"},
                         "one list per file: the other kind has its own library")

    def test_a_preset_is_not_filed_inside_the_video_bin(self):
        # Reference media and cut segments are different material, and a user who
        # deletes a video bin must not lose the reference presets named after it.
        create_project("P")
        save_references(IMAGE, "P", entries_for("a.png"))
        self.assertNotIn(PRESET_NAME, os.listdir(get_project_dir("P", create=False)),
                         "the reference library is a sibling of the video bin")

    def test_saving_one_kind_never_rewrites_the_other_library(self):
        save_references(IMAGE, "P", entries_for("a.png"))
        save_references(AUDIO, "P", entries_for("voice.mp3"))
        before = self.raw(AUDIO)
        save_references(IMAGE, "P", entries_for("c.png", "d.png"))
        self.assertEqual(self.raw(AUDIO), before, "the audio file is not touched")
        self.assertEqual(card_names(self.raw(IMAGE)), ["c.png", "d.png"])
        self.assertEqual(card_names(load_references(AUDIO, "P")), ["voice.mp3"])

    def test_parked_cards_survive_a_preset(self):
        entries = entries_for("a.png", "b.png")
        entries[1]["skip"] = True
        self.assertEqual(save_references(IMAGE, "P", entries)["saved"], 2)
        loaded = load_references(IMAGE, "P")
        self.assertEqual(card_names(loaded), ["a.png", "b.png"])
        self.assertIs(loaded[LIST_KEY][1].get("skip"), True,
                      "a preset restores the arrangement, not just the files")

    def test_the_file_itself_carries_the_arrangement(self):
        # The panel restores its cards from what load_references() returns, but the
        # guarantee that matters is on disk: the order and the skip flags are in the
        # file, so a restart of ComfyUI cannot turn an arrangement back into a dump
        # of paths.
        entries = entries_for("a.png", "b.png", "c.png")
        entries[1]["skip"] = True
        save_references(IMAGE, "P", entries)
        stored = self.raw()[LIST_KEY]
        self.assertEqual([item["filename"] for item in stored], ["a.png", "b.png", "c.png"])
        self.assertIs(stored[1].get("skip"), True)
        self.assertNotIn("skip", stored[0], "an active card stays byte-identical to the old format")

    def test_an_audio_window_survives_a_preset(self):
        # The trim window lives on the entry, so saving a preset saves the cut too:
        # recalling one must not quietly hand H3 the whole file again.
        save_references(AUDIO, "P", json.dumps([
            {"filename": "a.wav", "subfolder": "", "type": "input", "start": 1.5, "duration": 2},
        ]))
        self.assertEqual(self.raw(AUDIO)[LIST_KEY][0]["start"], 1.5, "the window is in the file")
        loaded = load_references(AUDIO, "P")
        self.assertEqual((loaded[LIST_KEY][0]["start"], loaded[LIST_KEY][0]["duration"]), (1.5, 2.0))

    def test_the_panel_json_is_accepted_as_is(self):
        # The panel posts serializeMedia() output, i.e. a JSON string, not a list, and
        # a subfolder may live in either half of the path - both are inside the bin.
        save_references(IMAGE, "P", json.dumps([
            {"filename": "a.png", "subfolder": "", "type": "input"},
            {"filename": "sub/b.jpg", "subfolder": "", "type": "input"},
            {"filename": "c.png", "subfolder": "sub", "type": "OUTPUT"},
        ]))
        loaded = load_references(IMAGE, "P")[LIST_KEY]
        self.assertEqual(loaded[1]["filename"], "sub/b.jpg")
        self.assertEqual(loaded[2]["subfolder"], "sub")
        self.assertEqual(loaded[2]["type"], "output", "the type is kept, only lower-cased")


class TestKindLimitsAndErrors(LibraryFixture):
    def test_each_kind_is_limited_to_its_own_slots(self):
        many = entries_for(*["i%d.png" % index for index in range(MAX_REF_IMAGES + 4)])
        self.assertEqual(save_references(IMAGE, "P", many)["saved"], MAX_REF_IMAGES)
        self.assertEqual(len(load_references(IMAGE, "P")[LIST_KEY]), MAX_REF_IMAGES)
        audio = entries_for(*["a%d.mp3" % index for index in range(MAX_REF_AUDIOS + 2)])
        self.assertEqual(save_references(AUDIO, "P", audio)["saved"], MAX_REF_AUDIOS)
        self.assertEqual(len(load_references(AUDIO, "P")[LIST_KEY]), MAX_REF_AUDIOS)

    def test_parked_entries_do_not_eat_the_slot_limit(self):
        entries = entries_for(*["i%d.png" % index for index in range(MAX_REF_IMAGES)])
        entries += [dict(item, skip=True) for item in
                    entries_for("extra1.png", "extra2.png")]
        self.assertEqual(save_references(IMAGE, "P", entries)["saved"], len(entries))
        self.assertEqual(len(load_references(IMAGE, "P")[LIST_KEY]), len(entries))

    def test_unknown_kind_is_refused_everywhere(self):
        for bad in ("video", "", None, 3, "IMAGE"):
            for call in (
                lambda: save_references(bad, "P", entries_for("a.png")),
                lambda: load_references(bad, "P"),
                lambda: count_references(bad, "P"),
                lambda: list_reference_projects(bad),
                lambda: create_reference_project(bad, "P"),
                lambda: delete_reference_project(bad, "P", "P"),
                lambda: library_dir(bad),
            ):
                with self.assertRaises(ValueError):
                    call()
        for kind in KIND_ROOTS:
            self.assertFalse(os.path.isdir(library_dir(kind)), "a refused kind creates no library")

    def test_unusable_entries_are_refused_rather_than_half_saved(self):
        with self.assertRaises(ValueError) as ctx:
            save_references(IMAGE, "P", entries_for("/abs/a.png"))
        self.assertIn("预设内容无法保存", str(ctx.exception))
        self.assertFalse(os.path.isfile(preset_path(IMAGE, "P")),
                         "a rejected save must not touch the bin")

    def test_a_missing_preset_reads_as_empty_without_creating_a_bin(self):
        loaded = load_references(IMAGE, "never-used")
        self.assertEqual(loaded["project_name"], "never-used")
        self.assertEqual(loaded[LIST_KEY], [])
        self.assertFalse(os.path.exists(preset_path(IMAGE, "never-used")))

    def test_a_broken_preset_reads_as_empty_and_the_next_save_fixes_it(self):
        self.write_raw("{ this is not json")
        self.assertEqual(load_references(IMAGE, "P")[LIST_KEY], [])
        save_references(IMAGE, "P", entries_for("a.png"))
        self.assertEqual(len(load_references(IMAGE, "P")[LIST_KEY]), 1)

    def test_the_old_two_list_shape_is_not_read(self):
        # Both kinds in one file is exactly the shape this split removed. Reading it
        # back would put image cards in the audio loader, so it stays unread; the
        # migration only ever copies from the shared pre-split file.
        self.write_raw(json.dumps({
            "project_name": "P",
            "images": [{"filename": "a.png", "subfolder": "", "type": "input"}],
            "audios": [{"filename": "v.mp3", "subfolder": "", "type": "input"}],
        }))
        self.assertEqual(load_references(IMAGE, "P")[LIST_KEY], [])
        self.assertEqual(count_references(AUDIO, "P"), 0)

    def test_a_preset_written_as_a_list_is_ignored_not_fatal(self):
        self.write_raw('["a.png"]')
        self.assertEqual(load_references(IMAGE, "P"), {"project_name": "P", LIST_KEY: []})

    def test_project_names_are_sanitised_into_one_bin(self):
        save_references(IMAGE, "a/b", entries_for("a.png"))
        self.assertEqual(card_names(load_references(IMAGE, "a_b")), ["a.png"])
        self.assertEqual(load_references(IMAGE, "")["project_name"], DEFAULT_PROJECT)
        self.assertEqual(load_references(IMAGE, None)["project_name"], DEFAULT_PROJECT)
        self.assertEqual(os.path.dirname(os.path.dirname(preset_path(IMAGE, ""))),
                         library_dir(IMAGE), "even the default bin stays in the image library")


class TestLibrarySplit(LibraryFixture):
    """The point of the split: two loaders, two libraries, never one shared list."""

    def test_each_kind_has_its_own_root_and_project_list(self):
        save_references(IMAGE, "story", entries_for("a.png"))
        save_references(AUDIO, "story", entries_for("v.mp3"))
        self.assertEqual(sorted(os.listdir(self._tmpdir)), sorted(KIND_ROOTS.values()),
                         "the two libraries sit beside the video bins, not inside them")
        self.assertEqual([row["name"] for row in list_reference_projects(IMAGE)], ["story"])
        self.assertEqual([row["name"] for row in list_reference_projects(AUDIO)], ["story"])
        self.assertNotEqual(preset_path(IMAGE, "story"), preset_path(AUDIO, "story"))

    def test_a_project_in_one_library_is_invisible_in_the_other(self):
        save_references(IMAGE, "images-only", entries_for("a.png"))
        self.assertEqual([row["name"] for row in list_reference_projects(AUDIO)], [])
        self.assertEqual(load_references(AUDIO, "images-only")[LIST_KEY], [])
        save_references(AUDIO, "voices-only", entries_for("v.mp3"))
        self.assertEqual([row["name"] for row in list_reference_projects(IMAGE)], ["images-only"])

    def test_creating_a_project_only_touches_one_library(self):
        created = create_reference_project(AUDIO, "P")
        self.assertEqual((created["name"], created["created"], created[LIST_KEY]), ("P", True, 0))
        self.assertTrue(os.path.isfile(preset_path(AUDIO, "P")))
        self.assertFalse(os.path.isdir(ref_project_dir(IMAGE, "P", create=False)),
                         "the image library must not grow a bin from an audio request")
        self.assertEqual(create_reference_project(AUDIO, "P")["created"], False)

    def test_deleting_a_project_only_touches_one_library(self):
        save_references(IMAGE, "P", entries_for("a.png"))
        save_references(AUDIO, "P", entries_for("v.mp3"))
        create_project("P")
        result = delete_reference_project(AUDIO, "P", "P")
        self.assertEqual((result["deleted"], result[LIST_KEY]), (True, 1))
        self.assertFalse(os.path.isdir(ref_project_dir(AUDIO, "P", create=False)))
        self.assertEqual(card_names(load_references(IMAGE, "P")), ["a.png"],
                         "the image preset of the same story stays")
        self.assertTrue(os.path.isdir(get_project_dir("P", create=False)),
                        "the video bin is a different folder")
        self.assertEqual(delete_reference_project(AUDIO, "P", "P")["deleted"], False)

    def test_delete_requires_the_exact_name(self):
        create_reference_project(IMAGE, "P")
        for wrong in ("", "p", None, "Q"):
            with self.assertRaises(ValueError):
                delete_reference_project(IMAGE, "P", wrong)
        self.assertTrue(os.path.isfile(preset_path(IMAGE, "P")))

    def test_the_shared_pre_split_file_is_copied_into_both_libraries(self):
        legacy = self.write_legacy({
            "project_name": "P",
            "images": entries_for("a.png", "b.png"),
            "audios": entries_for("v.mp3"),
        })
        self.assertEqual(card_names(load_references(IMAGE, "P")), ["a.png", "b.png"])
        self.assertEqual(card_names(load_references(AUDIO, "P")), ["v.mp3"])
        self.assertEqual([row["name"] for row in list_reference_projects(IMAGE)], ["P"])
        self.assertEqual([row["name"] for row in list_reference_projects(AUDIO)], ["P"])
        self.assertEqual(set(self.raw(AUDIO).keys()), {LIST_KEY, "project_name"},
                         "the copy is written in the new one-list shape")
        self.assertTrue(os.path.isfile(legacy), "the user's old file is left alone")

    def test_a_migrated_library_is_the_source_of_truth_afterwards(self):
        # The copy happens once. Re-reading the shared file after the user has edited
        # their preset would undo that edit, so the library wins from then on.
        self.write_legacy({"project_name": "P", "images": entries_for("old.png")})
        self.assertEqual(card_names(load_references(IMAGE, "P")), ["old.png"])
        self.write_legacy({"project_name": "P", "images": entries_for("other.png")})
        self.assertEqual(card_names(load_references(IMAGE, "P")), ["old.png"])
        save_references(IMAGE, "P", entries_for("new.png"))
        self.assertEqual(card_names(load_references(IMAGE, "P")), ["new.png"])

    def test_an_empty_or_broken_legacy_file_creates_no_bins(self):
        self.write_legacy({"project_name": "P", "images": [], "audios": []})
        self.assertEqual(load_references(IMAGE, "P")[LIST_KEY], [])
        self.assertEqual(load_references(AUDIO, "P")[LIST_KEY], [])
        self.write_legacy("{ not json", project="Q")
        self.assertEqual(load_references(IMAGE, "Q")[LIST_KEY], [])
        self.write_legacy({"images": [{"filename": "../outside.png"}]}, project="R")
        self.assertEqual(load_references(IMAGE, "R")[LIST_KEY], [])
        for kind in KIND_ROOTS:
            self.assertFalse(os.path.isdir(library_dir(kind)),
                             "a preset the user never saved must not appear as a bin")


class TestProjectMenuCounts(LibraryFixture):
    """The number beside a bin name in the loader's project menu.

    A loader can only read its own kind, so its menu counts its own library; a bin
    full of presets must never read （空）.
    """

    def test_a_preset_counts_its_own_kind(self):
        create_reference_project(IMAGE, "P")
        self.assertEqual(count_references(IMAGE, "P"), 0, "a bin with no preset has no cards")
        save_references(IMAGE, "P", entries_for("b.png", "a.png"))
        save_references(AUDIO, "P", entries_for("v.mp3"))
        self.assertEqual(count_references(IMAGE, "P"), 2, "images only, not the audio cards")
        self.assertEqual(count_references(AUDIO, "P"), 1)

    def test_a_broken_preset_counts_as_zero(self):
        self.write_raw("{ this is not json")
        self.assertEqual(count_references(IMAGE, "P"), 0)

    def test_counting_does_not_create_a_bin(self):
        self.assertEqual(count_references(IMAGE, "never-used"), 0)
        self.assertFalse(os.path.isdir(ref_project_dir(IMAGE, "never-used", create=False)))

    def test_the_projects_reply_carries_the_card_count(self):
        create_reference_project(IMAGE, "empty")
        create_reference_project(IMAGE, "refs")
        save_references(IMAGE, "refs", entries_for("a.png"))
        rows = {row["name"]: row for row in list_reference_projects(IMAGE)}
        self.assertEqual(rows["refs"][LIST_KEY], 1)
        self.assertEqual(rows["empty"][LIST_KEY], 0, "an empty bin is still a valid bin")
        self.assertNotIn("segments", rows["refs"],
                         "the reference menu has no business reporting segment counts")


if __name__ == "__main__":
    unittest.main()
