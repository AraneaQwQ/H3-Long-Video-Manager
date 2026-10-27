"""Streaming media primitives used only by the v2 file-based producers."""
from __future__ import annotations

import logging
import shutil
import subprocess
from fractions import Fraction
from typing import Iterator, Optional, Tuple

import numpy as np
import torch

from .playback_audio import _slowdown_audio
from .video_decode import (
    MAX_DECODE_FRAMES,
    TARGET_FPS,
    MediaError,
    _audio_to_channels,
    _av,
    _ffmpeg_errors,
    _frame_seconds,
    _frame_span,
    _interpolation,
    _rate_pair,
    probe_video,
)

logger = logging.getLogger(__name__)


class _FFmpegUnavailable(Exception):
    pass


def _read_into(stream, array):
    view = memoryview(array).cast("B")
    received = 0
    while received < view.nbytes:
        count = stream.readinto(view[received:])
        if not count:
            break
        received += count
    return received


def _iter_ffmpeg_frames(path, width, height):
    """CFR-only fast path; fps round=up matches the established PyAV timeline."""
    frame_size = int(width) * int(height) * 3
    command = [
        shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin",
        "-i", path, "-map", "0:v:0", "-vf", "setpts=PTS-STARTPTS,fps=24:round=up",
        "-an", "-sn", "-dn", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise _FFmpegUnavailable(str(exc)) from exc
    try:
        for _index in range(MAX_DECODE_FRAMES):
            array = np.empty((int(height), int(width), 3), dtype=np.uint8)
            received = _read_into(process.stdout, array)
            if not received:
                code = process.wait()
                if code:
                    detail = process.stderr.read().decode("utf-8", "replace").strip()[-1200:]
                    raise MediaError(f"FFmpeg 流式解码失败：{detail or f'退出码 {code}'}")
                return
            if received != frame_size:
                raise MediaError("FFmpeg 流式解码提前结束，最后一帧不完整。")
            yield torch.from_numpy(array)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()
        process.stderr.close()


def iter_video_frames(
    path: str,
    target_fps: int = TARGET_FPS,
    target_size: Optional[Tuple[int, int]] = None,
    source_info=None,
) -> Iterator[torch.Tensor]:
    """Choose the exact CFR fast path, or retain the general PyAV decoder."""
    use_ffmpeg = target_fps == TARGET_FPS and shutil.which("ffmpeg")
    info = None
    if use_ffmpeg:
        info = source_info or probe_video(path)
        original_size = (int(info["width"]), int(info["height"]))
        use_ffmpeg = not info.get("variable_fps") and (
            target_size is None or tuple(target_size) == original_size)
    if use_ffmpeg:
        fast = _iter_ffmpeg_frames(path, original_size[0], original_size[1])
        try:
            first = next(fast)
        except StopIteration:
            return
        except (MediaError, _FFmpegUnavailable) as exc:
            logger.info("[H3 v2] FFmpeg fast path unavailable, using PyAV: %s", exc)
        else:
            logger.info("[H3 v2] video backend: FFmpeg rawvideo (CFR, original size)")
            yield first
            yield from fast
            return
    yield from _iter_pyav_frames(path, target_fps=target_fps, target_size=target_size)


def _iter_pyav_frames(
    path: str,
    target_fps: int = TARGET_FPS,
    target_size: Optional[Tuple[int, int]] = None,
) -> Iterator[torch.Tensor]:
    """Yield the 24 fps timeline as uint8 RGB frames, never a whole-video tensor."""
    av = _av()
    try:
        container = av.open(path)
    except _ffmpeg_errors(av) as exc:
        raise MediaError("解码失败：这个视频读不出来（%s）。" % (getattr(exc, "message", exc))) from exc
    try:
        stream = container.streams.video[0]
        num, den = _rate_pair(stream)
        source_rate = Fraction(num, den) if num and den else None
        source_width, source_height = int(stream.width), int(stream.height)
        width, height = target_size or (source_width, source_height)
        width, height = int(width), int(height)
        if width <= 0 or height <= 0:
            raise MediaError("输出分辨率无效。")

        def pixels(frame) -> np.ndarray:
            if (width, height) == (source_width, source_height):
                return frame.to_ndarray(format="rgb24")
            kwargs = {"width": width, "height": height, "format": "rgb24"}
            interpolation = _interpolation(width <= source_width and height <= source_height)
            if interpolation is not None:
                kwargs["interpolation"] = interpolation
            return frame.reformat(**kwargs).to_ndarray(format="rgb24")

        filled = 0
        origin = None
        index = 0
        shape = None
        for frame in container.decode(video=0):
            seconds = _frame_seconds(frame, stream, index, source_rate)
            index += 1
            if origin is None:
                origin = seconds
            span = _frame_span(frame, stream, source_rate, target_fps)
            import math
            target = int(math.ceil((seconds + span - origin) * target_fps - 1e-6))
            if target <= filled:
                continue
            if (int(getattr(frame, "width", source_width)) != source_width
                    or int(getattr(frame, "height", source_height)) != source_height):
                raise MediaError("这个视频在播放过程中改变了分辨率，无法作为一段连续输出。")
            array = pixels(frame)
            if shape is None:
                shape = array.shape
            elif tuple(array.shape) != tuple(shape):
                raise MediaError("这个视频在播放过程中改变了分辨率，无法作为一段连续输出。")
            tensor = torch.from_numpy(array)
            while filled < target:
                yield tensor
                filled += 1
                if filled >= MAX_DECODE_FRAMES:
                    break
            if filled >= MAX_DECODE_FRAMES:
                break
    finally:
        container.close()


def stack_uint8(frames) -> torch.Tensor:
    """Stack one segment without first expanding every frame to float32."""
    if not frames:
        raise ValueError("片段没有视频帧。")
    return torch.stack(frames) if len(frames) > 1 else frames[0].unsqueeze(0)


def decode_audio_range(
    path: str,
    start_frame: int,
    frame_count: int,
    target_fps: int = TARGET_FPS,
    playback_speed: float = 1.0,
):
    """Seek and decode one segment's audio; pad only this segment to the video length."""
    speed = float(playback_speed)
    if not 0 < speed <= 1.0:
        raise ValueError("playback_speed must be in (0, 1]")
    av = _av()
    try:
        container = av.open(path)
    except _ffmpeg_errors(av):
        return None
    try:
        streams = list(container.streams.audio)
        if not streams:
            return None
        stream = streams[0]
        rate = int(getattr(stream, "rate", 0) or 44100)
        start_seconds = max(0.0, float(start_frame) * speed / float(target_fps))
        source_frames = float(frame_count) * speed
        end_seconds = start_seconds + source_frames / float(target_fps)
        target_samples = max(1, int(source_frames / float(target_fps) * rate))
        layout = getattr(getattr(stream, "layout", None), "name", None)
        try:
            resampler = (av.AudioResampler(format="s16p", layout=layout, rate=rate) if layout
                         else av.AudioResampler(format="s16p", rate=rate))
        except (AttributeError, TypeError, ValueError):
            resampler = None
        if start_seconds > 0 and getattr(stream, "time_base", None):
            offset = int(start_seconds / float(stream.time_base))
            try:
                container.seek(max(0, offset), stream=stream, backward=True)
            except _ffmpeg_errors(av):
                container.seek(0, stream=stream, backward=True)

        chunks = []
        first_seconds = None
        collected = 0
        stop = False
        for frame in container.decode(audio=0):
            pieces = [frame] if resampler is None else list(resampler.resample(frame))
            for piece in pieces:
                try:
                    data = _audio_to_channels(piece)
                except Exception:
                    data = None
                if data is None:
                    continue
                if first_seconds is None:
                    time_base = getattr(piece, "time_base", None) or getattr(stream, "time_base", None)
                    pts = getattr(piece, "pts", None)
                    if pts is not None and time_base:
                        first_seconds = float(pts * time_base)
                chunks.append(data)
                collected += int(data.shape[1])
                if first_seconds is not None and first_seconds + collected / float(rate) >= end_seconds:
                    stop = True
                    break
            if stop:
                break
        if not chunks:
            return None
        channels = max(int(chunk.shape[0]) for chunk in chunks)
        aligned = [
            chunk if chunk.shape[0] == channels else np.zeros(
                (channels, chunk.shape[1]), dtype=chunk.dtype)
            for chunk in chunks
        ]
        samples = np.concatenate(aligned, axis=1)
        target_start = int(start_seconds * rate)
        source_start = (int(round(first_seconds * rate)) if first_seconds is not None
                        else target_start)
        source_end = source_start + int(samples.shape[1])
        target_end = target_start + target_samples
        overlap_start = max(target_start, source_start)
        overlap_end = min(target_end, source_end)
        output = np.zeros((channels, target_samples), dtype=np.int16)
        if overlap_end > overlap_start:
            destination = overlap_start - target_start
            source = overlap_start - source_start
            length = overlap_end - overlap_start
            output[:, destination:destination + length] = samples[:, source:source + length]
        waveform = torch.from_numpy(np.ascontiguousarray(output.astype(np.float32) / 32768.0))
        result = {"waveform": waveform.unsqueeze(0), "sample_rate": rate}
        if speed < 1.0:
            result = _slowdown_audio(result, speed)
            slowed_samples = max(1, int(int(frame_count) / float(target_fps) * rate))
            slowed = result["waveform"]
            if slowed.shape[-1] > slowed_samples:
                slowed = slowed[..., :slowed_samples]
            elif slowed.shape[-1] < slowed_samples:
                slowed = torch.nn.functional.pad(
                    slowed, (0, slowed_samples - slowed.shape[-1]))
            result["waveform"] = slowed.contiguous()
        return result
    finally:
        container.close()


def silent_audio(frame_count: int, target_fps: int = TARGET_FPS):
    samples = max(1, int(int(frame_count) / float(target_fps) * 44100))
    return {"waveform": torch.zeros(1, 1, samples), "sample_rate": 44100}


__all__ = ["decode_audio_range", "iter_video_frames", "silent_audio", "stack_uint8"]
