"""Tests for H3 Long Video Manager — merging adjacent segments by hand.

Run with:
    cd H3-Long-Video-Manager
    python -m tests.test_merge_segments
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
    _load_tensors,
    get_project_dir,
    load_project_index,
    load_segment,
    merge_segments,
    save_segment,
    set_base_dir_override,
)


def ramp_video(first_frame, count, height=16, width=32):
    """A video whose frame values say which source frame each frame came from."""
    frames = [torch.full((height, width, 3), (first_frame + i) / 100.0, dtype=torch.float32)
              for i in range(count)]
    return torch.stack(frames, dim=0)


def _first_pixel(video, index):
    return float(video[index, 0, 0, 0])


class MergeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="h3lvm_merge_")
        set_base_dir_override(self._tmpdir)

    def tearDown(self):
        set_base_dir_override(None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def save_shot(self, project, seg_id, first_frame, count, context=0, fps=24,
                  audio=True, height=16, width=32, save_dtype="int8"):
        """Save one segment the way the split nodes do: context frames up front."""
        audio_dict = None
        if audio:
            samples = int(count / fps * 44100)
            audio_dict = {"waveform": torch.zeros(1, 1, samples), "sample_rate": 44100}
        return save_segment(
            project, seg_id, ramp_video(first_frame, count, height, width), audio_dict,
            fps=fps, save_dtype=save_dtype,
            meta={
                "context_frames": context,
                "main_start": first_frame,
                "main_end": first_frame + count - context,
                "main_frames": count - context,
            },
        )

    def ids_in_bin(self, project):
        return [s["segment_id"] for s in load_project_index(project).get("segments", [])]


class TestMergeShape(MergeTestCase):
    def test_merge_drops_overlap_and_keeps_frame_order(self):
        self.save_shot("M1", 1, 0, 10, context=0)
        self.save_shot("M1", 2, 5, 10, context=5)  # its head repeats frames 5..9

        result = merge_segments("M1", [1, 2])
        self.assertEqual(result["merged_id"], 1)
        self.assertEqual(result["merged_from"], [1, 2])
        self.assertEqual(result["dropped_overlap_frames"], 5)
        self.assertEqual(result["renumbered"], [])
        self.assertEqual(self.ids_in_bin("M1"), [1])

        entry = load_project_index("M1")["segments"][0]
        self.assertEqual(entry["frames"], 15)
        self.assertEqual(entry["segmentation_method"], "manual_merge")
        self.assertEqual(entry["merged_parts"], 2)
        self.assertEqual(entry["main_start"], 0)
        self.assertEqual(entry["main_frames"], 15)

        video, _, meta = load_segment("M1", 1)
        self.assertEqual(video.shape[0], 15)
        self.assertEqual(meta["segment_id"], 1)
        for index in range(15):
            self.assertAlmostEqual(_first_pixel(video, index), index / 100.0, places=2)

    def test_merged_cover_comes_from_the_main_range(self):
        # tensor_to_pil needs float [0,1]; a packed int8 cover would turn out black.
        self.save_shot("C1", 1, 0, 10, context=3)
        self.save_shot("C1", 2, 7, 10, context=5)
        merged = merge_segments("C1", [1, 2])["segment"]

        from PIL import Image
        path = os.path.join(get_project_dir("C1", create=False), "seg01", merged["thumbnail"])
        self.assertTrue(os.path.isfile(path))
        image = Image.open(path).convert("RGB")
        mean = sum(image.getpixel((0, 0))) / 3.0
        self.assertAlmostEqual(mean, 3 * 2.55, delta=3)

    def test_merge_keeps_the_stored_dtype(self):
        for dtype in ("int8", "fp16"):
            project = "D_" + dtype
            self.save_shot(project, 1, 0, 10, context=0, save_dtype=dtype)
            self.save_shot(project, 2, 5, 10, context=5, save_dtype=dtype)
            merged = merge_segments(project, [1, 2])["segment"]
            self.assertEqual(merged["video_dtype"], dtype)

            tensors_file = os.path.join(get_project_dir(project, create=False), "seg01", merged["tensors_file"])
            raw = _load_tensors(tensors_file)["video"]
            expected = torch.float16 if dtype == "fp16" else torch.int8
            self.assertEqual(raw.dtype, expected)
            self.assertEqual(raw.shape[0], 15)

    def test_merge_rejects_odd_shapes(self):
        self.save_shot("S1", 1, 0, 10, context=0, fps=24)
        self.save_shot("S1", 2, 5, 10, context=5, fps=30)
        with self.assertRaises(ValueError):
            merge_segments("S1", [1, 2])

        self.save_shot("S2", 1, 0, 10, context=0, height=16, width=32)
        self.save_shot("S2", 2, 5, 10, context=5, height=16, width=48)
        with self.assertRaises(ValueError):
            merge_segments("S2", [1, 2])


class TestMergeIds(MergeTestCase):
    def test_later_segments_shift_down_and_files_follow(self):
        for index in range(1, 6):
            self.save_shot("M2", index, (index - 1) * 10, 10, context=5 if index > 1 else 0)

        result = merge_segments("M2", [2, 3])
        self.assertEqual(result["merged_id"], 2)
        self.assertEqual(result["renumbered"], [{"from": 4, "to": 3}, {"from": 5, "to": 4}])
        self.assertEqual(self.ids_in_bin("M2"), [1, 2, 3, 4])

        pdir = get_project_dir("M2", create=False)
        self.assertFalse(os.path.isdir(os.path.join(pdir, "seg05")))
        for tag in ("seg01", "seg02", "seg03", "seg04"):
            self.assertTrue(os.path.isdir(os.path.join(pdir, tag)))
        moved = os.path.join(pdir, "seg04")
        self.assertTrue(os.path.isfile(os.path.join(moved, "seg04_first.png")))
        self.assertTrue(os.path.isfile(os.path.join(moved, "seg04.safetensors"))
                        or os.path.isfile(os.path.join(moved, "seg04.pt")))

        entry = [s for s in load_project_index("M2")["segments"] if s["segment_id"] == 4][0]
        self.assertEqual(entry["tag"], "seg04")
        self.assertEqual(entry["dir"], "seg04")
        self.assertTrue(entry["thumbnail"].startswith("seg04"))
        self.assertTrue(entry["tensors_file"].startswith("seg04"))

        # The old segment 4 and 5 content is now reachable as 3 and 4.
        moved, _, _ = load_segment("M2", 3)
        self.assertAlmostEqual(_first_pixel(moved, 0), 30 / 100.0, places=2)
        last, _, _ = load_segment("M2", 4)
        self.assertAlmostEqual(_first_pixel(last, 0), 40 / 100.0, places=2)

    def test_merge_at_the_end_renumbers_nothing(self):
        for index in range(1, 4):
            self.save_shot("M3", index, (index - 1) * 10, 10, context=5 if index > 1 else 0)
        result = merge_segments("M3", [2, 3])
        self.assertEqual(self.ids_in_bin("M3"), [1, 2])
        self.assertEqual(result["renumbered"], [])

    def test_only_adjacent_ids_are_allowed(self):
        for index in range(1, 5):
            self.save_shot("M4", index, (index - 1) * 10, 10, context=0)
        for bad in ([1], [1, 3], [1, 2, 4], [], "1,2", [0, 1], [True, 2], None):
            with self.assertRaises(ValueError):
                merge_segments("M4", bad)

    def test_missing_segment_is_reported(self):
        self.save_shot("M5", 1, 0, 10, context=0)
        with self.assertRaises(ValueError):
            merge_segments("M5", [1, 2])

    def test_merging_twice_stays_contiguous(self):
        for index in range(1, 5):
            self.save_shot("M6", index, (index - 1) * 10, 10, context=5 if index > 1 else 0)
        merge_segments("M6", [1, 2])
        merge_segments("M6", [2, 3])
        self.assertEqual(self.ids_in_bin("M6"), [1, 2])
        video, _, _ = load_segment("M6", 1)
        self.assertEqual(video.shape[0], 15)
        video2, _, _ = load_segment("M6", 2)
        self.assertEqual(video2.shape[0], 15)


class TestMergeAudio(MergeTestCase):
    def test_audio_is_joined_without_the_overlap(self):
        self.save_shot("A1", 1, 0, 10, context=0)
        self.save_shot("A1", 2, 5, 10, context=5)
        merge_segments("A1", [1, 2])

        _, audio, meta = load_segment("A1", 1)
        self.assertIsNotNone(audio)
        self.assertEqual(audio["sample_rate"], 44100)
        # 15 joined frames of audio, not 20: the seam must not repeat either.
        self.assertAlmostEqual(audio["waveform"].shape[-1], int(15 / 24 * 44100), delta=3)
        self.assertTrue(meta["has_audio"])

    def test_audio_is_dropped_when_a_part_has_none(self):
        self.save_shot("A2", 1, 0, 10, context=0, audio=True)
        self.save_shot("A2", 2, 5, 10, context=5, audio=False)
        merge_segments("A2", [1, 2])

        _, audio, meta = load_segment("A2", 1)
        self.assertIsNone(audio)
        self.assertFalse(meta["has_audio"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
