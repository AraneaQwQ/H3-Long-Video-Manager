"""Streaming decoder equivalence with the established whole-file decoder."""
from __future__ import annotations

import os
import shutil
import unittest
from unittest import mock

import torch

from comfyui import stream_video
from comfyui.stream_video import decode_audio_range, iter_video_frames, silent_audio, stack_uint8
from comfyui.video_decode import decode_video
from tests._media_clip import have_ffmpeg, make_clip, make_stereo_clip, make_vfr_clip
from tests._temp_dir import make_temp_dir

try:
    import av  # noqa: F401
    HAS_AV = True
except ImportError:
    HAS_AV = False


@unittest.skipUnless(HAS_AV and have_ffmpeg(), "needs PyAV and ffmpeg")
class TestStreamVideo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = make_temp_dir(prefix="h3lvm_stream_video_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def assert_same_video(self, path):
        expected, _audio, _info = decode_video(path)
        streamed = stack_uint8(list(iter_video_frames(path)))
        actual = streamed.to(torch.float32).div(255.0)
        self.assertEqual(actual.shape, expected.shape)
        self.assertTrue(torch.allclose(actual, expected, rtol=0.0, atol=1e-7))

    def test_60fps_stream_matches_whole_decode(self):
        self.assert_same_video(make_clip(os.path.join(self.tmpdir, "60.mp4"), fps=60, duration=2.0))

    def test_12fps_stream_matches_whole_decode(self):
        self.assert_same_video(make_clip(os.path.join(self.tmpdir, "12.mp4"), fps=12, duration=2.0))

    def test_vfr_stream_matches_whole_decode(self):
        path = make_vfr_clip(os.path.join(self.tmpdir, "vfr.mp4"), tmpdir=self.tmpdir)
        self.assert_same_video(path)

    def test_scaling_happens_per_frame(self):
        path = make_clip(os.path.join(self.tmpdir, "scale.mp4"), fps=60, duration=1.0, size="128x72")
        frames = list(iter_video_frames(path, target_size=(64, 36)))
        self.assertEqual(len(frames), 24)
        self.assertEqual(frames[0].shape, (36, 64, 3))
        self.assertEqual(frames[0].dtype, torch.uint8)

    def test_cfr_original_size_uses_ffmpeg_but_scaling_keeps_pyav(self):
        path = make_clip(os.path.join(self.tmpdir, "backend.mp4"), fps=60, duration=1.0)
        with (mock.patch.object(stream_video, "_iter_ffmpeg_frames",
                                wraps=stream_video._iter_ffmpeg_frames) as fast,
              mock.patch.object(stream_video, "_iter_pyav_frames",
                                wraps=stream_video._iter_pyav_frames) as fallback):
            self.assertEqual(len(list(iter_video_frames(path))), 24)
            fast.assert_called_once()
            fallback.assert_not_called()
            fast.reset_mock()
            self.assertEqual(len(list(iter_video_frames(path, target_size=(32, 18)))), 24)
            fast.assert_not_called()
            fallback.assert_called_once()

    def test_vfr_never_uses_the_cfr_fast_path(self):
        path = make_vfr_clip(os.path.join(self.tmpdir, "backend-vfr.mp4"), tmpdir=self.tmpdir)
        with (mock.patch.object(stream_video, "_iter_ffmpeg_frames") as fast,
              mock.patch.object(stream_video, "_iter_pyav_frames",
                                wraps=stream_video._iter_pyav_frames) as fallback):
            self.assertEqual(len(list(iter_video_frames(path))), 48)
            fast.assert_not_called()
            fallback.assert_called_once()

    def test_missing_ffmpeg_falls_back_to_pyav(self):
        path = make_clip(os.path.join(self.tmpdir, "no-ffmpeg.mp4"), fps=60, duration=1.0)
        with (mock.patch.object(stream_video.shutil, "which", return_value=None),
              mock.patch.object(stream_video, "_iter_pyav_frames",
                                wraps=stream_video._iter_pyav_frames) as fallback):
            self.assertEqual(len(list(iter_video_frames(path))), 24)
            fallback.assert_called_once()

    def test_ffmpeg_start_failure_also_falls_back(self):
        path = make_clip(os.path.join(self.tmpdir, "ffmpeg-start-failure.mp4"), duration=1.0)
        with mock.patch.object(stream_video.subprocess, "Popen", side_effect=OSError("blocked")):
            frames = list(iter_video_frames(path))
        self.assertEqual(len(frames), 24)
        expected, _audio, _info = decode_video(path)
        actual = stack_uint8(frames).to(torch.float32).div(255.0)
        self.assertTrue(torch.allclose(actual, expected, rtol=0.0, atol=1e-7))

    def test_audio_range_has_exact_requested_length(self):
        path = make_clip(os.path.join(self.tmpdir, "audio.mp4"), fps=60, duration=3.0, audio=True)
        audio = decode_audio_range(path, 24, 48)
        self.assertIsNotNone(audio)
        self.assertEqual(audio["waveform"].shape[-1], 2 * audio["sample_rate"])
        self.assertGreater(float(audio["waveform"].abs().max()), 0.1)

    def test_half_speed_audio_has_slowed_duration_and_keeps_samples(self):
        path = make_clip(os.path.join(self.tmpdir, "audio-slow.mp4"), fps=24, duration=3.0, audio=True)
        audio = decode_audio_range(path, 24, 48, playback_speed=0.5)
        self.assertIsNotNone(audio)
        self.assertEqual(audio["waveform"].shape[-1], 2 * audio["sample_rate"])
        self.assertGreater(float(audio["waveform"].abs().max()), 0.1)
        wave = audio["waveform"][0, 0]
        crossings = int(((wave[:-1] <= 0) & (wave[1:] > 0)).sum())
        seconds = audio["waveform"].shape[-1] / float(audio["sample_rate"])
        self.assertAlmostEqual(crossings / seconds, 440, delta=20)

    def test_stereo_audio_range_keeps_channels_and_pitch(self):
        path = make_stereo_clip(os.path.join(self.tmpdir, "stereo.mp4"), duration=3.0)
        audio = decode_audio_range(path, 24, 48)
        self.assertEqual(audio["waveform"].shape[:2], (1, 2))
        seconds = audio["waveform"].shape[-1] / float(audio["sample_rate"])
        for channel, expected in enumerate((440, 880)):
            wave = audio["waveform"][0, channel]
            crossings = int(((wave[:-1] <= 0) & (wave[1:] > 0)).sum())
            self.assertAlmostEqual(crossings / seconds, expected, delta=15)

    def test_silent_audio_matches_segment_duration(self):
        audio = silent_audio(141)
        self.assertEqual(audio["waveform"].shape[-1], int(141 / 24 * 44100))


if __name__ == "__main__":
    unittest.main()
