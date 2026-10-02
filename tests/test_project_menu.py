"""The project menu behind the H3 Segment Picker.

The panel asks which folder to read instead of making the user type a project name,
so the backend has to list what already exists with its segment count, create a bin on
request, and delete one when a story is abandoned. These tests drive the real index
format against a throwaway output folder.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

# Ensure plugin root is importable
_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from comfyui.segment_store import (
    create_project,
    delete_project,
    get_project_dir,
    INDEX_NAME,
    list_project,
    list_projects,
    list_projects_with_counts,
    MAX_PROJECT_NAME_LENGTH,
    set_base_dir_override,
)


class ProjectFixture(unittest.TestCase):
    """A throwaway output folder plus the index writer both test classes need."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="h3lvm_menu_")
        set_base_dir_override(self._tmpdir)

    def tearDown(self):
        set_base_dir_override(None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def add_segment(self, project, seg_id):
        """Writes one index entry the way the Manager node would.

        The files themselves are not needed here - the menu counts what the index
        declares, which is exactly what the cards show.
        """
        seg_dir = os.path.join(self._tmpdir, project, "seg%02d" % seg_id)
        os.makedirs(seg_dir, exist_ok=True)
        path = os.path.join(self._tmpdir, project, INDEX_NAME)
        idx = {"project_name": project, "total_segments": 0, "segments": []}
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as stream:
                idx = json.load(stream)
        idx["segments"].append({"segment_id": seg_id, "dir": "seg%02d" % seg_id})
        idx["total_segments"] = len(idx["segments"])
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(idx, stream, ensure_ascii=False)

    def names(self):
        return [item["name"] for item in list_projects_with_counts()]

    def count(self, name):
        for item in list_projects_with_counts():
            if item["name"] == name:
                return item["segments"]
        self.fail("project %r is not in the menu" % name)


class TestProjectListing(ProjectFixture):
    def test_only_folders_with_an_index_are_offered(self):
        os.makedirs(os.path.join(self._tmpdir, "HalfSaved"), exist_ok=True)
        self.assertEqual(list_projects(), [])
        self.assertEqual(list_projects_with_counts(), [])

    def test_every_bin_is_listed_sorted_with_its_segment_count(self):
        self.add_segment("Movie", 1)
        self.add_segment("Movie", 2)
        self.add_segment("Other", 1)
        self.assertEqual(self.names(), ["Movie", "Other"])
        self.assertEqual(self.count("Movie"), 2)
        self.assertEqual(self.count("Other"), 1)

    def test_an_empty_bin_is_still_offered(self):
        create_project("Fresh")
        self.assertEqual(list_projects_with_counts(), [{"name": "Fresh", "segments": 0}])


class TestProjectCreation(ProjectFixture):
    def test_a_new_bin_is_created_and_shows_up_in_the_menu(self):
        result = create_project("科幻短片 01")
        self.assertEqual(result, {"name": "科幻短片 01", "created": True, "segments": 0})
        self.assertTrue(os.path.isdir(os.path.join(self._tmpdir, "科幻短片 01")))
        self.assertEqual(self.names(), ["科幻短片 01"])

    def test_a_new_bin_writes_an_empty_index_the_picker_can_read(self):
        create_project("Fresh")
        data = list_project("Fresh")
        self.assertEqual(data["segments"], [])
        self.assertEqual(data["total_segments"], 0)

    def test_an_existing_name_is_selected_rather_than_duplicated(self):
        self.add_segment("Movie", 1)
        result = create_project("Movie")
        self.assertEqual(result, {"name": "Movie", "created": False, "segments": 1})
        self.assertEqual(self.names(), ["Movie"])
        self.assertEqual(self.count("Movie"), 1)

    def test_the_name_returned_is_the_folder_name_that_was_written(self):
        # The panel writes back what the server answers, so the widget can never hold
        # a name that does not exist on disk.
        result = create_project("  我的/项目: 第一集  ")
        self.assertEqual(result["name"], "我的_项目_ 第一集")
        self.assertTrue(os.path.isdir(os.path.join(self._tmpdir, "我的_项目_ 第一集")))
        self.assertEqual(self.names(), ["我的_项目_ 第一集"])

    def test_a_name_without_letters_or_digits_is_refused(self):
        for typed in ("", "   ", "///", "———", None):
            with self.assertRaises(ValueError):
                create_project(typed)
        self.assertEqual(list_projects(), [])
        self.assertFalse(os.path.isdir(get_project_dir("///", create=False)))

    def test_an_overlong_name_is_refused(self):
        with self.assertRaises(ValueError):
            create_project("x" * (MAX_PROJECT_NAME_LENGTH + 1))


class TestProjectDeletion(ProjectFixture):
    """Deleting a whole bin, which is the mirror of creating one and just as final."""

    def test_deleting_a_bin_removes_the_folder_and_every_segment_in_it(self):
        self.add_segment("Movie", 1)
        self.add_segment("Movie", 2)
        self.add_segment("Other", 1)
        result = delete_project("Movie", "Movie")
        self.assertEqual(result, {"name": "Movie", "deleted": True, "segments": 2})
        self.assertFalse(os.path.exists(os.path.join(self._tmpdir, "Movie")))
        self.assertEqual(self.names(), ["Other"])

    def test_the_confirm_name_has_to_match(self):
        self.add_segment("Movie", 1)
        for confirm in ("", "movie", "Other", None):
            with self.assertRaises(ValueError):
                delete_project("Movie", confirm)
        self.assertTrue(os.path.isdir(os.path.join(self._tmpdir, "Movie")))

    def test_the_sanitized_name_is_the_one_that_has_to_be_confirmed(self):
        create_project("我的/项目: 第一集")
        with self.assertRaises(ValueError):
            delete_project("我的/项目: 第一集", "我的/项目: 第一集")
        result = delete_project("我的/项目: 第一集", "我的_项目_ 第一集")
        self.assertTrue(result["deleted"])
        self.assertEqual(self.names(), [])

    def test_a_bin_that_is_already_gone_reports_that_without_recreating_it(self):
        result = delete_project("Movie", "Movie")
        self.assertEqual(result, {"name": "Movie", "deleted": False, "segments": 0})
        self.assertFalse(os.path.exists(os.path.join(self._tmpdir, "Movie")))

    def test_a_name_without_letters_or_digits_is_refused(self):
        for typed in ("", "   ", "///"):
            with self.assertRaises(ValueError):
                delete_project(typed, typed)


if __name__ == "__main__":
    unittest.main()

