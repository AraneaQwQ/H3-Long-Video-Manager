"""H3 Long Video Manager — Core (Layer A).

Framework-independent logic for video metadata, conforming,
segmentation, Motion Context range calculation, and extraction planning.
"""

from .models import (
    SourceVideoInfo,
    WorkingVideoConfig,
    WorkingVideoInfo,
    MotionContextConfig,
    Segment,
    SegmentManifest,
)

__all__ = [
    "SourceVideoInfo",
    "WorkingVideoConfig",
    "WorkingVideoInfo",
    "MotionContextConfig",
    "Segment",
    "SegmentManifest",
]
