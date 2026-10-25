"""Batch streaming frames with the exact v1 fixed/smart range semantics."""
from __future__ import annotations

from collections import deque


def _meta(segment_id, main_start, extract_end, context_frames):
    extract_start = main_start - context_frames
    return {
        "segment_id": segment_id,
        "main_start": main_start,
        "main_end": extract_end,
        "main_frames": extract_end - main_start,
        "context_start": extract_start,
        "context_end": main_start,
        "context_frames": context_frames,
        "extract_start": extract_start,
        "extract_end": extract_end,
        "extract_frames": extract_end - extract_start,
    }


def iter_fixed_segment_batches(frames, slice_frames, context_frames):
    """Yield (v1-shaped range, uint8 frame list) while retaining only MC overlap."""
    slice_frames = int(slice_frames)
    context_frames = int(context_frames)
    if slice_frames <= 0:
        raise ValueError("slice_frames must be > 0")
    if context_frames < 0:
        raise ValueError("context_frames must be >= 0")
    if slice_frames - context_frames < 5:
        raise ValueError(
            f"每段 {slice_frames} 帧里 Motion Context 占 {context_frames} 帧，"
            f"正文只剩 {slice_frames - context_frames} 帧（至少需要 5 帧）。"
            "请增大每段时长，或减小 Motion Context 帧数。"
        )
    buffer = []
    main_start = 0
    segment_id = 0
    while True:
        context = context_frames if segment_id else 0
        for frame in frames:
            buffer.append(frame)
            if len(buffer) != slice_frames:
                continue
            meta = _meta(segment_id, main_start, main_start - context + slice_frames, context)
            yield meta, buffer
            segment_id += 1
            main_start = meta["extract_end"]
            buffer = buffer[-context_frames:] if context_frames else []
            context = context_frames
        if buffer and len(buffer) > context:
            extract_end = main_start - context + len(buffer)
            yield _meta(segment_id, main_start, extract_end, context), buffer
        return


def iter_smart_segment_batches(frames, segments, context_frames):
    """Yield smart ranges in one pass; a small deque supplies the next shot's MC."""
    context_frames = int(context_frames)
    recent = deque(maxlen=max(1, context_frames))
    current = 0
    buffer = None
    for index, frame in enumerate(frames):
        if current >= len(segments):
            break
        segment = segments[current]
        if index == segment["main_start"]:
            buffer = list(recent)[-context_frames:] if context_frames else []
        if segment["main_start"] <= index < segment["main_end"]:
            buffer.append(frame)
        recent.append(frame)
        if index == segment["main_end"] - 1:
            yield segment, buffer
            current += 1
            buffer = None
    if current != len(segments):
        raise ValueError("流式解码提前结束，无法覆盖全部镜头；请检查源视频是否损坏。")


__all__ = ["iter_fixed_segment_batches", "iter_smart_segment_batches"]
