"""H3 Long Video Manager — Core Data Models (Phase 1).

All frame calculations use **half-open intervals** `[start, end)`.
Internal frame indices are always integers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional


# ---------------------------------------------------------------------------
# Motion Context
# ---------------------------------------------------------------------------

#: Allowed Motion Context frame counts (user-facing options).
MOTION_CONTEXT_OPTIONS = (5, 22, 39, 56)


@dataclass(frozen=True)
class MotionContextConfig:
    """User-selected Motion Context parameter.

    This is a simple user-controlled value meaning:
    "How many frames immediately preceding the logical segment
    should be included in the physical video extraction."

    The plugin does NOT implement, inspect, or synchronize with
    any Motion Context node. The user is responsible for ensuring
    the downstream value matches.
    """

    context_frames: int = 22

    def __post_init__(self) -> None:
        if self.context_frames not in MOTION_CONTEXT_OPTIONS:
            raise ValueError(
                f"context_frames must be one of {MOTION_CONTEXT_OPTIONS}, "
                f"got {self.context_frames}"
            )

    def context_start(self, main_start_frame: int) -> int:
        """Calculate the context start frame (clamped at 0).

        For the first segment, context cannot go negative.
        """
        return max(0, main_start_frame - self.context_frames)

    def context_end(self, main_start_frame: int) -> int:
        """Context always ends where the main segment starts."""
        return main_start_frame


# ---------------------------------------------------------------------------
# Source Video
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceVideoInfo:
    """Metadata about the source video file.

    The source video is never modified; this is read-only information.
    """

    file_path: str
    width: int
    height: int
    fps: Fraction
    frame_count: Optional[int] = None
    duration_seconds: Optional[float] = None
    codec: Optional[str] = None
    container: Optional[str] = None
    is_cfr: Optional[bool] = None

    @property
    def aspect_ratio(self) -> tuple[int, int]:
        """Return (w, h) as a reduced fraction pair."""
        from math import gcd
        g = gcd(self.width, self.height)
        return (self.width // g, self.height // g)

    @property
    def pixel_count(self) -> int:
        return self.width * self.height


# ---------------------------------------------------------------------------
# Working Video
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkingVideoConfig:
    """Configuration for the H3 working video.

    The working video is a standardized 24 FPS timeline that all
    segmentation and extraction is based on.
    """

    target_fps: int = 24
    # Resolution scaling — at most one should be set
    scale_percent: Optional[float] = None   # e.g. 50.0 means 50%
    target_width: Optional[int] = None      # absolute target width

    def __post_init__(self) -> None:
        if self.target_fps <= 0:
            raise ValueError("target_fps must be positive")
        if self.scale_percent is not None and not (0 < self.scale_percent <= 100):
            raise ValueError("scale_percent must be in (0, 100]")
        if self.target_width is not None and self.target_width <= 0:
            raise ValueError("target_width must be positive")

    def compute_working_dimensions(
        self, source_width: int, source_height: int
    ) -> tuple[int, int]:
        """Compute working (width, height), preserving aspect ratio.

        Results are rounded to even numbers (required by many VAEs).
        """
        if self.scale_percent is not None:
            w = int(source_width * self.scale_percent / 100.0)
            h = int(source_height * self.scale_percent / 100.0)
        elif self.target_width is not None:
            w = self.target_width
            h = int(source_height * (w / source_width))
        else:
            # No scaling — keep source resolution
            w = source_width
            h = source_height

        # Round to even (required by 16x VAE downscaling)
        w = w if w % 2 == 0 else w + 1
        h = h if h % 2 == 0 else h + 1
        return (w, h)


@dataclass(frozen=True)
class WorkingVideoInfo:
    """Computed information about the H3 working video timeline.

    This is the authoritative basis for all segmentation calculations.
    """

    width: int
    height: int
    fps: int  # Always the target FPS (default 24)
    total_frames: int
    duration_seconds: float

    @classmethod
    def from_source(
        cls,
        source: SourceVideoInfo,
        config: WorkingVideoConfig,
    ) -> WorkingVideoInfo:
        """Derive working video info from source + config.

        The total frame count is recalculated based on duration × target_fps.
        This ensures a deterministic 24 FPS timeline regardless of source FPS.
        """
        w, h = config.compute_working_dimensions(source.width, source.height)

        if source.duration_seconds is not None:
            total_frames = round(source.duration_seconds * config.target_fps)
        elif source.frame_count is not None:
            # Scale frame count proportionally from source FPS to target FPS
            total_frames = round(source.frame_count * config.target_fps / source.fps)
        else:
            raise ValueError(
                "Cannot determine total frames: source has neither "
                "duration_seconds nor frame_count"
            )

        duration_seconds = total_frames / config.target_fps

        return cls(
            width=w,
            height=h,
            fps=config.target_fps,
            total_frames=total_frames,
            duration_seconds=duration_seconds,
        )


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    """A single logical segment with its Motion Context extraction range.

    All frame indices are absolute positions in the working video.
    Ranges use half-open intervals [start, end).
    """

    segment_id: int
    # Logical segment (the actual content)
    main_start_frame: int
    main_end_frame: int
    # Motion Context (preceding frames for physical extraction)
    context_start_frame: int
    context_end_frame: int
    context_length: int
    # Physical extraction range (context + main)
    extraction_start_frame: int
    extraction_end_frame: int

    @property
    def main_frame_count(self) -> int:
        return self.main_end_frame - self.main_start_frame

    @property
    def extraction_frame_count(self) -> int:
        return self.extraction_end_frame - self.extraction_start_frame

    @property
    def main_start_time(self) -> float:
        """Start time in seconds (requires knowing fps; use manifest for this)."""
        # This property is informational only; use manifest.fps for calculation
        return self.main_start_frame  # placeholder — use manifest

    def summary(self) -> str:
        return (
            f"Segment {self.segment_id:02d}: "
            f"main=[{self.main_start_frame},{self.main_end_frame}), "
            f"context=[{self.context_start_frame},{self.context_end_frame}), "
            f"extract=[{self.extraction_start_frame},{self.extraction_end_frame})"
        )


# ---------------------------------------------------------------------------
# Segment Manifest (Source of Truth)
# ---------------------------------------------------------------------------


@dataclass
class SegmentManifest:
    """Authoritative segment manifest.

    The frontend must not independently reimplement segmentation math.
    This manifest is the single source of truth for all segment calculations.

    Conceptual separation:
    - Logical segment: the main timeline portion
    - Context: preceding frames from Motion Context
    - Physical extraction: context + main = what actually gets output
    """

    source_info: SourceVideoInfo
    working_config: WorkingVideoConfig
    working_info: WorkingVideoInfo
    motion_context: MotionContextConfig
    segment_duration_frames: int
    segments: list[Segment] = field(default_factory=list)
    selected_segment_id: Optional[int] = None

    @property
    def selected_segment(self) -> Optional[Segment]:
        if self.selected_segment_id is None:
            return None
        for seg in self.segments:
            if seg.segment_id == self.selected_segment_id:
                return seg
        return None

    def get_segment(self, segment_id: int) -> Segment:
        for seg in self.segments:
            if seg.segment_id == segment_id:
                return seg
        raise KeyError(f"Segment {segment_id} not found in manifest")
