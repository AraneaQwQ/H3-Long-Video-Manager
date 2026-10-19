"""H3 Segment Picker dual-mode node tests (needs comfy_api + PyAV + ffmpeg).

The questions this file answers are the ones the task book asks about the node: does a
workflow saved before `source_mode` existed still read the cut bin with the same four
outputs, does the same node read the upload library instead when asked, and does a
project name that exists in both libraries stay two different clips.
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

from tests._media_clip import have_ffmpeg, make_clip, make_vfr_clip
from tests.test_node_schema import LOAD_ERROR, NODES

try:
    import av  # noqa: F401
    HAS_AV = True
except ImportError:
    HAS_AV = False

READY = NODES is not None and have_ffmpeg() and HAS_AV
SKIP_WHY = "needs comfy_api, PyAV and ffmpeg on PATH (%s)" % (LOAD_ERROR,)

# These must be the module instances the node itself imported; overriding a copy would
# point the node at ComfyUI's real output folder instead of the temporary one.
if NODES is not None:
    bin_store = importlib.import_module(".segment_store", package=NODES.__package__)
    upload_store = importlib.import_module(".uploaded_video_store", package=NODES.__package__)
else:
    bin_store = upload_store = None

PROJECT = "DualMode"
# make_clip's default is 64x36, and ComfyUI tensors are [F,H,W,3].
CLIP_SHAPE = (36, 64, 3)


class _TwoLibraries(unittest.TestCase):
    """A cut bin and an upload library that share one project name."""

    def setUp(self):
        self.case = tempfile.mkdtemp(prefix="h3lvm_dual_")
        bin_store.set_base_dir_override(os.path.join(self.case, "bin"))
        upload_store.set_base_dir_override(os.path.join(self.case, "uploads"))

    def tearDown(self):
        bin_store.set_base_dir_override(None)
        upload_store.set_base_dir_override(None)
        shutil.rmtree(self.case, ignore_errors=True)

    def save_bin_segment(self, frames=39, project=PROJECT):
        """One saved segment, written the way the Manager writes it."""
        video = torch.zeros(frames, 24, 32, 3, dtype=torch.float32)
        for index in range(frames):
            video[index] = index / float(frames)
        bin_store.save_segment(project, 1, video, None, 24)
        return frames

    def import_upload(self, path, project=PROJECT):
        """Register a real file through the same path the HTTP route uses."""
        _, partial = upload_store.open_partial(project)
        shutil.copyfile(path, partial)
        return upload_store.import_upload(project, partial, os.path.basename(path))

    def pick(self, segment_id, mode, project=PROJECT):
        out = NODES.H3SegmentPicker.execute(project_name=project, segment_id=segment_id,
                                            source_mode=mode)
        return out.result


@unittest.skipUnless(READY, SKIP_WHY)
class CutBinModeIsUnchanged(_TwoLibraries):
    def test_a_two_widget_workflow_still_reads_the_cut_bin(self):
        frames = self.save_bin_segment()
        video, audio, frame_count, segment_id = self.pick(1, None)
        self.assertEqual(frame_count, frames)
        self.assertEqual(tuple(video.shape), (frames, 24, 32, 3))
        self.assertEqual(segment_id, 1)
        # The silent fallback is part of the old contract: H3 must never get None.
        self.assertIsNotNone(audio["waveform"])

    def test_explicit_segments_mode_is_the_same_code_path(self):
        frames = self.save_bin_segment()
        video, _, frame_count, _ = self.pick(1, "segments")
        self.assertEqual(frame_count, frames)

    def test_a_missing_segment_still_reports_the_cut_bin(self):
        self.save_bin_segment()
        with self.assertRaises(ValueError) as caught:
            self.pick(7, "segments")
        self.assertIn("is not saved in project", str(caught.exception))

    def test_an_unknown_mode_is_refused_instead_of_guessing(self):
        self.save_bin_segment()
        for bad in ("bin", "upload", ""):
            if not bad:
                continue
            with self.assertRaises(ValueError) as caught:
                self.pick(1, bad)
            self.assertIn("素材库模式", str(caught.exception))


@unittest.skipUnless(READY, SKIP_WHY)
class UploadModeOutputs(_TwoLibraries):
    def test_24fps_clip_with_audio_round_trips(self):
        clip = make_clip(os.path.join(self.case, "with_sound.mp4"), fps=24, duration=2.0,
                         audio=True)
        record = self.import_upload(clip)
        video, audio, frame_count, segment_id = self.pick(record["segment_id"], "uploads")

        self.assertEqual(frame_count, 48)
        self.assertEqual(frame_count, video.shape[0])
        self.assertEqual(tuple(video.shape[1:]), CLIP_SHAPE)
        self.assertEqual(video.dtype, torch.float32)
        self.assertGreaterEqual(float(video.min()), 0.0)
        self.assertLessEqual(float(video.max()), 1.0)
        self.assertEqual(audio["waveform"].shape[0], 1)
        played = audio["waveform"].shape[-1] / float(audio["sample_rate"])
        self.assertAlmostEqual(played, frame_count / 24.0, places=2)
        self.assertEqual(segment_id, record["segment_id"])

    def test_a_silent_video_gets_matching_silent_audio(self):
        clip = make_clip(os.path.join(self.case, "silent.mp4"), fps=24, duration=1.0)
        record = self.import_upload(clip)
        video, audio, frame_count, _ = self.pick(record["segment_id"], "uploads")
        self.assertEqual(frame_count, 24)
        self.assertIsNotNone(audio)
        played = audio["waveform"].shape[-1] / float(audio["sample_rate"])
        self.assertAlmostEqual(played, frame_count / 24.0, places=2)

    def test_a_30fps_source_is_sampled_to_24fps(self):
        clip = make_clip(os.path.join(self.case, "thirty.mp4"), fps=30, duration=2.0)
        record = self.import_upload(clip)
        _, _, frame_count, _ = self.pick(record["segment_id"], "uploads")
        self.assertEqual(frame_count, 48)

    def test_a_variable_rate_source_keeps_the_wall_clock(self):
        vfr = make_vfr_clip(os.path.join(self.case, "vfr.mp4"), first_fps=24,
                            second_fps=30, each=1.0, tmpdir=self.case)
        record = self.import_upload(vfr)
        _, _, frame_count, _ = self.pick(record["segment_id"], "uploads")
        self.assertEqual(frame_count, 48)

    def test_uploads_run_without_anything_in_the_cut_bin(self):
        clip = make_clip(os.path.join(self.case, "alone.mp4"), fps=24, duration=1.0)
        record = self.import_upload(clip)
        _, _, frame_count, _ = self.pick(record["segment_id"], "uploads")
        self.assertEqual(frame_count, 24)

    def test_the_same_project_name_is_two_different_clips(self):
        frames = self.save_bin_segment()
        clip = make_clip(os.path.join(self.case, "both.mp4"), fps=24, duration=1.0)
        record = self.import_upload(clip)

        _, _, from_bin, _ = self.pick(1, "segments")
        _, _, from_upload, _ = self.pick(record["segment_id"], "uploads")
        self.assertEqual(from_bin, frames)
        self.assertEqual(from_upload, 24)

    def test_a_missing_card_names_the_upload_library(self):
        upload_store.create_upload_project(PROJECT)
        with self.assertRaises(ValueError) as caught:
            self.pick(3, "uploads")
        self.assertIn("投放视频库", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
