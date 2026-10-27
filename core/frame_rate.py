"""Constant-frame-rate conversion and playback-speed remapping for IMAGE timelines."""

import math

import torch

#: Widget options shared by the producers; "custom" reads its number from a
#: second widget. Values are kept as strings because Combo widgets are strings.
PLAYBACK_SPEED_OPTIONS = ("1.0x", "0.75x", "0.5x", "custom")


def parse_playback_speed(playback_speed, playback_speed_custom=1.0) -> float:
    """Validate a playback-speed widget pair into a float in (0, 1.0].

    Presets keep their exact value (0.75 stays two decimals); a custom value is
    rounded to one decimal, matching how the UI asks for it. Anything outside
    (0, 1.0] is refused - only slow motion is offered here, never speed-up.
    """
    choice = str(playback_speed if playback_speed is not None else "1.0x").strip()
    if choice.lower() == "custom":
        try:
            value = float(playback_speed_custom)
        except (TypeError, ValueError):
            raise ValueError(
                f"自定义播放速度必须是数字，收到 {playback_speed_custom!r}。"
            )
        value = round(value, 1)
        if value <= 0 or value > 1.0:
            raise ValueError(
                f"自定义播放速度必须在 (0, 1.0] 之间（收到 {value}）。"
            )
        return value
    text = choice[:-1] if choice.lower().endswith("x") else choice
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"未知的播放速度选项：{playback_speed!r}。")
    if value <= 0 or value > 1.0:
        raise ValueError(f"播放速度必须在 (0, 1.0] 之间（收到 {value}）。")
    return value


def slowdown_frame_count(source_frames: int, speed: float) -> int:
    """Frame count of a timeline slowed down to `speed` at the SAME fps."""
    source_frames = int(source_frames)
    if source_frames <= 0:
        return 0
    if not (0 < speed <= 1):
        raise ValueError("speed must be in (0, 1]")
    return max(1, int(round(source_frames / float(speed))))


def slowdown_video(video: torch.Tensor, speed: float) -> torch.Tensor:
    """Slow a video down by holding frames (nearest-neighbour time remap).

    Same sampling style as resample_video: no interpolation, no invented
    frames - each output frame is a copy of one source frame, so 0.5x turns
    every source frame into roughly two output frames. Output fps is
    unchanged; only the frame count grows.
    """
    if not (0 < speed <= 1):
        raise ValueError("speed must be in (0, 1]")
    source_frames = int(video.shape[0])
    if source_frames == 0 or speed == 1.0:
        return video
    target_frames = slowdown_frame_count(source_frames, speed)
    positions = torch.arange(target_frames, dtype=torch.float64, device=video.device)
    indices = torch.floor(positions * float(speed) + 0.5).long()
    indices = indices.clamp_(0, source_frames - 1)
    return video[indices].contiguous()


def iter_slowed_frames(frames, speed: float, stats=None):
    """Apply slowdown_video's nearest-neighbour mapping to a lazy frame iterable."""
    if not (0 < speed <= 1):
        raise ValueError("speed must be in (0, 1]")
    source_count = 0
    output_count = 0
    last_frame = None
    try:
        if speed == 1.0:
            for frame in frames:
                source_count += 1
                output_count += 1
                yield frame
            return
        for source_index, frame in enumerate(frames):
            source_count += 1
            last_frame = frame
            while math.floor(output_count * float(speed) + 0.5) == source_index:
                output_count += 1
                yield frame
        target_frames = slowdown_frame_count(source_count, speed)
        while output_count < target_frames:
            output_count += 1
            yield last_frame
    finally:
        if stats is not None:
            stats.update({
                "source_frames": source_count,
                "processed_frames": output_count,
            })


def converted_frame_count(source_frames: int, source_fps: float, target_fps: int = 24) -> int:
    source_frames = int(source_frames)
    if source_frames <= 0:
        return 0
    if source_fps <= 0 or target_fps <= 0:
        raise ValueError("fps must be positive")
    return max(1, int(round(source_frames * float(target_fps) / float(source_fps))))


def resample_video(video: torch.Tensor, source_fps: float, target_fps: int = 24) -> torch.Tensor:
    """Select the nearest source frame at each target timestamp."""
    if source_fps <= 0 or target_fps <= 0:
        raise ValueError("fps must be positive")
    source_frames = int(video.shape[0])
    if source_frames == 0 or float(source_fps) == float(target_fps):
        return video
    target_frames = converted_frame_count(source_frames, source_fps, target_fps)
    positions = torch.arange(target_frames, dtype=torch.float64, device=video.device)
    indices = torch.floor(positions * (float(source_fps) / float(target_fps)) + 0.5).long()
    indices = indices.clamp_(0, source_frames - 1)
    return video[indices].contiguous()
