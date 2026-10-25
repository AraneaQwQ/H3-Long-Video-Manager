"""Constant-frame-rate conversion for ComfyUI IMAGE timelines."""

import torch


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
