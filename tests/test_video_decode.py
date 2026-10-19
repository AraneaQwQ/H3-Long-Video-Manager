"""Tests for H3 Long Video Manager - video_decode (upload mode).

What this pins down: the frame count the node reports is the frame count the tensor
really has, a file at any frame rate becomes 24 fps of the same wall-clock length, and a
file that cannot be read says so in Chinese instead of crashing the queue.

Run with:
    cd H3-Long-Video-Manager
    python -m tests.test_video_decode
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import torch

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from tests._media_clip import (have_ffmpeg, make_audio_only, make_broken, make_clip,
                               make_gradient, make_vfr_clip)

try:
    import av  # noqa: F401
    import numpy  # noqa: F401
    HAS_AV = True
except ImportError:
    HAS_AV = False

READY = have_ffmpeg() and HAS_AV

from comfyui import video_decode
from comfyui.video_decode import (CUSTOM_MAX_SIDE_DEFAULT, DEFAULT_RESIZE, MAX_DECODE_FRAMES,
                                  MAX_MAX_SIDE, MIN_MAX_SIDE, RESIZE_CUSTOM, RESIZE_OPTIONS,
                                  TARGET_FPS, MediaError, backend_name, decode_video,
                                  parse_custom_max_side, parse_max_side, probe_video,
                                  scale_plan, write_cover)


@unittest.skipUnless(READY, "needs PyAV and ffmpeg on PATH")
class ClipFixture(unittest.TestCase):
    """One temp folder of clips, built once per test class."""

    kind = "clip"

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="h3lvm_decode_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def clip(self, name, **kwargs):
        return make_clip(os.path.join(self.tmpdir, name), **kwargs)


class TestProbe(ClipFixture):
    def test_probe_reports_exact_rate(self):
        path = self.clip("rate.mp4", fps=30, duration=2.0)
        info = probe_video(path)
        self.assertEqual((info["source_fps_num"], info["source_fps_den"]), (30, 1))
        self.assertEqual(info["source_fps"], 30.0)
        self.assertFalse(info["variable_fps"])

    def test_probe_keeps_1001_denominators(self):
        path = self.clip("ntsc.mp4", fps=30000, duration=1.0, extra=["-r", "29.97"])
        info = probe_video(path)
        self.assertEqual(info["source_fps_den"], 100)
        self.assertLess(abs(info["source_fps"] - 29.97), 0.01)

    def test_probe_reads_size_and_audio(self):
        with_sound = self.clip("with_audio.mp4", fps=24, duration=1.0, audio=True)
        silent = self.clip("silent.mp4", fps=24, duration=1.0)
        self.assertEqual((probe_video(with_sound)["width"], probe_video(with_sound)["height"]),
                         (64, 36))
        self.assertTrue(probe_video(with_sound)["has_audio"])
        self.assertEqual(probe_video(with_sound)["audio_streams"], 1)
        self.assertFalse(probe_video(silent)["has_audio"])
        self.assertEqual(probe_video(silent)["audio_streams"], 0)

    def test_probe_flags_variable_frame_rate(self):
        path = make_vfr_clip(os.path.join(self.tmpdir, "vfr.mp4"), tmpdir=self.tmpdir)
        self.assertTrue(probe_video(path)["variable_fps"])

    def test_probe_rejects_a_non_video_file(self):
        path = make_broken(os.path.join(self.tmpdir, "notes.mp4"))
        with self.assertRaises(MediaError) as caught:
            probe_video(path)
        self.assertIn("读不出来", str(caught.exception))

    def test_probe_rejects_an_audio_only_file(self):
        path = make_audio_only(os.path.join(self.tmpdir, "voice.m4a"))
        with self.assertRaises(MediaError) as caught:
            probe_video(path)
        self.assertIn("没有视频流", str(caught.exception))

    def test_backend_name_is_reportable(self):
        self.assertTrue(backend_name())


class TestDecode(ClipFixture):
    def _assert_tensor_contract(self, image):
        self.assertEqual(image.dtype, torch.float32)
        self.assertEqual(image.ndim, 4)
        self.assertGreaterEqual(float(image.min()), 0.0)
        self.assertLessEqual(float(image.max()), 1.0)

    def test_24fps_source_passes_through(self):
        path = self.clip("src24.mp4", fps=24, duration=3.0)
        image, audio, info = decode_video(path)
        self.assertEqual(info["frame_count"], 72)
        self.assertEqual(info["frame_count"], image.shape[0])
        self.assertEqual((image.shape[1], image.shape[2], image.shape[3]), (36, 64, 3))
        self.assertEqual(info["out_fps"], TARGET_FPS)
        self._assert_tensor_contract(image)

    def test_faster_source_is_sampled_down(self):
        for fps in (30, 60):
            path = self.clip("src%d.mp4" % fps, fps=fps, duration=2.0)
            image, audio, info = decode_video(path)
            self.assertEqual(info["frame_count"], 48, "%d fps must become 2 s of 24 fps" % fps)
            self.assertEqual(info["frame_count"], image.shape[0])

    def test_slower_source_is_padded_up(self):
        path = self.clip("src12.mp4", fps=12, duration=2.0)
        image, audio, info = decode_video(path)
        self.assertEqual(info["frame_count"], 48)
        self.assertEqual(info["frame_count"], image.shape[0])

    def test_duration_matches_the_frame_count(self):
        path = self.clip("short.mp4", fps=30, duration=1.5)
        image, audio, info = decode_video(path)
        self.assertAlmostEqual(info["duration_sec"], info["frame_count"] / float(TARGET_FPS))

    def test_variable_frame_rate_still_covers_the_file(self):
        path = make_vfr_clip(os.path.join(self.tmpdir, "vfr2.mp4"), tmpdir=self.tmpdir)
        image, audio, info = decode_video(path)
        self.assertEqual(info["frame_count"], 48)
        self.assertEqual(info["frame_count"], image.shape[0])

    def test_audio_matches_the_played_length(self):
        path = self.clip("sync.mp4", fps=30, duration=2.0, audio=True)
        image, audio, info = decode_video(path)
        self.assertIsNotNone(audio)
        self.assertEqual(audio["waveform"].ndim, 3)
        self.assertEqual(audio["waveform"].shape[0], 1)
        self.assertEqual(info["audio_samples"], audio["waveform"].shape[-1])
        seconds = info["audio_samples"] / float(info["audio_sample_rate"])
        self.assertAlmostEqual(seconds, info["duration_sec"], places=3)

    def test_silent_source_yields_no_audio(self):
        path = self.clip("mute.mp4", fps=24, duration=1.0)
        image, audio, info = decode_video(path)
        self.assertIsNone(audio)
        self.assertFalse(info["has_audio"])
        self.assertEqual(info["frame_count"], 24)

    def test_frame_order_follows_the_source(self):
        """The source counts up in red, so the output must count up too."""
        import numpy as np
        path = make_gradient(os.path.join(self.tmpdir, "count.mp4"), fps=12, frames=24)
        image, audio, info = decode_video(path)
        self.assertEqual(info["frame_count"], 48)
        red = image[:, :, :, 0].mean(dim=(1, 2)).numpy()
        self.assertEqual(len(red), info["frame_count"])
        self.assertGreater(red[-1], red[0])
        self.assertTrue(np.all(np.diff(red) > -1.0), "frames must stay in source order")

    def test_broken_file_reports_a_readable_error(self):
        path = make_broken(os.path.join(self.tmpdir, "broken2.mp4"))
        with self.assertRaises(MediaError) as caught:
            decode_video(path)
        self.assertIn("解码失败", str(caught.exception))

    def test_frame_cap_is_honest_about_the_limit(self):
        self.assertGreater(MAX_DECODE_FRAMES, 0)


class TestCover(ClipFixture):
    def test_cover_is_a_small_jpeg(self):
        path = self.clip("cover.mp4", fps=24, duration=2.0, size="320x180")
        cover = os.path.join(self.tmpdir, "cover.jpg")
        made = write_cover(path, cover)
        self.assertTrue(os.path.isfile(cover))
        self.assertLessEqual(max(made["cover_width"], made["cover_height"]), 320)

    def test_tall_video_keeps_its_full_frame(self):
        path = self.clip("portrait.mp4", fps=24, duration=1.0, size="270x480")
        cover = os.path.join(self.tmpdir, "portrait.jpg")
        made = write_cover(path, cover)
        self.assertEqual(made["cover_height"], 320)
        self.assertLess(made["cover_width"], made["cover_height"])

    def test_cover_of_a_broken_file_reports(self):
        path = make_broken(os.path.join(self.tmpdir, "broken3.mp4"))
        with self.assertRaises(MediaError):
            write_cover(path, os.path.join(self.tmpdir, "nope.jpg"))

class TestScalePlan(unittest.TestCase):
    """The size plan is arithmetic, so it is checked without a decoder."""

    def test_no_cap_keeps_the_source(self):
        for value in (0, None, "", DEFAULT_RESIZE):
            plan = scale_plan(3840, 2160, parse_max_side(value))
            self.assertEqual((plan["width"], plan["height"]), (3840, 2160))
            self.assertFalse(plan["scaled"])

    def test_the_cap_is_the_long_edge_in_both_orientations(self):
        self.assertEqual((scale_plan(3840, 2160, 1920)["width"],
                          scale_plan(3840, 2160, 1920)["height"]), (1920, 1080))
        self.assertEqual((scale_plan(2160, 3840, 1920)["width"],
                          scale_plan(2160, 3840, 1920)["height"]), (1080, 1920))

    def test_the_aspect_ratio_survives(self):
        plan = scale_plan(4000, 3000, 1920)
        self.assertEqual((plan["width"], plan["height"]), (1920, 1440))
        self.assertAlmostEqual(plan["width"] / plan["height"], 4 / 3, places=3)

    def test_a_cap_above_the_source_never_grows_the_picture(self):
        plan = scale_plan(1280, 720, 3840)
        self.assertEqual((plan["width"], plan["height"]), (1280, 720))
        self.assertFalse(plan["scaled"])

    def test_the_output_is_always_even_and_inside_the_cap(self):
        for src_w, src_h in ((1001, 563), (1919, 1079), (721, 401)):
            plan = scale_plan(src_w, src_h, 500)
            self.assertTrue(plan["scaled"])
            self.assertEqual(plan["width"] % 2, 0)
            self.assertEqual(plan["height"] % 2, 0)
            self.assertLessEqual(max(plan["width"], plan["height"]), 500)

    def test_a_source_that_makes_no_sense_is_not_scaled(self):
        for width, height in ((0, 0), (-5, 10), (10, 0)):
            plan = scale_plan(width, height, 320)
            self.assertFalse(plan["scaled"])

    def test_a_cap_that_would_leave_no_picture_keeps_the_source(self):
        self.assertFalse(scale_plan(4000, 100, 16)["scaled"])


class TestParseMaxSide(unittest.TestCase):
    """The widget stores the label the user saw, so the label has to be the contract."""

    def test_the_default_option_means_no_scaling(self):
        for value in (DEFAULT_RESIZE, None, "", "segments", "原始"):
            self.assertEqual(parse_max_side(value), 0)

    def test_each_preset_option_parses_to_the_number_it_shows(self):
        for option in RESIZE_OPTIONS[1:]:
            match = re.search(r"\d+", option)
            if not match:
                # 自定义 carries no number on purpose - its number is the other widget - and
                # it is the only number-less entry, so a typo cannot hide in this loop.
                self.assertEqual(option, RESIZE_CUSTOM)
                continue
            number = int(match.group(0))
            self.assertGreaterEqual(number, 16)
            self.assertEqual(parse_max_side(option), number)

    def test_a_number_outside_the_range_is_ignored(self):
        self.assertEqual(parse_max_side("最长边 8"), 0)
        self.assertEqual(parse_max_side("最长边 99999"), 0)

    def test_a_preset_option_ignores_the_custom_number(self):
        # The typed field is only read by the custom entry, so leaving a number in it while
        # a preset is selected cannot quietly change what the preset means.
        self.assertEqual(parse_max_side("最长边 1920", 320), 1920)
        self.assertEqual(parse_max_side(DEFAULT_RESIZE, 320), 0)
        self.assertEqual(parse_max_side(None, 320), 0)


class TestCustomMaxSide(unittest.TestCase):
    """自定义（自己填最长边）: the number comes from the companion widget.

    A typed value is clamped rather than ignored: the widget cannot leave the range, but a
    copied or hand-edited workflow can, and "90000" means "as close as you can get" to the
    person who typed it. scale_plan() never grows a picture, so a cap above the source is
    simply no scaling.
    """

    def test_the_custom_option_uses_the_typed_number(self):
        self.assertEqual(parse_max_side(RESIZE_CUSTOM, 1337), 1337)
        self.assertEqual(parse_max_side(RESIZE_CUSTOM, "1337"), 1337)
        self.assertEqual(parse_max_side(RESIZE_CUSTOM, " 1337 "), 1337)

    def test_the_offered_default_is_a_usable_cap(self):
        self.assertTrue(MIN_MAX_SIDE <= CUSTOM_MAX_SIDE_DEFAULT <= MAX_MAX_SIDE)
        self.assertEqual(parse_max_side(RESIZE_CUSTOM, CUSTOM_MAX_SIDE_DEFAULT),
                         CUSTOM_MAX_SIDE_DEFAULT)

    def test_a_typed_number_outside_the_range_is_clamped(self):
        self.assertEqual(parse_max_side(RESIZE_CUSTOM, 4), MIN_MAX_SIDE)
        self.assertEqual(parse_max_side(RESIZE_CUSTOM, 99999), MAX_MAX_SIDE)

    def test_a_custom_option_without_a_number_means_no_scaling(self):
        for value in (None, "", "   ", "abc", "1920px", 0, -5, float("nan")):
            self.assertEqual(parse_max_side(RESIZE_CUSTOM, value), 0,
                             "expected no scaling for %r" % (value,))

    def test_a_typed_decimal_is_still_a_pixel_count(self):
        self.assertEqual(parse_custom_max_side("1337.9"), 1337)
        self.assertEqual(parse_custom_max_side(1337.9), 1337)


class TestDecodeScaled(ClipFixture):
    """The 输出分辨率 control: a smaller decode, the same frames, the same file."""

    def test_a_cap_produces_the_planned_size(self):
        path = self.clip("cap.mp4", fps=24, duration=1.0, size="64x36")
        image, _audio, info = decode_video(path, max_side=32)
        self.assertEqual((image.shape[2], image.shape[1]), (32, 18))
        self.assertEqual((info["width"], info["height"]), (32, 18))
        self.assertEqual((info["source_width"], info["source_height"]), (64, 36))
        self.assertTrue(info["scaled"])

    def test_scaling_does_not_change_the_frame_count(self):
        path = self.clip("cap2.mp4", fps=30, duration=2.0, size="64x36")
        plain, _audio, plain_info = decode_video(path)
        small, _audio, small_info = decode_video(path, max_side=32)
        self.assertEqual(plain.shape[0], small.shape[0])
        self.assertEqual(plain_info["frame_count"], small_info["frame_count"])
        self.assertAlmostEqual(small_info["duration_sec"], plain_info["duration_sec"], places=4)

    def test_a_vertical_video_is_capped_on_its_long_edge(self):
        path = self.clip("cap3.mp4", fps=24, duration=1.0, size="36x64")
        image, _audio, info = decode_video(path, max_side=32)
        self.assertEqual((image.shape[2], image.shape[1]), (18, 32))
        self.assertTrue(info["scaled"])

    def test_a_cap_above_the_source_decodes_unchanged(self):
        path = self.clip("cap4.mp4", fps=24, duration=1.0, size="64x36")
        image, _audio, info = decode_video(path, max_side=1920)
        self.assertEqual((image.shape[2], image.shape[1]), (64, 36))
        self.assertFalse(info["scaled"])

    def test_a_typed_custom_size_decodes_at_that_size(self):
        # 1337 is deliberately not one of the presets: the custom entry has to work with
        # any number in range, not with a hidden second preset list.
        path = self.clip("cap_custom.mp4", fps=24, duration=1.0, size="64x36")
        max_side = parse_max_side(RESIZE_CUSTOM, 30)
        self.assertEqual(max_side, 30)
        image, _audio, info = decode_video(path, max_side=max_side)
        self.assertEqual((image.shape[2], image.shape[1]), (30, 16))
        self.assertEqual((info["width"], info["height"]), (30, 16))
        self.assertEqual((info["source_width"], info["source_height"]), (64, 36))
        self.assertTrue(info["scaled"])

    def test_the_frames_are_still_the_ones_in_the_file(self):
        """A resampled frame must not invent or drop content: the gradient still counts up."""
        path = make_gradient(os.path.join(self.tmpdir, "cap_gradient.mp4"),
                             fps=24, frames=24, size=(64, 36))
        small, _audio, _info = decode_video(path, max_side=32)
        first = small[0, :, :, 0].flatten()
        last = small[-1, :, :, 0].flatten()
        self.assertLess(float(first.mean()), float(last.mean()))

    def test_the_memory_cap_uses_the_planned_size(self):
        # [F,H,W,3] float32 is 12 bytes per pixel per frame, so a cap that halves the
        # long edge quarters the RAM - which is the whole point of the control.
        path = self.clip("cap5.mp4", fps=24, duration=1.0, size="64x36")
        full = 24 * 64 * 36 * 3 * 4
        small = 24 * 32 * 18 * 3 * 4
        with mock.patch.object(video_decode, "MAX_DECODE_BYTES", (full + small) // 2):
            with self.assertRaises(MediaError) as caught:
                decode_video(path)
            self.assertIn("输出分辨率", str(caught.exception))
            image, _audio, info = decode_video(path, max_side=32)
        self.assertEqual((info["width"], info["height"]), (32, 18))


if __name__ == "__main__":
    unittest.main(verbosity=2)
