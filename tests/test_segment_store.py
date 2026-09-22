"""Tests for H3 Long Video Manager — segment_store (Phase A).

Run with:
    cd H3-Long-Video-Manager
    python -m tests.test_segment_store
"""
from __future__ import annotations

import os
import sys
import tempfile
import shutil
import unittest

# Ensure plugin root is importable
_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

import torch

from comfyui.segment_store import (
    set_base_dir_override,
    sanitize_project_name,
    save_segment,
    load_segment,
    load_project_index,
    list_project,
    list_projects,
    delete_segment,
    get_project_dir,
    BIN_DIR_NAME,
    INDEX_NAME,
    DEFAULT_PROJECT,
)


class TestSanitize(unittest.TestCase):
    def test_empty_becomes_default(self):
        self.assertEqual(sanitize_project_name(""), DEFAULT_PROJECT)

    def test_none_becomes_default(self):
        self.assertEqual(sanitize_project_name(None), DEFAULT_PROJECT)

    def test_bad_chars_cleaned(self):
        result = sanitize_project_name("my/project:folder*")
        self.assertNotIn("/", result)
        self.assertNotIn(":", result)
        self.assertNotIn("*", result)

    def test_normal_name_preserved(self):
        self.assertEqual(sanitize_project_name("MyProject"), "MyProject")

    def test_whitespace_stripped(self):
        self.assertEqual(sanitize_project_name("  hello  "), "hello")


class TestSaveLoad(unittest.TestCase):
    """Test save_segment → load_segment round-trip."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="h3lvm_test_")
        set_base_dir_override(self._tmpdir)

    def tearDown(self):
        set_base_dir_override(None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_video(self, F=10, H=32, W=64):
        return torch.rand(F, H, W, 3, dtype=torch.float32)

    def _make_audio(self, samples=10000, sr=44100):
        return {"waveform": torch.randn(1, 1, samples), "sample_rate": sr}

    def test_save_creates_files(self):
        video = self._make_video()
        audio = self._make_audio()
        meta = save_segment("TestProj", 1, video, audio, fps=24, save_mp4=False)

        pdir = get_project_dir("TestProj", create=False)
        sdir = os.path.join(pdir, "seg01")
        self.assertTrue(os.path.isdir(sdir))

        # safetensors or .pt
        has_tensor = (os.path.isfile(os.path.join(sdir, "seg01.safetensors"))
                      or os.path.isfile(os.path.join(sdir, "seg01.pt")))
        self.assertTrue(has_tensor, "tensor file not created")

        # PNG
        self.assertTrue(os.path.isfile(os.path.join(sdir, "seg01_first.png")))

        # Index
        self.assertTrue(os.path.isfile(os.path.join(pdir, INDEX_NAME)))

    def test_load_roundtrip(self):
        video = self._make_video()
        audio = self._make_audio()
        save_segment("RoundTrip", 1, video, audio, fps=24)

        loaded_video, loaded_audio, meta = load_segment("RoundTrip", 1)

        # Video shape matches
        self.assertEqual(loaded_video.shape, video.shape)
        # Video values close (f16 precision)
        self.assertTrue(torch.allclose(
            loaded_video.float(), video, atol=1e-2
        ))

        # Audio
        self.assertIsNotNone(loaded_audio)
        self.assertEqual(loaded_audio["waveform"].shape, audio["waveform"].shape)
        self.assertEqual(loaded_audio["sample_rate"], 44100)

    def test_save_no_audio(self):
        video = self._make_video()
        save_segment("NoAudio", 1, video, None, fps=24)

        _, loaded_audio, _ = load_segment("NoAudio", 1)
        self.assertIsNone(loaded_audio)

    def test_multiple_segments(self):
        video = self._make_video(F=20)
        audio = self._make_audio()
        for i in range(1, 4):
            save_segment("Multi", i, video, audio, fps=24)

        idx = load_project_index("Multi")
        self.assertEqual(idx["total_segments"], 3)
        self.assertEqual(len(idx["segments"]), 3)
        ids = [s["segment_id"] for s in idx["segments"]]
        self.assertEqual(ids, [1, 2, 3])

    def test_upsert_overwrites(self):
        video1 = self._make_video(F=10)
        video2 = self._make_video(F=15)
        save_segment("Upsert", 1, video1, None, fps=24)
        save_segment("Upsert", 1, video2, None, fps=24)

        idx = load_project_index("Upsert")
        self.assertEqual(idx["total_segments"], 1)
        self.assertEqual(idx["segments"][0]["frames"], 15)


class TestListProjects(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="h3lvm_list_")
        set_base_dir_override(self._tmpdir)

    def tearDown(self):
        set_base_dir_override(None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_empty(self):
        self.assertEqual(list_projects(), [])

    def test_after_save(self):
        video = torch.rand(5, 16, 16, 3)
        save_segment("ProjA", 1, video, None, fps=24)
        save_segment("ProjB", 1, video, None, fps=24)

        projects = list_projects()
        self.assertIn("ProjA", projects)
        self.assertIn("ProjB", projects)
        self.assertEqual(len(projects), 2)


class TestListProject(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="h3lvm_lp_")
        set_base_dir_override(self._tmpdir)

    def tearDown(self):
        set_base_dir_override(None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_enriched_urls(self):
        video = torch.rand(10, 32, 64, 3)
        save_segment("URLTest", 1, video, None, fps=24)

        data = list_project("URLTest")
        self.assertEqual(data["total_segments"], 1)
        seg = data["segments"][0]
        # thumbnail_url should be set (PNG was created)
        self.assertIn("thumbnail_url", seg)
        self.assertTrue(seg["thumbnail_url"].startswith("/view?"))


class TestDelete(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="h3lvm_del_")
        set_base_dir_override(self._tmpdir)

    def tearDown(self):
        set_base_dir_override(None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_delete_removes(self):
        video = torch.rand(5, 16, 16, 3)
        save_segment("DelTest", 1, video, None, fps=24)
        save_segment("DelTest", 2, video, None, fps=24)

        self.assertTrue(delete_segment("DelTest", 1))

        idx = load_project_index("DelTest")
        self.assertEqual(idx["total_segments"], 1)
        self.assertEqual(idx["segments"][0]["segment_id"], 2)

    def test_delete_nonexistent(self):
        self.assertFalse(delete_segment("NoProj", 99))


if __name__ == "__main__":
    unittest.main(verbosity=2)
