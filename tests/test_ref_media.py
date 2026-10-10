"""Media list parsing, path safety, slot filling and cache keys for the loaders."""

import json
import os
import shutil
import tempfile
import unittest

from core.ref_media import (
    MAX_REF_AUDIOS, MAX_REF_IMAGES, active_entries, fill_slots, is_skipped,
    media_fingerprint, media_kind, parse_media_list, resolve_media_path, split_entries,
    trim_range,
)

TMP_ROOT = None


def setUpModule():
    global TMP_ROOT
    TMP_ROOT = tempfile.mkdtemp(prefix="h3lvm_ref_media_")


def tearDownModule():
    if TMP_ROOT:
        shutil.rmtree(TMP_ROOT, ignore_errors=True)


def write_file(name: str, content: str) -> str:
    path = os.path.join(TMP_ROOT, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


class TestParseMediaList(unittest.TestCase):
    def test_empty_input_is_an_empty_list(self):
        for raw in (None, "", "   ", "[]", []):
            self.assertEqual(parse_media_list(raw), [])

    def test_panel_json_is_kept_in_order(self):
        raw = json.dumps([
            {"filename": "b.png", "subfolder": "", "type": "input"},
            {"filename": "a.png", "subfolder": "sub", "type": "input"},
        ])
        self.assertEqual(parse_media_list(raw), [
            {"filename": "b.png", "subfolder": "", "type": "input"},
            {"filename": "a.png", "subfolder": "sub", "type": "input"},
        ])

    def test_plain_names_are_accepted_for_hand_written_api_prompts(self):
        self.assertEqual(parse_media_list(["one.png", "two.png"], MAX_REF_IMAGES), [
            {"filename": "one.png", "subfolder": "", "type": "input"},
            {"filename": "two.png", "subfolder": "", "type": "input"},
        ])

    def test_missing_subfolder_and_type_get_safe_defaults(self):
        self.assertEqual(parse_media_list('[{"filename": "x.png"}]'),
                         [{"filename": "x.png", "subfolder": "", "type": "input"}])

    def test_more_items_than_slots_keeps_the_first_ones(self):
        raw = [f"pic{i}.png" for i in range(MAX_REF_IMAGES + 4)]
        entries = parse_media_list(raw, MAX_REF_IMAGES)
        self.assertEqual(len(entries), MAX_REF_IMAGES)
        self.assertEqual(entries[0]["filename"], "pic0.png")
        self.assertEqual(entries[-1]["filename"], f"pic{MAX_REF_IMAGES - 1}.png")

    def test_parked_entries_stay_in_the_list_but_hold_no_slot(self):
        raw = json.dumps([
            {"filename": "a.png", "subfolder": "", "type": "input"},
            {"filename": "b.png", "subfolder": "", "type": "input", "skip": True},
            {"filename": "c.png", "subfolder": "", "type": "input"},
        ])
        entries = parse_media_list(raw, MAX_REF_IMAGES)
        self.assertEqual([entry["filename"] for entry in entries], ["a.png", "b.png", "c.png"])
        self.assertTrue(is_skipped(entries[1]))
        self.assertFalse(is_skipped(entries[0]))
        self.assertEqual(active_entries(entries), [entries[0], entries[2]])
        self.assertEqual(split_entries(entries)[1], [entries[1]])

    def test_an_active_entry_carries_no_skip_key(self):
        # Lists saved before this feature parse exactly as they always did.
        self.assertEqual(parse_media_list('[{"filename": "a.png", "skip": false}]'),
                         [{"filename": "a.png", "subfolder": "", "type": "input"}])

    def test_parked_entries_do_not_eat_the_slot_limit(self):
        active = [{"filename": f"pic{i}.png"} for i in range(MAX_REF_IMAGES)]
        parked = [{"filename": f"park{i}.png", "skip": True} for i in range(3)]
        entries = parse_media_list(json.dumps(active + parked), MAX_REF_IMAGES)
        self.assertEqual(len(active_entries(entries)), MAX_REF_IMAGES)
        self.assertEqual(len(split_entries(entries)[1]), 3)

    def test_only_active_entries_are_truncated(self):
        items = [{"filename": f"pic{i}.png"} for i in range(MAX_REF_IMAGES + 3)]
        items.insert(2, {"filename": "parked.png", "skip": True})
        entries = parse_media_list(json.dumps(items), MAX_REF_IMAGES)
        self.assertEqual(len(active_entries(entries)), MAX_REF_IMAGES)
        self.assertEqual([entry["filename"] for entry in split_entries(entries)[1]], ["parked.png"])
        self.assertEqual(active_entries(entries)[1]["filename"], "pic1.png")

    def test_bad_json_says_where_it_broke(self):
        with self.assertRaises(ValueError) as ctx:
            parse_media_list('[{"filename": "a.png"')
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_unusable_shapes_are_rejected_rather_than_dropped(self):
        for raw in ('{"filename": "a.png"}', "5", '[null]', '[3]', '[{"nope": 1}]'):
            with self.assertRaises(ValueError):
                parse_media_list(raw)

    def test_paths_must_stay_inside_the_media_folder(self):
        for name in ("/abs.png", "C:\\media\\a.png", "../out.png", "a/../../b.png", "", "   ", ".hidden.png"):
            with self.assertRaises(ValueError):
                parse_media_list(json.dumps([{"filename": name}]))

    def test_unknown_media_type_is_an_error(self):
        with self.assertRaises(ValueError):
            parse_media_list('[{"filename": "a.png", "type": "models"}]')

    def test_output_and_temp_folders_are_allowed(self):
        entries = parse_media_list('[{"filename": "a.png", "type": "OUTPUT"}]')
        self.assertEqual(entries[0]["type"], "output")


class TestTrimFields(unittest.TestCase):
    """A card window is seconds, and only audio cards have one."""

    def test_media_kind_is_decided_by_the_extension(self):
        self.assertEqual(media_kind("a.wav"), "audio")
        self.assertEqual(media_kind("dir/B.MP3"), "audio")
        self.assertEqual(media_kind("a.png"), "image")
        self.assertEqual(media_kind("a.txt"), "other")
        self.assertEqual(media_kind(None), "other")

    def test_only_audio_entries_keep_a_window(self):
        entries = parse_media_list(json.dumps([
            {"filename": "a.wav", "start": 1.5, "duration": 2},
            {"filename": "a.png", "start": 1.5, "duration": 2},
            {"filename": "b.wav", "start": 0, "duration": 0},
        ]))
        self.assertEqual(entries[0]["start"], 1.5)
        self.assertEqual(entries[0]["duration"], 2.0)
        self.assertNotIn("start", entries[1], "a stray start key on an image is not a window")
        self.assertNotIn("duration", entries[2], "zero means the whole file, so it is not written")

    def test_a_list_of_names_still_parses_without_any_window(self):
        self.assertEqual(
            parse_media_list('["a.wav"]'),
            [{"filename": "a.wav", "subfolder": "", "type": "input"}],
        )

    def test_a_number_written_as_text_is_still_seconds(self):
        entries = parse_media_list(json.dumps([{"filename": "a.wav", "start": "1.5", "duration": "2"}]))
        self.assertEqual((entries[0]["start"], entries[0]["duration"]), (1.5, 2.0))

    def test_a_negative_start_is_kept_as_written(self):
        entries = parse_media_list(json.dumps([{"filename": "a.wav", "start": -2}]))
        self.assertEqual(entries[0]["start"], -2.0)

    def test_impossible_numbers_are_rejected(self):
        for item in (
            {"filename": "a.wav", "duration": -1},
            {"filename": "a.wav", "start": True},
            {"filename": "a.wav", "start": float("nan")},
            {"filename": "a.wav", "start": "two seconds"},
        ):
            with self.assertRaises(ValueError):
                parse_media_list(json.dumps([item]))

    def test_trim_range_reads_the_window_back_off_an_entry(self):
        self.assertEqual(trim_range({"filename": "a.wav", "start": 1, "duration": 2}), (1.0, 2.0))
        self.assertEqual(trim_range({"filename": "a.wav"}), (0.0, 0.0))
        self.assertEqual(trim_range("a.wav"), (0.0, 0.0))


class TestResolveMediaPath(unittest.TestCase):
    def test_finds_a_file_in_the_declared_folder(self):
        write_file("pic.png", "x")
        roots = {"input": TMP_ROOT}
        path = resolve_media_path(roots, {"filename": "pic.png", "subfolder": "", "type": "input"})
        self.assertEqual(os.path.realpath(path), os.path.realpath(os.path.join(TMP_ROOT, "pic.png")))

    def test_finds_a_file_in_a_subfolder(self):
        write_file(os.path.join("sub", "pic.png"), "x")
        path = resolve_media_path({"input": TMP_ROOT},
                                  {"filename": "pic.png", "subfolder": "sub", "type": "input"})
        self.assertTrue(os.path.isfile(path))

    def test_missing_file_names_the_media_folder(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_media_path({"input": TMP_ROOT},
                               {"filename": "gone.png", "subfolder": "", "type": "input"})
        self.assertIn("input folder", str(ctx.exception))

    def test_escaping_the_root_is_refused(self):
        outside = write_file("..\\..\\h3lvm_outside_probe.txt", "x")
        try:
            with self.assertRaises(ValueError):
                resolve_media_path({"input": TMP_ROOT},
                                   {"filename": os.path.basename(outside),
                                    "subfolder": "..\\..", "type": "input"})
        finally:
            os.remove(outside)

    def test_unknown_folder_type_is_an_error(self):
        with self.assertRaises(ValueError):
            resolve_media_path({}, {"filename": "a.png", "subfolder": "", "type": "input"})


class TestFillSlots(unittest.TestCase):
    def test_image_slots_are_none_after_the_last_card(self):
        built = []

        def build(entry):
            built.append(entry["filename"])
            return entry["filename"]

        for count in (0, 1, 8, 9, 12):
            entries = [{"filename": f"p{i}.png"} for i in range(count)]
            slots = fill_slots(entries, MAX_REF_IMAGES, build)
            self.assertEqual(len(slots), MAX_REF_IMAGES)
            self.assertEqual([value for value in slots if value is not None],
                             [f"p{i}.png" for i in range(min(count, MAX_REF_IMAGES))])
            self.assertEqual(built, [f"p{i}.png" for i in range(min(count, MAX_REF_IMAGES))])
            built.clear()

    def test_audio_slots_use_the_same_rule(self):
        slots = fill_slots([{"filename": "a.wav"}], MAX_REF_AUDIOS, lambda e: e["filename"])
        self.assertEqual(slots, ("a.wav", None, None))


class TestMediaFingerprint(unittest.TestCase):
    def test_a_card_window_is_part_of_the_key(self):
        roots = {"input": TMP_ROOT}
        write_file("k_window.wav", "same bytes")
        entry = {"filename": "k_window.wav", "subfolder": "", "type": "input"}
        self.assertNotEqual(
            media_fingerprint([entry], roots),
            media_fingerprint([dict(entry, start=1.0, duration=2.0)], roots),
            "the same file with a different window is a different output",
        )

    def test_same_list_gives_the_same_key(self):
        write_file("same.png", "hello")
        roots = {"input": TMP_ROOT}
        entries = parse_media_list('[{"filename": "same.png"}]')
        self.assertEqual(media_fingerprint(entries, roots), media_fingerprint(entries, roots))

    def test_replacing_the_bytes_invalidates_the_key(self):
        write_file("swap.png", "one")
        roots = {"input": TMP_ROOT}
        entries = parse_media_list('[{"filename": "swap.png"}]')
        before = media_fingerprint(entries, roots)
        write_file("swap.png", "one-longer-content")
        self.assertNotEqual(before, media_fingerprint(entries, roots))

    def test_order_is_part_of_the_key(self):
        write_file("first.png", "1")
        write_file("second.png", "2")
        roots = {"input": TMP_ROOT}
        left = media_fingerprint(parse_media_list('["first.png", "second.png"]'), roots)
        right = media_fingerprint(parse_media_list('["second.png", "first.png"]'), roots)
        self.assertNotEqual(left, right)

    def test_target_megapixels_is_part_of_the_key(self):
        roots = {"input": TMP_ROOT}
        entries = parse_media_list('[]')
        self.assertNotEqual(media_fingerprint(entries, roots, extra="0.25"),
                            media_fingerprint(entries, roots, extra="0.4"))

    def test_missing_file_still_produces_a_key(self):
        # validate_inputs reports the problem; the cache key must not crash first.
        self.assertIsInstance(media_fingerprint(parse_media_list('["gone.png"]'),
                                               {"input": TMP_ROOT}), str)


if __name__ == "__main__":
    unittest.main()
