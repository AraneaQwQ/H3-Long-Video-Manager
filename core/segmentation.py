"""H3 Long Video Manager — Segmentation (Phase 4).

Generates logical segments from a working video timeline.
All ranges use half-open intervals [start, end).
"""

from __future__ import annotations


def compute_segment_duration_frames(duration_seconds: float, fps: int) -> int:
    """Convert a user-specified duration (in seconds) to integer frame count.

    Uses round-half-to-even (banker's rounding) for determinism.
    """
    if duration_seconds <= 0:
        raise ValueError(f"duration_seconds must be > 0, got {duration_seconds}")
    frames = int(round(duration_seconds * fps))
    if frames <= 0:
        raise ValueError(
            f"Computed segment duration is 0 frames "
            f"(duration={duration_seconds}s, fps={fps}). "
            f"Increase the duration or fps."
        )
    return frames


def generate_segments(
    total_frames: int,
    segment_duration_frames: int,
) -> list[tuple[int, int]]:
    """Generate logical segment boundaries as (start, end) half-open pairs.

    Rules:
    - Segments are sequential, non-overlapping.
    - The final segment may be shorter than segment_duration_frames.
    - No frames are invented beyond total_frames.
    - If total_frames == 0, returns empty list.

    Example:
        total_frames=1000, duration=144
        → [(0,144), (144,288), (288,432), (432,576), (576,720),
           (720,864), (864,1000)]  # last is short (136 frames)
    """
    if total_frames <= 0:
        return []
    if segment_duration_frames <= 0:
        raise ValueError(f"segment_duration_frames must be > 0, got {segment_duration_frames}")

    segments: list[tuple[int, int]] = []
    start = 0
    while start < total_frames:
        end = min(start + segment_duration_frames, total_frames)
        segments.append((start, end))
        start = end

    return segments
