"""Probe and decode an uploaded video - the two moments where bytes become a tensor.

Two very different jobs share this module:

  import  probe_video() + write_cover()   a few frames only, for the card
  run     decode_video()                  the selected video, at execution time

Nothing here is cached. A 40 s clip is a few hundred frames of float32; keeping one per
project in memory would cost more than the video files on disk.

Frame-rate decision (planning doc section 6): the H3 workflow expects 24 fps, so the file
on disk is never touched and the sampling happens here, from presentation timestamps. That
is what makes a variable-frame-rate file come out at the right wall-clock timing instead of
"nb_frames divided by a guessed rate". A 24 fps source is passed through frame by frame.
No 17n+5 alignment, no black padding, no silent trimming - the frame count is reported as
it is and the card says so.

Resolution decision: the file on disk is stored byte for byte, so a size reduction can only
ever happen here. The Picker's output-size control caps the long side while frames are
decoded, which is what keeps a 4K file from costing 8 MB of RAM per frame - and the card
says what the decode will produce.
"""
from __future__ import annotations

import logging
import math
import os
import re
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch

logger = logging.getLogger(__name__)

# The MiniMax H3 convention. The stored file keeps its own rate; only the tensor uses this.
TARGET_FPS = 24

# Card covers are thumbnails, not previews.
COVER_MAX_EDGE = 320

# [F,H,W,3] float32 is 12 bytes per pixel per frame. Refusing a 4K clip that needs more
# RAM than the machine has is kinder than being killed while building it.
MAX_DECODE_BYTES = 12 * 1024 ** 3

# A hard frame ceiling, so a file with a wrong duration header cannot loop forever.
MAX_DECODE_FRAMES = 200_000

# ---------------------------------------------------------------------------
# Output size (the Picker's 输出分辨率 control)
# ---------------------------------------------------------------------------

# A 4K frame is 8 MB of float32 before anything looks at it, and the H3 encoder downscales
# the frames anyway. So the Picker may ask for a smaller decode. The stored file is never
# touched - this is a decode-time cap, not a transcode.
#
# The option list lives here so the node widget, the card labels and the tests cannot
# disagree about what is offered. The number in each label is the long side in pixels,
# which is the one reading that means the same thing for a 16:9 and a 9:16 file.
#
# The last entry carries no number on purpose: it points at the companion custom_max_side
# widget, where the user types their own long side. A preset list alone forces a choice
# between 1280 and 960 when someone already knows the size they want.
RESIZE_ORIGINAL = "原始（不缩放）"
RESIZE_CUSTOM = "自定义（自己填最长边）"
RESIZE_OPTIONS = [
    RESIZE_ORIGINAL, "最长边 3840", "最长边 1920", "最长边 1280",
    "最长边 960", "最长边 640", "最长边 480", RESIZE_CUSTOM,
]
DEFAULT_RESIZE = RESIZE_ORIGINAL

# Outside this range the option is a mistake rather than a choice, and decoding at the
# source size is the safe answer for a workflow saved before the control existed.
MIN_MAX_SIDE = 16
MAX_MAX_SIDE = 8192

# A typed number needs a default; 1920 is the cap that makes 4K material cheap, which is
# the reason anyone opens the custom field in the first place.
CUSTOM_MAX_SIDE_DEFAULT = 1920


def parse_custom_max_side(value) -> int:
    """The typed long side, clamped into the supported range; 0 means "decode as-is".

    The widget cannot leave the range, but a hand-edited or copied workflow can, and a
    typed 10000 or 4 means "as close to what I asked for as possible" to a person - so it
    is clamped rather than ignored. Nothing here can grow a picture: scale_plan() only
    ever shrinks, so a cap above the source simply leaves it alone.
    """
    try:
        limit = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0
    if limit <= 0:
        return 0
    return min(max(limit, MIN_MAX_SIDE), MAX_MAX_SIDE)


def parse_max_side(value, custom_max_side=None) -> int:
    """The long-side limit a widget value asks for; 0 means "decode as-is".

    The number is read out of the label because the label is what the user sees and what a
    saved workflow stores. Anything unrecognised - including no value at all - is 0, which
    is the behaviour every existing workflow expects.

    自定义（自己填最长边） has no number in its label, so the number comes from the
    companion widget instead; without one it means no scaling, like every older workflow.
    """
    text = str(value if value is not None else "").strip()
    if not text or text == RESIZE_ORIGINAL:
        return 0
    if text == RESIZE_CUSTOM:
        return parse_custom_max_side(custom_max_side)
    match = re.search(r"\d+", text)
    if not match:
        return 0
    limit = int(match.group(0))
    return limit if MIN_MAX_SIDE <= limit <= MAX_MAX_SIDE else 0


def scale_plan(width, height, max_side) -> Dict[str, Any]:
    """Plan the output size for one source: same aspect ratio, never bigger than the cap.

    Even numbers only. An odd width or height survives in a tensor but not in the H.264 a
    downstream node will encode, and rounding down 1 px is invisible. Nothing ever grows:
    a cap above the source size means "leave it alone", so a small file is not resampled
    for nothing.
    """
    src_w, src_h = int(width or 0), int(height or 0)
    limit = int(max_side or 0)
    plan = {"source_width": src_w, "source_height": src_h, "max_side": limit,
            "width": src_w, "height": src_h, "scaled": False}
    if src_w <= 0 or src_h <= 0 or limit <= 0 or max(src_w, src_h) <= limit:
        return plan
    ratio = float(limit) / float(max(src_w, src_h))
    out_w = int(src_w * ratio) // 2 * 2
    out_h = int(src_h * ratio) // 2 * 2
    if out_w < 2 or out_h < 2:
        return plan
    plan.update({"width": out_w, "height": out_h, "scaled": True})
    return plan


def _interpolation(shrink: bool):
    """The scaler FFmpeg should use, or None to let PyAV choose.

    AREA is the correct filter for shrinking - it averages, so it does not ring - and it is
    several times faster than LANCZOS. Older PyAV has no enum, and then the default is
    fine; failing to find a scaler is not a reason to refuse the user's video.
    """
    try:
        from av.video.reformatter import Interpolation
    except Exception:
        return None
    return getattr(Interpolation, "AREA" if shrink else "LANCZOS", None)



class MediaError(ValueError):
    """A media problem worth showing the user; the API answers it as a 400."""


def _av():
    """PyAV, or a readable error naming the missing dependency.

    PyAV is FFmpeg inside the Python environment, so it needs no ffmpeg on PATH and it is
    the same library ComfyUI's own video nodes use. If it is missing, saying "this video is
    corrupt" would be a lie - the decoder is what is missing.
    """
    try:
        import av
        return av
    except ImportError:
        raise MediaError(
            "读取视频需要 PyAV（它自带 FFmpeg 解码器）。请在 ComfyUI 所用的 Python 环境里执行："
            "pip install av。安装后重启 ComfyUI。"
        )


def _ffmpeg_errors(av):
    """The exception classes PyAV raises for a file it cannot read.

    PyAV moved these between releases - ``av.error.FFmpegError`` now, ``av.Error`` in older
    builds - so the name is resolved instead of assumed. A bare ``except Exception`` would
    turn a programming mistake into a friendly "this video is broken" message.
    """
    found = []
    for holder in (av, getattr(av, "error", None)):
        for name in ("FFmpegError", "Error"):
            cls = getattr(holder, name, None) if holder is not None else None
            if isinstance(cls, type) and issubclass(cls, BaseException) and cls not in found:
                found.append(cls)
    return tuple(found) if found else (Exception,)


def backend_name() -> str:
    """What the panel can report about the decoder, for support questions."""
    try:
        import av
        return "PyAV %s" % getattr(av, "__version__", "?")
    except ImportError:
        return "no decoder"


# ---------------------------------------------------------------------------
# Probe (import time)
# ---------------------------------------------------------------------------

def _rate_pair(stream) -> Tuple[Optional[int], Optional[int]]:
    """The declared frame rate as an exact numerator/denominator pair.

    30000/1001 is kept as 30000/1001 rather than 29.97, because the difference is a whole
    frame over a minute of footage.
    """
    for rate in (getattr(stream, "average_rate", None), getattr(stream, "base_rate", None),
                 getattr(stream.codec_context, "framerate", None)):
        if rate:
            value = Fraction(rate)
            if value > 0:
                return int(value.numerator), int(value.denominator)
    return None, None


def _is_variable(stream) -> bool:
    """True when the container says two different rates.

    A constant-rate file reports the same average and base rate; a variable-rate one does
    not, and then no single fps number describes it.
    """
    average = getattr(stream, "average_rate", None)
    base = getattr(stream, "base_rate", None)
    if not average or not base:
        return not average
    try:
        a, b = Fraction(average), Fraction(base)
    except (TypeError, ValueError):
        return True
    if a <= 0 or b <= 0:
        return True
    return abs(float(a) - float(b)) > max(0.01, 0.005 * float(b))


def _duration_seconds(container, stream, fps: Optional[float]) -> Optional[float]:
    """Best available duration: container, then stream, then frame count over rate."""
    if getattr(container, "duration", None):
        return float(container.duration) / 1_000_000.0
    if getattr(stream, "duration", None) and getattr(stream, "time_base", None):
        return float(stream.duration * stream.time_base)
    frames = getattr(stream, "frames", 0) or 0
    if frames and fps:
        return float(frames) / float(fps)
    return None


def probe_video(path: str) -> Dict[str, Any]:
    """Container facts for one file: size, rate, duration, audio.

    The extension is never trusted - this is the step that decides whether the bytes are a
    video at all.
    """
    av = _av()
    try:
        container = av.open(path)
    except _ffmpeg_errors(av) as exc:
        raise MediaError("这个文件读不出来，可能已损坏或不是受支持的容器格式（%s）。" % (exc.message if hasattr(exc, "message") else exc)) from exc
    try:
        streams = list(container.streams.video)
        if not streams:
            raise MediaError("这个文件里没有视频流，不能作为投放视频。")
        stream = streams[0]
        num, den = _rate_pair(stream)
        fps = (float(num) / float(den)) if num and den else None
        audio = list(container.streams.audio)
        return {
            "width": int(stream.width),
            "height": int(stream.height),
            "codec_name": str(getattr(getattr(stream, "codec_context", None), "name", "") or ""),
            "pix_fmt": str(getattr(getattr(stream, "codec_context", None), "pix_fmt", "") or ""),
            "source_fps": round(fps, 6) if fps else None,
            "source_fps_num": num,
            "source_fps_den": den,
            "variable_fps": _is_variable(stream),
            "duration_sec": _duration_seconds(container, stream, fps),
            "has_audio": bool(audio),
            "audio_streams": len(audio),
            "audio_rate": int(audio[0].rate) if audio and getattr(audio[0], "rate", None) else None,
            "video_streams": len(streams),
        }
    finally:
        container.close()


def write_cover(video_path: str, cover_path: str, max_edge: int = COVER_MAX_EDGE) -> Dict[str, int]:
    """First decodable frame as a small JPEG. One frame only - never the whole clip."""
    av = _av()
    try:
        container = av.open(video_path)
    except _ffmpeg_errors(av) as exc:
        raise MediaError("生成封面失败：这个视频读不出画面（%s）。" % (getattr(exc, "message", exc))) from exc
    try:
        for frame in container.decode(video=0):
            image = frame.to_image().convert("RGB")
            image.thumbnail((int(max_edge), int(max_edge)))
            image.save(cover_path, "JPEG", quality=82)
            return {"cover_width": image.width, "cover_height": image.height}
        raise MediaError("生成封面失败：这个视频里没有任何可解码的画面。")
    finally:
        container.close()


# ---------------------------------------------------------------------------
# Decode (execution time)
# ---------------------------------------------------------------------------

def _frame_seconds(frame, stream, index: int, fallback_rate: Optional[Fraction]) -> float:
    """Wall-clock time of one decoded frame.

    pts first, because that is the only reading that survives a variable-rate file. The
    frame counter over the declared rate is a last resort for streams without timestamps.
    """
    time_base = getattr(frame, "time_base", None) or getattr(stream, "time_base", None)
    if getattr(frame, "pts", None) is not None and time_base:
        return float(frame.pts * time_base)
    if fallback_rate:
        return index / float(fallback_rate)
    return index / float(TARGET_FPS)


def _estimate_bytes(duration: Optional[float], width: int, height: int, fps: int) -> Optional[int]:
    if not duration:
        return None
    return int(duration * fps) * int(width) * int(height) * 3 * 4


def _frame_span(frame, stream, source_rate, target_fps: int) -> float:
    """How long one decoded frame stays on screen, in seconds.

    The sampling below counts target slots per displayed interval, so a frame's end matters
    as much as its start. Containers usually carry the duration; when they do not, the
    declared rate is the next best answer, and the target rate keeps a rate-less file
    from producing zero frames.
    """
    duration = getattr(frame, "duration", None)
    time_base = getattr(stream, "time_base", None)
    if duration and time_base:
        try:
            span = float(duration * time_base)
        except TypeError:
            span = 0.0
        if span > 0:
            return span
    if source_rate:
        return float(1.0) / float(source_rate)
    return 1.0 / float(target_fps)


def _decode_frames(path: str, target_fps: int,
                   max_side: int = 0) -> Tuple[torch.Tensor, Dict[str, Any]]:
    """Sample the video stream at target_fps and return [F,H,W,3] float32 in 0..1.

    Each source frame is stamped with the interval it is displayed for, and every target
    slot takes the frame on screen at that moment. A faster source therefore drops frames,
    a slower one repeats them, and the last frame is held long enough that the result is
    as long as the file - not one slot shorter. Times are measured from the first decoded
    frame, so a file that starts at a non-zero timestamp does not gain silent frames.

    max_side caps the long edge of the frames this produces (see scale_plan). The memory
    estimate is computed from the planned size rather than the source size, which is what
    lets a 4K file through once the user has asked for a smaller decode.
    """
    av = _av()
    try:
        container = av.open(path)
    except _ffmpeg_errors(av) as exc:
        raise MediaError("解码失败：这个视频读不出来（%s）。" % (getattr(exc, "message", exc))) from exc
    try:
        stream = container.streams.video[0]
        num, den = _rate_pair(stream)
        source_rate = Fraction(num, den) if num and den else None
        width, height = int(stream.width), int(stream.height)
        plan = scale_plan(width, height, max_side)
        duration = _duration_seconds(container, stream, float(source_rate) if source_rate else None)
        estimate = _estimate_bytes(duration, plan["width"], plan["height"], target_fps)
        if estimate and estimate > MAX_DECODE_BYTES:
            raise MediaError(
                "这个视频解码后约需 %.1f GB 内存（%d 帧 × %dx%d），超过了本节点允许的 %.1f GB。"
                "请在节点上把「输出分辨率」调小，或先用其他工具把它缩小、裁短，再投放。"
                % (estimate / 1024 ** 3, int(duration * target_fps), plan["width"], plan["height"],
                   MAX_DECODE_BYTES / 1024 ** 3)
            )
        if estimate and estimate > 2 * 1024 ** 3:
            logger.warning("[H3 LVM Uploads] decoding %s will need about %.1f GB of RAM",
                           os.path.basename(path), estimate / 1024 ** 3)

        # Scaling happens per frame, before anything is accumulated, so the memory the
        # tensor needs is decided by the planned size and not by the file on disk.
        def pixels(frame) -> np.ndarray:
            if not plan["scaled"]:
                return frame.to_ndarray(format="rgb24")
            kwargs = {"width": plan["width"], "height": plan["height"], "format": "rgb24"}
            shrink = plan["width"] <= width and plan["height"] <= height
            interpolation = _interpolation(shrink)
            if interpolation is not None:
                kwargs["interpolation"] = interpolation
            try:
                return frame.reformat(**kwargs).to_ndarray(format="rgb24")
            except (AttributeError, TypeError, ValueError) as exc:
                raise MediaError("这个视频缩小画面失败（%s）。请把「输出分辨率」改回原始再试。"
                                 % (getattr(exc, "message", exc) or exc)) from exc

        frames: List[torch.Tensor] = []
        shape = None
        filled = 0
        origin: Optional[float] = None
        index = 0
        for frame in container.decode(video=0):
            seconds = _frame_seconds(frame, stream, index, source_rate)
            index += 1
            if origin is None:
                origin = seconds
            span = _frame_span(frame, stream, source_rate, target_fps)
            target = int(math.ceil((seconds + span - origin) * target_fps - 1e-6))
            if (int(getattr(frame, "width", width)) != width
                    or int(getattr(frame, "height", height)) != height):
                raise MediaError("这个视频在播放过程中改变了分辨率，无法作为一段连续输出。")
            if target <= filled:
                continue
            array = pixels(frame)
            if shape is None:
                shape = array.shape
            elif tuple(array.shape) != tuple(shape):
                raise MediaError("这个视频在播放过程中改变了分辨率，无法作为一段连续输出。")
            tensor = torch.from_numpy(array).to(torch.float32).mul_(1.0 / 255.0)
            while filled < target:
                frames.append(tensor)
                filled += 1
                if filled >= MAX_DECODE_FRAMES:
                    break
            if filled >= MAX_DECODE_FRAMES:
                logger.warning("[H3 LVM Uploads] stopped decoding after %d frames", MAX_DECODE_FRAMES)
                break
        if not frames:
            raise MediaError("解码失败：这个视频里没有任何可解码的画面。")
        video = torch.stack(frames) if len(frames) > 1 else frames[0].unsqueeze(0)
        info = {
            "width": int(video.shape[2]),
            "height": int(video.shape[1]),
            "source_width": width,
            "source_height": height,
            "max_side": int(plan["max_side"]),
            "scaled": bool(plan["scaled"]),
            "frame_count": int(video.shape[0]),
            "out_fps": int(target_fps),
            "source_fps": (round(float(source_rate), 6) if source_rate else None),
            "source_fps_num": num,
            "source_fps_den": den,
            "variable_fps": _is_variable(stream),
            "duration_sec": float(video.shape[0]) / float(target_fps),
            "probe_duration_sec": duration,
        }
        return video, info
    finally:
        container.close()


def _audio_to_channels(frame) -> Optional[np.ndarray]:
    """One resampled audio frame as int16 [channels, samples].

    Packed frames interleave channels inside each plane; planar frames already have one
    row per channel. Treating packed stereo as one mono row doubles its apparent pitch.
    """
    array = np.asarray(frame.to_ndarray())
    if array.size == 0:
        return None
    channels = int(getattr(frame, "channels", 0) or 0)
    planar = bool(getattr(getattr(frame, "format", None), "is_planar", False))
    if channels > 1 and not planar:
        array = array.reshape(-1, channels).T
    else:
        if array.ndim == 1:
            array = array.reshape(1, -1)
        if channels and array.ndim == 2 and array.shape[0] != channels and array.shape[1] == channels:
            array = array.T
    return array


def _decode_audio(path: str, seconds: float) -> Optional[Dict[str, Any]]:
    """Decode the first audio track and cut or pad it to the played video length.

    The sample rate is kept as the file has it - resampling here would change what the user
    hears for no benefit, and ComfyUI audio inputs carry their own rate.
    """
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
        layout = getattr(getattr(stream, "layout", None), "name", None)
        try:
            resampler = (av.AudioResampler(format="s16p", layout=layout, rate=rate) if layout
                         else av.AudioResampler(format="s16p", rate=rate))
        except (AttributeError, TypeError, ValueError):
            resampler = None
        chunks: List[np.ndarray] = []
        for frame in container.decode(audio=0):
            if resampler is None:
                pieces = [frame]
            else:
                pieces = list(resampler.resample(frame))
            for piece in pieces:
                try:
                    data = _audio_to_channels(piece)
                except Exception:
                    data = None
                if data is not None:
                    chunks.append(data)
        if not chunks:
            return None
        channels = max(int(c.shape[0]) for c in chunks)
        aligned = [c if c.shape[0] == channels else np.zeros((channels, c.shape[1]), dtype=c.dtype)
                   for c in chunks]
        samples = np.concatenate(aligned, axis=1)
        target = max(1, int(round(seconds * rate)))
        if samples.shape[1] > target:
            samples = samples[:, :target]
        elif samples.shape[1] < target:
            pad = np.zeros((channels, target - samples.shape[1]), dtype=samples.dtype)
            samples = np.concatenate([samples, pad], axis=1)
        waveform = torch.from_numpy(np.ascontiguousarray(samples.astype(np.float32) / 32768.0))
        return {"waveform": waveform.unsqueeze(0), "sample_rate": rate}
    finally:
        container.close()


def decode_video(path: str, target_fps: int = TARGET_FPS,
                 max_side: int = 0) -> Tuple[torch.Tensor, Optional[Dict[str, Any]], Dict[str, Any]]:
    """One uploaded file -> (IMAGE [F,H,W,3] float32 0..1, AUDIO dict or None, info).

    The audio length is matched to the frames actually produced, so a downstream H3 node
    cannot drift: frame_count / out_fps and samples / sample_rate describe the same clip.

    max_side is passed to the frame decoder only - the audio is unaffected, and the file
    on disk is never rewritten.
    """
    video, info = _decode_frames(path, target_fps, max_side)
    audio = None
    audio = _decode_audio(path, info["duration_sec"])
    info["has_audio"] = audio is not None
    if audio is not None:
        info["audio_sample_rate"] = int(audio["sample_rate"])
        info["audio_samples"] = int(audio["waveform"].shape[-1])
    logger.info("[H3 LVM Uploads] decoded %s -> %d frames at %d fps (%dx%d%s), %s",
                os.path.basename(path), info["frame_count"], info["out_fps"], info["width"],
                info["height"],
                (" from %dx%d" % (info["source_width"], info["source_height"])) if info["scaled"] else "",
                "with audio" if audio else "silent")
    return video, audio, info




__all__ = [
    "COVER_MAX_EDGE", "CUSTOM_MAX_SIDE_DEFAULT", "DEFAULT_RESIZE", "MAX_DECODE_BYTES",
    "MAX_MAX_SIDE", "MediaError", "MIN_MAX_SIDE", "RESIZE_CUSTOM", "RESIZE_OPTIONS",
    "RESIZE_ORIGINAL", "TARGET_FPS",
    "backend_name", "decode_video", "parse_custom_max_side", "parse_max_side", "probe_video",
    "scale_plan", "write_cover",
]
