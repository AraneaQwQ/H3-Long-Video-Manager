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
    normalize_save_dtype,
    _load_tensors,
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


class TestSaveDtype(unittest.TestCase):
    """The int8 / fp16 storage switch."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="h3lvm_dtype_")
        set_base_dir_override(self._tmpdir)

    def tearDown(self):
        set_base_dir_override(None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _stored_dtype(self, project, seg_id=1):
        sdir = os.path.join(get_project_dir(project, create=False), f"seg{seg_id:02d}")
        tensors = _load_tensors(os.path.join(sdir, f"seg{seg_id:02d}.safetensors"))
        return tensors["video"].dtype

    def _tensor_file_size(self, project, seg_id=1):
        sdir = os.path.join(get_project_dir(project, create=False), f"seg{seg_id:02d}")
        return os.path.getsize(os.path.join(sdir, f"seg{seg_id:02d}.safetensors"))

    def test_aliases(self):
        for value in ("fp16", "FP16", " float16 ", "half", "f16"):
            self.assertEqual(normalize_save_dtype(value), "fp16", value)
        for value in ("int8", "", None, "int4", "fp8", "uint8"):
            self.assertEqual(normalize_save_dtype(value), "int8", repr(value))

    def test_int8_is_the_default(self):
        video = torch.rand(6, 16, 16, 3)
        meta = save_segment("DtypeDefault", 1, video, None, fps=24)
        self.assertEqual(meta["video_dtype"], "int8")
        self.assertEqual(self._stored_dtype("DtypeDefault"), torch.int8)

    def test_int8_is_exact_for_8bit_sources(self):
        # Every real frame comes out of the decoder as uint8 / 255, so int8
        # storage must round-trip those values bit for bit.
        quantized = torch.randint(0, 256, (8, 16, 16, 3), dtype=torch.uint8)
        video = quantized.float() / 255.0
        save_segment("DtypeExact", 1, video, None, fps=24, save_dtype="int8")
        loaded, _, _ = load_segment("DtypeExact", 1)
        self.assertEqual(loaded.dtype, torch.float32)
        self.assertTrue(torch.equal(loaded, video))

    def test_int8_halves_the_file(self):
        video = torch.rand(40, 64, 64, 3)
        save_segment("DtypeSmall", 1, video, None, fps=24, save_dtype="int8")
        save_segment("DtypeLarge", 1, video, None, fps=24, save_dtype="fp16")
        small = self._tensor_file_size("DtypeSmall")
        large = self._tensor_file_size("DtypeLarge")
        self.assertLess(small, large * 0.6)

    def test_fp16_option_keeps_float_tensors(self):
        video = torch.rand(6, 16, 16, 3)
        meta = save_segment("DtypeFp16", 1, video, None, fps=24, save_dtype="fp16")
        self.assertEqual(meta["video_dtype"], "fp16")
        self.assertEqual(self._stored_dtype("DtypeFp16"), torch.float16)
        loaded, _, _ = load_segment("DtypeFp16", 1)
        self.assertEqual(loaded.dtype, torch.float16)
        self.assertTrue(torch.equal(loaded, video.to(torch.float16)))

    def test_mixed_project_loads_each_segment(self):
        video = (torch.randint(0, 256, (6, 16, 16, 3)).float() / 255.0)
        save_segment("DtypeMixed", 1, video, None, fps=24, save_dtype="int8")
        save_segment("DtypeMixed", 2, video, None, fps=24, save_dtype="fp16")
        first, _, _ = load_segment("DtypeMixed", 1)
        second, _, _ = load_segment("DtypeMixed", 2)
        self.assertTrue(torch.equal(first, video))
        self.assertTrue(torch.allclose(second.float(), video, atol=2e-3))

    def test_int8_output_stays_in_range(self):
        video = torch.rand(8, 16, 16, 3) * 1.5  # values above 1 are clamped
        save_segment("DtypeRange", 1, video, None, fps=24, save_dtype="int8")
        loaded, _, _ = load_segment("DtypeRange", 1)
        self.assertGreaterEqual(float(loaded.min()), 0.0)
        self.assertLessEqual(float(loaded.max()), 1.0)
        self.assertTrue(torch.allclose(loaded, video.clamp(0.0, 1.0), atol=1.0 / 255.0))


class TestThumbnailFrame(unittest.TestCase):
    """Smart Split needs the cover to be the first MAIN frame, not the MC overlap."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="h3lvm_thumb_")
        set_base_dir_override(self._tmpdir)

    def tearDown(self):
        set_base_dir_override(None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _ramp_video(self, frames=30):
        """Frame i is a flat colour of value i, so a cover pixel names its frame."""
        video = torch.zeros(frames, 8, 8, 3, dtype=torch.float32)
        for index in range(frames):
            video[index] = index / 255.0
        return video

    def _cover_pixel(self, project, tag="seg01"):
        from PIL import Image

        path = os.path.join(get_project_dir(project, create=False), tag, f"{tag}_first.png")
        with Image.open(path) as image:
            return image.convert("RGB").getpixel((0, 0))

    def test_default_cover_is_still_frame_zero(self):
        save_segment("ThumbDefault", 1, self._ramp_video(), None, fps=24)
        self.assertEqual(self._cover_pixel("ThumbDefault"), (0, 0, 0))

    def test_thumbnail_frame_skips_the_context_overlap(self):
        save_segment("ThumbMain", 1, self._ramp_video(), None, fps=24, thumbnail_frame=22)
        self.assertEqual(self._cover_pixel("ThumbMain"), (22, 22, 22))

    def test_out_of_range_cover_clamps_to_the_last_frame(self):
        save_segment("ThumbClamp", 1, self._ramp_video(5), None, fps=24, thumbnail_frame=99)
        self.assertEqual(self._cover_pixel("ThumbClamp"), (4, 4, 4))


if __name__ == "__main__":
    unittest.main(verbosity=2)
