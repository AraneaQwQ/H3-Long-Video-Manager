"""Synthetic video files for the upload/decode tests.

The decode tests need real containers with a known frame rate, audio track, and duration -
a hand-written byte stub cannot prove that sampling is correct. ffmpeg is already a runtime
dependency of the segment store (mp4 previews), so the tests use the same binary and skip
themselves when it is missing.
"""
from __future__ import annotations

import os
import shutil
import subprocess

FFMPEG = shutil.which("ffmpeg")


def have_ffmpeg() -> bool:
    return bool(FFMPEG)


def make_clip(path: str, fps: int = 24, duration: float = 1.0, audio: bool = False,
              size: str = "64x36", extra=None) -> str:
    """Write one playable clip; frame content comes from lavfi testsrc."""
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi",
           "-i", "testsrc=duration=%s:size=%s:rate=%s" % (duration, size, fps)]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=%s" % duration]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "aac"] if audio else ["-an"]
    if extra:
        cmd += list(extra)
    cmd += [path]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return path


def make_gradient(path: str, fps: int = 24, frames: int = 48, size=(64, 36)) -> str:
    """A clip whose red channel counts up with the frame number.

    lavfi testsrc is not monotonic in brightness, so an ordering test needs a source it
    can actually predict. PyAV writes this one without ffmpeg on PATH.
    """
    import av
    import numpy as np

    width, height = size
    container = av.open(path, "w", format="mp4")
    stream = container.add_stream("h264", rate=fps)
    stream.width, stream.height, stream.pix_fmt = width, height, "yuv420p"
    for index in range(frames):
        array = np.zeros((height, width, 3), dtype=np.uint8)
        array[:, :, 0] = index * 255 // max(frames - 1, 1)
        frame = av.VideoFrame.from_ndarray(array, format="rgb24")
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()
    return path


def make_vfr_clip(path: str, first_fps: int = 24, second_fps: int = 30,
                  each: float = 1.0, tmpdir: str = ".") -> str:
    """Concatenate two constant-rate parts so the container reports two rates."""
    a = os.path.join(tmpdir, "vfr_part_a.mp4")
    b = os.path.join(tmpdir, "vfr_part_b.mp4")
    make_clip(a, fps=first_fps, duration=each)
    make_clip(b, fps=second_fps, duration=each)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", a, "-i", b,
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
                    "-map", "[v]", "-fps_mode", "vfr", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", path],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return path


def make_audio_only(path: str, duration: float = 1.0) -> str:
    """A file with sound but no picture - a plausible wrong drop on the upload card."""
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi",
           "-i", "sine=frequency=440:duration=%s" % duration, "-c:a", "aac", path]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return path


def make_broken(path: str) -> str:
    """Bytes that are not a media file at all."""
    with open(path, "wb") as stream:
        stream.write(b"this is not a video, it is a sentence")
    return path


__all__ = ["FFMPEG", "have_ffmpeg", "make_clip", "make_gradient", "make_vfr_clip", "make_audio_only",
           "make_broken"]
