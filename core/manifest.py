"""H3 Long Video Manager — Manifest Builder (Phase 6).

Uses the carry-forward seamless segmentation algorithm to ensure:
- Each main segment is a valid 17n+5 frame count
- Segments are contiguous (no gaps between segments)
- Lost frames from alignment slide to the next segment
- Only the final segment may lose frames
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
from .h3_grid import generate_aligned_segments, is_valid_h3_frame_count


def build_manifest(
    source: SourceVideoInfo,
    working_config: WorkingVideoConfig,
    segment_duration_seconds: float,
    motion_context: MotionContextConfig | None = None,
    align_to_h3: bool = True,
) -> SegmentManifest:
    """Build the complete SegmentManifest from inputs.

    When align_to_h3=True (default), uses the carry-forward seamless
    segmentation algorithm:
    - Main segments are contiguous (no gaps)
    - Each main segment is 17n+5 frames
    - Truncation slides forward (no frames lost between segments)
    - Only the final segment may be short

    Motion Context (if provided) extends the extraction range backward
    into the previous segment. The total extraction (MC + main) may not
    be 17n+5 — H3 auto-snaps when processing.

    Returns a manifest where every segment has:
    - main range (logical segment, 17n+5, contiguous)
    - context range (preceding frames for MC)
    - extraction range (context + main = physical output)
    """
    if motion_context is None:
        motion_context = MotionContextConfig(context_frames=22)

    # Compute working video info
    working_info = WorkingVideoInfo.from_source(source, working_config)

    # Compute segment duration in frames
    seg_frames = compute_segment_duration_frames(
        segment_duration_seconds, working_info.fps
    )

    total_frames = working_info.total_frames

    if align_to_h3:
        # Use seamless carry-forward segmentation (main segments are 17n+5)
        main_segments = generate_aligned_segments(total_frames, seg_frames)
    else:
        # Fallback: plain equal splits (old behavior, no H3 alignment)
        main_segments = []
        pos = 0
        while pos < total_frames:
            end = min(pos + seg_frames, total_frames)
            main_segments.append((pos, end))
            pos = end

    # Build full segment list with Motion Context
    segments: list[Segment] = []
    for idx, (main_start, main_end) in enumerate(main_segments):
        ctx_start = motion_context.context_start(main_start)
        ctx_end = motion_context.context_end(main_start)
        ctx_length = ctx_end - ctx_start

        # Extraction range = context + main
        # (MC overlaps with previous segment by design)
        extract_start = ctx_start
        extract_end = main_end

        # Clamp to total frames
        extract_end = min(extract_end, total_frames)

        segments.append(
            Segment(
                segment_id=idx,
                main_start_frame=main_start,
                main_end_frame=main_end,
                context_start_frame=ctx_start,
                context_end_frame=ctx_end,
                context_length=ctx_length,
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
        segments=segments,
        selected_segment_id=None,
    )
