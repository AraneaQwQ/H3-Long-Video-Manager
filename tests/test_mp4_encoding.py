"""MP4 preview encoding keeps ffmpeg output unchanged without whole-video byte copies."""

import os
import shutil
import subprocess
import unittest
from unittest import mock

import torch

from comfyui import segment_store
from tests._media_clip import have_ffmpeg
from tests._temp_dir import make_temp_dir

try:
    import av
    HAS_AV = True
except ImportError:
    HAS_AV = False


class _TrackedStdin:
    def __init__(self, stream, writes):
        self.stream = stream
        self.writes = writes

    def write(self, data):
        self.writes.append(len(data))
        return self.stream.write(data)

    def close(self):
        return self.stream.close()


class _FakeProcess:
    def __init__(self, returncode=0, broken_pipe=False):
        self.returncode = returncode
        self.stdin = mock.Mock()
        self.stdin.write.side_effect = BrokenPipeError("closed") if broken_pipe else None
        self.wait_calls = 0
        self.kill_calls = 0

    def wait(self):
        self.wait_calls += 1
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        self.kill_calls += 1
        self.returncode = -9


@unittest.skipUnless(have_ffmpeg() and HAS_AV and shutil.which("ffmpeg"),
                     "needs PyAV and ffmpeg on PATH")
class TestMp4Encoding(unittest.TestCase):
    def setUp(self):
        self.tmpdir = make_temp_dir("h3lvm_mp4_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_packed_video_is_encoded_in_bounded_chunks(self):
        frames = torch.empty(10, 16, 32, 3, dtype=torch.float32)
        for index in range(10):
            frames[index].fill_((index + 1) / 20.0)
        packed = segment_store._encode_video(frames, "int8")
        audio = {"waveform": torch.zeros(1, 1, 24000), "sample_rate": 24000}
        output = os.path.join(self.tmpdir, "preview.mp4")
        writes = []
        real_popen = subprocess.Popen

        def tracked_popen(cmd, **kwargs):
            self.assertEqual(kwargs.get("stdout"), subprocess.DEVNULL)
            self.assertEqual(kwargs.get("stderr"), subprocess.DEVNULL)
            proc = real_popen(cmd, **kwargs)
            proc.stdin = _TrackedStdin(proc.stdin, writes)
            return proc

        with mock.patch.object(segment_store.subprocess, "Popen", side_effect=tracked_popen):
            self.assertTrue(segment_store._encode_mp4(packed, audio, 24, output))

        frame_bytes = 16 * 32 * 3
        self.assertEqual(writes, [8 * frame_bytes, 2 * frame_bytes])
        with av.open(output) as container:
            self.assertEqual(len(container.streams.audio), 1)
            decoded = [frame.to_ndarray(format="rgb24")
                       for frame in container.decode(video=0)]
        self.assertEqual(len(decoded), 10)
        expected = segment_store._decode_video(packed[:1]).mean().item()
        self.assertAlmostEqual(decoded[0].mean() / 255.0, expected, delta=0.03)
        self.assertAlmostEqual(decoded[-1].mean() / 255.0, 0.5, delta=0.03)


class TestMp4FailureCleanup(unittest.TestCase):
    def test_nonzero_ffmpeg_exit_is_a_failed_encode(self):
        proc = _FakeProcess(returncode=1)
        with mock.patch.object(segment_store.shutil, "which", return_value="ffmpeg"), \
                mock.patch.object(segment_store.subprocess, "Popen", return_value=proc):
            self.assertFalse(segment_store._encode_mp4(
                torch.zeros(1, 2, 2, 3), None, 24, "unused.mp4"))
        self.assertEqual(proc.wait_calls, 1)
        self.assertEqual(proc.kill_calls, 0)
        proc.stdin.close.assert_called_once_with()

    def test_broken_pipe_kills_and_reaps_a_stuck_process(self):
        proc = _FakeProcess(returncode=None, broken_pipe=True)
        with mock.patch.object(segment_store.shutil, "which", return_value="ffmpeg"), \
                mock.patch.object(segment_store.subprocess, "Popen", return_value=proc):
            self.assertFalse(segment_store._encode_mp4(
                torch.zeros(1, 2, 2, 3), None, 24, "unused.mp4"))
        self.assertEqual(proc.kill_calls, 1)
        self.assertEqual(proc.wait_calls, 1)
        proc.stdin.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
