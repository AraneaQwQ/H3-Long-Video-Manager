"""H3 Long Video Manager — Extraction Service (Phase 7).

Extracts a physical frame range from a video source.
Uses PyAV (av) for video decoding, same library as ComfyUI core.

The extracted frames are returned as a torch tensor of shape [F, H, W, C]
with values in [0.0, 1.0] — directly compatible with ComfyUI IMAGE type.
"""

from __future__ import annotations

import io
import logging
from fractions import Fraction
from typing import Optional, Union

import av
import torch

logger = logging.getLogger(__name__)


def extract_frames(
    source: Union[str, io.BytesIO],
    start_frame: int,
    end_frame: int,
    target_width: Optional[int] = None,
    target_height: Optional[int] = None,
) -> torch.Tensor:
    """Extract frames [start_frame, end_frame) from a video source.

    Args:
        source: File path or BytesIO containing the video.
        start_frame: First frame to extract (inclusive).
        end_frame: Last frame to extract (exclusive).
        target_width: Optional target width (for scaling).
        target_height: Optional target height (for scaling).

    Returns:
        torch.Tensor of shape [F, H, W, C] with values in [0, 1], dtype float32.

    Raises:
        ValueError: If start_frame >= end_frame or frame range is invalid.
        RuntimeError: If the video does not have enough frames.
    """
    if start_frame < 0:
        raise ValueError(f"start_frame must be >= 0, got {start_frame}")
    if end_frame <= start_frame:
        raise ValueError(
            f"end_frame ({end_frame}) must be > start_frame ({start_frame})"
        )

    frames = []
    expected_count = end_frame - start_frame

    if isinstance(source, (str, bytes)) or hasattr(source, 'name'):
        container = av.open(source)
    else:
        container = av.open(source)

    try:
        # Get the video stream
        video_stream = container.streams.video[0]
        total_frames_in_file = video_stream.frames  # May be 0 if unknown

        current_index = 0
        for frame in container.decode(video=0):
            if current_index >= end_frame:
                break

            if current_index >= start_frame:
                img = frame.to_ndarray(format="rgb24")  # H×W×C numpy array

                # Scale if needed
                if target_width is not None and target_height is not None:
                    h, w = img.shape[:2]
                    if w != target_width or h != target_height:
                        img = _resize(img, target_width, target_height)

                frames.append(img)

            current_index += 1

    finally:
        container.close()

    if len(frames) < expected_count:
        raise RuntimeError(
            f"Video has insufficient frames: needed {expected_count} "
            f"(frames {start_frame}..{end_frame - 1}), "
            f"got only {len(frames)}"
        )

    # Convert to torch tensor [F, H, W, C] float32 in [0, 1]
    tensor = torch.from_numpy(
        __import__('numpy').stack(frames)
    ).float() / 255.0

    return tensor


def _resize(img, target_w: int, target_h: int):
    """Resize a numpy HWC image using torch (to avoid PIL dependency)."""
    t = torch.from_numpy(img).float() / 255.0
    t = t.permute(2, 0, 1)  # HWC → CHW
    t = torch.nn.functional.interpolate(
        t.unsqueeze(0),
        size=(target_h, target_w),
        mode='bilinear',
        align_corners=False,
    ).squeeze(0)
    t = t.permute(1, 2, 0).numpy()  # CHW → HWC
    return (t * 255.0).astype('uint8')


def get_video_metadata(source: Union[str, io.BytesIO]) -> dict:
    """Get basic metadata from a video file using PyAV.

    Returns a dict with: width, height, fps (Fraction), frame_count,
    duration_seconds, codec, container, is_cfr (best effort).
    """
    if isinstance(source, (str, bytes)) or hasattr(source, 'name'):
        container = av.open(source)
    else:
        container = av.open(source)

    try:
        video_stream = container.streams.video[0]
        width = video_stream.width
        height = video_stream.height
        fps = video_stream.average_rate or Fraction(30, 1)
        frame_count = video_stream.frames  # 0 if unknown
        codec = video_stream.codec.name if video_stream.codec else None

        # Duration from container
        duration_seconds = None
        if container.duration and container.duration > 0:
            duration_seconds = float(container.duration) / av.time_base
        elif frame_count > 0 and fps:
            duration_seconds = frame_count / float(fps)

        container_fmt = container.format.name if container.format else None

        return {
            "width": width,
            "height": height,
            "fps": fps,
            "frame_count": frame_count if frame_count > 0 else None,
            "duration_seconds": duration_seconds,
            "codec": codec,
            "container": container_fmt,
            "is_cfr": None,  # Determining CFR/VFR reliably requires more work
        }
    finally:
        container.close()
