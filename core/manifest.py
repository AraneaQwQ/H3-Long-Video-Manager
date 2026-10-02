"""H3 Long Video Manager — Manifest Builder.

Builds the segment plan with the fixed-length algorithm:
- Every output segment has the SAME frame count: the requested duration
  rounded down to 17n+5, Motion Context included, so no segment is ever
  longer than the user asked for.
- Main ranges stay contiguous (no gaps, no invented frames).
- Motion Context is a leading overlap with the previous segment.
- Tail: the last segment takes whatever frames are left, with no 17n+5
  rounding. Every source frame is used; H3 handles the odd length.
"""

from __future__ import annotations

from .models import (
    MotionContextConfig,
    Segment,
    SegmentManifest,
    SourceVideoInfo,
    WorkingVideoConfig,
    WorkingVideoInfo,
)
from .segmentation import compute_segment_duration_frames
from .h3_grid import fixed_slice_frames, generate_fixed_segments


def build_manifest(
    source: SourceVideoInfo,
    working_config: WorkingVideoConfig,
    segment_duration_seconds: float,
    motion_context: MotionContextConfig | None = None,
    align_to_h3: bool = True,
) -> SegmentManifest:
    """Build the complete SegmentManifest from inputs.

    Every segment produced here has the same physical length:
        slice_frames = requested duration (frames), rounded DOWN to 17n+5
    and that length already includes the Motion Context frames, so a segment
    never exceeds the duration the user asked for.

    Motion Context is taken from the tail of the previous segment (a leading
    overlap). The first segment has no context, so its whole length is content.

    The tail is the last segment: it takes exactly the frames left over plus its
    Motion Context, with no 17n+5 rounding. Nothing is repeated, padded, or
    dropped - every source frame is used, and H3 decides what to do with a
    length that is not on the grid.

    Returns a manifest where every segment has:
    - main range (the segment's own content)
    - context range (preceding frames, overlap with the previous segment)
    - extraction range (context + main = the physical file)
    """
    if motion_context is None:
        motion_context = MotionContextConfig(context_frames=22)

    # Compute working video info
    working_info = WorkingVideoInfo.from_source(source, working_config)

    # Requested duration in frames, then the fixed length actually used
    seg_frames = compute_segment_duration_frames(
        segment_duration_seconds, working_info.fps
    )
    slice_frames = fixed_slice_frames(seg_frames, align_to_h3)

    total_frames = working_info.total_frames

    plan = generate_fixed_segments(
        total_frames=total_frames,
        slice_frames=slice_frames,
        context_frames=motion_context.context_frames,
        align_to_h3=align_to_h3,
    )

    segments: list[Segment] = []
    for plan_seg in plan:
        main_start = plan_seg["main_start"]
        main_end = plan_seg["main_end"]
        extract_start = plan_seg["extract_start"]
        extract_end = plan_seg["extract_end"]
        segments.append(
            Segment(
                segment_id=plan_seg["segment_id"],
                main_start_frame=main_start,
                main_end_frame=main_end,
                context_start_frame=extract_start,
                context_end_frame=main_start,
                context_length=main_start - extract_start,
                extraction_start_frame=extract_start,
                extraction_end_frame=extract_end,
            )
        )
    return SegmentManifest(
        source_info=source,
        working_config=working_config,
        working_info=working_info,
        motion_context=motion_context,
        segment_duration_frames=seg_frames,
        slice_frames=slice_frames,
        segments=segments,
        selected_segment_id=None,
    )
