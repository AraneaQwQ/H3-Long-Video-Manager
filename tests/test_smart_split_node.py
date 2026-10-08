"""H3 Smart Split - end-to-end node test (needs comfy_api + PySceneDetect).

Planning doc sections 75, 76, 77 and 37: detect on a real tensor, save through
the existing Store, and read the result back with the existing loader. The
cover must be the first MAIN frame even when Motion Context widens the
extraction.
"""

import importlib
import os
import shutil
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import torch

from core.smart_split import scenedetect_available

from tests.test_node_schema import LOAD_ERROR, NODES

# The Store must be the module instance the node itself imported, otherwise the
# base-dir override below would point at a copy and saves would hit ComfyUI's
# real output folder.
store = importlib.import_module(".segment_store", package=NODES.__package__)
get_project_dir = store.get_project_dir
load_project_index = store.load_project_index
load_segment = store.load_segment
set_base_dir_override = store.set_base_dir_override

PROJECT = "SmartE2E"


def _two_shot_video(cut=60, frames=120, height=48, width=64):
    """Two flat shots split by one hard cut, each with a faint per-frame ramp.

    The ramp makes every frame identifiable by its pixel value (so a cover can
    be traced back to the frame it came from) while staying far too small to
    create extra cuts; the shot-to-shot jump is what the detector must find.
    """
    video = torch.zeros(frames, height, width, 3, dtype=torch.float32)
    for index in range(frames):
        base = 0.05 if index < cut else 0.75
        video[index] = base + (index / float(frames)) * 0.2
    return video


def _frame_value(index, frames=120, cut=60):
    """The cover pixel the Store writes for frame ``index``.

    Mirrors segment_store.tensor_to_pil, i.e. clamp(0,1) * 255 truncated to
    uint8 - not rounded.
    """
    base = 0.05 if index < cut else 0.75
    value = torch.tensor(base + (index / float(frames)) * 0.2, dtype=torch.float32)
    return int(value.mul(255).to(torch.uint8).item())


@unittest.skipIf(NODES is None, f"comfy_api unavailable: {LOAD_ERROR}")
@unittest.skipUnless(scenedetect_available(), "PySceneDetect is not installed")
class TestSmartSplitNode(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="h3lvm_smart_")
        set_base_dir_override(self._tmpdir)

    def tearDown(self):
        set_base_dir_override(None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _run(self, motion_context="0", segment_id=1, save_enabled=True, project=PROJECT):
        out = NODES.H3SmartSplit.execute(
            video=_two_shot_video(), fps=24, detection_sensitivity="medium",
            motion_context_frames=motion_context, segment_id=segment_id,
            project_name=project, save_enabled=save_enabled,
        )
        return out.args

    def _cover_pixel(self, tag, project=PROJECT):
        from PIL import Image

        path = os.path.join(get_project_dir(project, create=False), tag, f"{tag}_first.png")
        with Image.open(path) as image:
            return image.convert("RGB").getpixel((0, 0))

    def test_hard_cut_becomes_two_saved_segments(self):
        live_video, live_audio, frame_count, total_segments = self._run()
        self.assertEqual(total_segments, 2)
        self.assertEqual(frame_count, 60)
        self.assertEqual(live_video.shape[0], 60)
        self.assertIsNotNone(live_audio)

        index = load_project_index(PROJECT)
        self.assertEqual(index["total_segments"], 2)
        entries = {e["segment_id"]: e for e in index["segments"]}
        self.assertEqual(sorted(entries), [1, 2])
        self.assertEqual([(e["main_start"], e["main_end"]) for e in index["segments"]],
                         [(0, 60), (60, 120)])
        self.assertEqual(sum(e["main_frames"] for e in index["segments"]), 120)
        for entry in index["segments"]:
            self.assertEqual(entry["segmentation_method"], "smart")
            self.assertEqual(entry["context_frames"], 0)

    def test_saved_tensors_match_the_scene_boundaries(self):
        self._run()
        first, _, first_meta = load_segment(PROJECT, 1)
        second, _, second_meta = load_segment(PROJECT, 2)
        self.assertEqual(first.shape[0], 60)
        self.assertEqual(second.shape[0], 60)
        self.assertEqual(first_meta["main_start"], 0)
        self.assertEqual(second_meta["main_start"], 60)

    def test_motion_context_widens_the_file_but_not_the_main_range(self):
        self._run(motion_context="22", segment_id=2)
        index = load_project_index(PROJECT)
        entries = {e["segment_id"]: e for e in index["segments"]}
        self.assertEqual(entries[1]["frames"], 60)
        self.assertEqual(entries[2]["frames"], 82)
        self.assertEqual(entries[2]["main_frames"], 60)
        self.assertEqual(entries[2]["context_frames"], 22)
        self.assertEqual(entries[2]["main_start"], 60)

    def test_cover_is_the_first_main_frame_not_the_context(self):
        self._run(motion_context="22", segment_id=2)
        main_frame = (_frame_value(60),) * 3
        context_frame = (_frame_value(38),) * 3
        self.assertEqual(self._cover_pixel("seg02"), main_frame)
        self.assertNotEqual(self._cover_pixel("seg02"), context_frame)
        self.assertEqual(self._cover_pixel("seg01"), (_frame_value(0),) * 3)

    def test_selected_segment_output_follows_segment_id(self):
        live_video, _, frame_count, _ = self._run(motion_context="22", segment_id=2)
        self.assertEqual(frame_count, 82)
        self.assertEqual(live_video.shape[0], 82)

    def test_save_disabled_writes_nothing(self):
        _, _, frame_count, total_segments = self._run(save_enabled=False)
        self.assertEqual(total_segments, 2)
        self.assertEqual(frame_count, 60)
        self.assertEqual(load_project_index(PROJECT)["total_segments"], 0)

    def test_segment_id_out_of_range_explains_the_plan(self):
        with self.assertRaises(ValueError) as ctx:
            self._run(segment_id=9)
        self.assertIn("out of range [1, 2]", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)