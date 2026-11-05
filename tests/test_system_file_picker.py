"""The native picker returns an arbitrary absolute path without reading file bytes."""
from __future__ import annotations

import importlib
import os
import shutil
import unittest
from unittest import mock

from tests._temp_dir import make_temp_dir
from tests.test_node_schema import NODES

system_file_picker = (importlib.import_module(
    ".system_file_picker", package=NODES.__package__) if NODES is not None else None)


@unittest.skipIf(NODES is None, "comfy_api unavailable")
class TestSystemFilePicker(unittest.TestCase):
    def setUp(self):
        self.tmpdir = make_temp_dir(prefix="h3lvm_system_picker_")
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        self.path = os.path.join(self.tmpdir, "任意磁盘 视频.mp4")
        with open(self.path, "wb") as handle:
            handle.write(b"path validation only")

    def test_windows_selection_is_not_restricted_to_input(self):
        with mock.patch.object(system_file_picker.platform, "system", return_value="Windows"), \
                mock.patch.object(system_file_picker, "_windows_pick_file", return_value=self.path), \
                mock.patch.object(system_file_picker, "probe_video", return_value={
                    "duration_sec": 12.0, "width": 1920, "height": 1080,
                }):
            result = system_file_picker.choose_system_video()
        self.assertFalse(result["cancelled"])
        self.assertEqual(result["path"], os.path.realpath(self.path))
        self.assertEqual(result["name"], "任意磁盘 视频.mp4")

    def test_cancel_does_not_probe_or_invent_a_path(self):
        with mock.patch.object(system_file_picker.platform, "system", return_value="Windows"), \
                mock.patch.object(system_file_picker, "_windows_pick_file", return_value=""), \
                mock.patch.object(system_file_picker, "probe_video") as probe:
            result = system_file_picker.choose_system_video()
        self.assertEqual(result, {"cancelled": True})
        probe.assert_not_called()

    def test_non_windows_has_a_clear_fallback_message(self):
        with mock.patch.object(system_file_picker.platform, "system", return_value="Linux"):
            with self.assertRaisesRegex(RuntimeError, "服务器文件浏览器"):
                system_file_picker.choose_system_video()

    def test_a_second_dialog_is_refused_instead_of_stacking(self):
        self.assertTrue(system_file_picker._dialog_lock.acquire(blocking=False))
        self.addCleanup(system_file_picker._dialog_lock.release)
        with mock.patch.object(system_file_picker.platform, "system", return_value="Windows"):
            with self.assertRaisesRegex(RuntimeError, "已经打开"):
                system_file_picker.choose_system_video()

    def test_a_folder_opens_even_when_raising_it_fails(self):
        # The shell already opened the folder; a window lookup failure is not an error
        # the panel should report as a failed request.
        with mock.patch.object(system_file_picker.platform, "system", return_value="Windows"), \
                mock.patch.object(system_file_picker, "_explorer_windows", return_value=[]), \
                mock.patch.object(system_file_picker, "_raise_explorer",
                                  side_effect=OSError("no window yet")), \
                mock.patch.object(system_file_picker.os, "startfile") as startfile:
            system_file_picker.open_local_folder(self.tmpdir)
        startfile.assert_called_once_with(os.path.realpath(self.tmpdir))

    def test_opening_a_folder_is_windows_only(self):
        with mock.patch.object(system_file_picker.platform, "system", return_value="Linux"):
            with self.assertRaisesRegex(RuntimeError, "仅支持 Windows"):
                system_file_picker.open_local_folder(self.tmpdir)

    def test_the_window_the_shell_just_created_is_the_one_raised(self):
        folder = os.path.join(self.tmpdir, "Movie")
        with mock.patch.object(system_file_picker, "_explorer_windows",
                               side_effect=[[(1, "Old")], [(1, "Old"), (2, "Movie")]]), \
                mock.patch("ctypes.windll", mock.MagicMock()):
            self.assertTrue(system_file_picker._raise_explorer(folder, {1}, timeout=0.5))


if __name__ == "__main__":
    unittest.main()
