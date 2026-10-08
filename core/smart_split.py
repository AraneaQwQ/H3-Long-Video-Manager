"""H3 Long Video Manager - Smart Split (scene-aware segment producer).

Two producers feed the SAME Project Segment Store:

    fixed   core/segmentation.py + core/h3_grid.py   17n+5 grid, equal slices
    smart   this module                              real shot boundaries, no grid

The four Smart Split invariants are absolute (planning doc section 7):

    no dropped frames - no duplicated main frames - no padding - no H3 alignment

so the main ranges always cover [0, total_frames) exactly and contiguously, and
a segment length is never rounded to 17n+5. Motion Context only widens the
physical extraction range; it never moves a scene boundary.

This module must NOT import core/h3_grid.py - tests/test_smart_split_core.py
checks that the smart path has no hidden dependency on the 17n+5 grid.
"""

from __future__ import annotations

import inspect
import logging
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .models import MotionContextConfig

logger = logging.getLogger(__name__)

#: Detection sensitivity -> AdaptiveDetector.adaptive_threshold (higher = fewer cuts).
#: Same mapping as the reference Director plugin, so "medium" behaves the same there.
SENSITIVITY_THRESHOLDS: Dict[str, float] = {
    "low": 4.5,
    "medium": 3.0,
    "high": 2.0,
}
DEFAULT_SENSITIVITY = "medium"

#: Longest side of the copy handed to the detector. PySceneDetect's own
#: SceneManager downscales before analysing, so this only buys speed: frame
#: indices - the thing segments are made of - are never affected.
DETECT_MAX_SIDE = 256

#: Declared dependency range (also in requirements.txt). Never auto-installed.
SCENEDETECT_REQUIREMENT = "scenedetect>=0.6.4,<0.8"


def scenedetect_install_hint() -> str:
    """Install command for the Python that is actually running ComfyUI."""
    py = sys.executable or "python"
    return f'"{py}" -m pip install "{SCENEDETECT_REQUIREMENT}"'


def scenedetect_available() -> bool:
    try:
        import scenedetect  # noqa: F401

        return True
    except ImportError:
        return False


def _require_detector():
    """Import the detector the reference Director uses, or explain why it cannot."""
    try:
        from scenedetect.common import FrameTimecode
        from scenedetect.detectors import AdaptiveDetector
    except ImportError as exc:
        raise ImportError(
            "H3 Smart Split requires PySceneDetect. Please install the "
            f"project's declared dependency: {SCENEDETECT_REQUIREMENT}\n"
            "H3 Smart Split 需要 PySceneDetect，请在 ComfyUI 所用的 Python 里执行："
            f"{scenedetect_install_hint()}\n"
            "（H3 Long Video Manager 与 H3 Segment Picker 不依赖它，仍然可用。）"
        ) from exc
    return AdaptiveDetector, FrameTimecode

# ---------------------------------------------------------------------------
# Boundaries: raw detector cuts -> legal, sorted, gap-free bounds
# ---------------------------------------------------------------------------


def normalize_boundaries(raw_cuts: Optional[Iterable[Any]], total_frames: int) -> List[int]:
    """Sort, clamp and deduplicate cut candidates.

    The result always starts at 0 and ends at total_frames, so the segments
    built from it cover the whole timeline. Zero cuts is a legal answer: it
    means the video is one shot, i.e. one segment.

    Values outside [0, total_frames] are dropped with a warning; nothing here
    "intelligently moves" a boundary.
    """
    if total_frames <= 0:
        return []

    interior = set()
    for value in raw_cuts or []:
        try:
            cut = int(value)
        except (TypeError, ValueError):
            logger.warning("[H3 Smart Split] ignoring non-integer cut: %r", value)
            continue
        if cut < 0 or cut > total_frames:
            logger.warning(
                "[H3 Smart Split] ignoring out-of-range cut %d (timeline is 0..%d)",
                cut, total_frames,
            )
            continue
        if 0 < cut < total_frames:
            interior.add(cut)

    return [0, *sorted(interior), total_frames]


# ---------------------------------------------------------------------------
# Segments: bounds -> exact main ranges + optional Motion Context
# ---------------------------------------------------------------------------


def build_smart_segments(
    total_frames: int,
    raw_cuts: Optional[Iterable[Any]],
    motion_context_frames: int = 0,
) -> List[Dict[str, int]]:
    """Turn scene cuts into exact, contiguous segments on the working timeline.

    Returns dicts with the same shape as core.h3_grid.generate_fixed_segments()
    (main / context / extraction ranges) so the node can treat both producers
    alike. ``segment_id`` is 0-based there, exactly like the fixed producer; the
    node turns it into the 1-based bin id (seg01, seg02, ...).

    Motion Context goes through core.models.MotionContextConfig, i.e. the same
    semantics as the fixed producer: the ``motion_context_frames`` frames right
    before the main range, clamped at frame 0. Main ranges are untouched by it.
    """
    if total_frames <= 0:
        return []
    if int(motion_context_frames) < 0:
        raise ValueError(f"motion_context_frames must be >= 0, got {motion_context_frames}")

    bounds = normalize_boundaries(raw_cuts, total_frames)
    context = MotionContextConfig(context_frames=int(motion_context_frames))

    segments = []
    for index in range(len(bounds) - 1):
        main_start, main_end = bounds[index], bounds[index + 1]
        if main_end <= main_start:
            continue
        context_start = context.context_start(main_start)
        segments.append(
            {
                "segment_id": len(segments),
                "scene_id": index,
                "main_start": main_start,
                "main_end": main_end,
                "main_frames": main_end - main_start,
                "context_start": context_start,
                "context_end": main_start,
                "context_frames": main_start - context_start,
                "extract_start": context_start,
                "extract_end": main_end,
                "extract_frames": main_end - context_start,
            }
        )
    return segments


def assert_lossless(segments: Sequence[Dict[str, int]], total_frames: int) -> None:
    """Guard used by the node: main ranges must tile [0, total_frames) exactly."""
    if not segments:
        raise ValueError("H3 Smart Split produced no segments")
    if segments[0]["main_start"] != 0:
        raise ValueError(f"first segment must start at 0, got {segments[0]['main_start']}")
    if segments[-1]["main_end"] != total_frames:
        raise ValueError(f"last segment must end at {total_frames}, got {segments[-1]['main_end']}")
    for previous, current in zip(segments, segments[1:]):
        if previous["main_end"] != current["main_start"]:
            raise ValueError(
                "H3 Smart Split must not leave a gap or an overlap between main "
                f"ranges: {previous['main_end']} != {current['main_start']}"
            )
    covered = sum(seg["main_frames"] for seg in segments)
    if covered != total_frames:
        raise ValueError(f"main ranges cover {covered} frames, expected {total_frames}")

# ---------------------------------------------------------------------------
# Detection: frames -> raw cut indices (one pass, the video is never re-opened)
# ---------------------------------------------------------------------------


def analysis_size(width: int, height: int) -> Tuple[int, int]:
    """Downscaled analysis size; the long side is capped at DETECT_MAX_SIDE."""
    long_side = max(int(width), int(height))
    if long_side <= DETECT_MAX_SIDE:
        return int(width), int(height)
    scale = DETECT_MAX_SIDE / float(long_side)
    return max(2, int(round(width * scale))), max(2, int(round(height * scale)))


def _fps_float(fps) -> float:
    try:
        value = float(fps)
    except (TypeError, ValueError):
        return 24.0
    return value if value > 0 else 24.0


def _resize_numpy(frame, target_w: int, target_h: int):
    import numpy as np

    h, w = frame.shape[:2]
    rows = (np.arange(target_h) * h // max(1, target_h)).clip(0, h - 1)
    cols = (np.arange(target_w) * w // max(1, target_w)).clip(0, w - 1)
    return frame[rows[:, None], cols[None, :], :]


def _prepare_analysis_frames(video, total_frames: int):
    """Shrink the whole timeline once (batch) instead of frame by frame."""
    shape = getattr(video, "shape", None)
    if shape is None or len(shape) != 4:
        return video
    height, width = int(shape[1]), int(shape[2])
    target_w, target_h = analysis_size(width, height)
    if (target_w, target_h) == (width, height):
        return video
    if hasattr(video, "permute"):  # torch: [F,H,W,C] -> [F,C,H,W] -> interpolate
        import torch

        flat = video[:total_frames].permute(0, 3, 1, 2)
        flat = torch.nn.functional.interpolate(
            flat, size=(target_h, target_w), mode="bilinear", align_corners=False
        )
        return flat.permute(0, 2, 3, 1)
    import numpy as np

    return np.stack([_resize_numpy(video[i], target_w, target_h) for i in range(total_frames)])


def _to_bgr_uint8(frame):
    """One timeline frame -> contiguous uint8 BGR array for the detector."""
    import numpy as np

    arr = frame.detach().cpu().numpy() if hasattr(frame, "detach") else np.asarray(frame)
    if arr.ndim == 2:
        arr = arr[:, :, None]
    if arr.shape[-1] == 4:
        arr = arr[:, :, :3]
    if arr.dtype != np.uint8:
        arr = (np.clip(arr.astype(np.float64), 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    if arr.shape[-1] == 1:
        arr = np.repeat(arr, 3, axis=-1)
    return np.ascontiguousarray(arr[:, :, ::-1])


def _process_frame(detector, FrameTimecode, index: int, frame, total_frames: int, fps):
    """Call SceneDetector.process_frame across the 0.6 / 0.7 signatures."""
    timecode = FrameTimecode(index, fps=_fps_float(fps))
    params = list(inspect.signature(detector.process_frame).parameters)
    if len(params) >= 3:  # 0.6.x: process_frame(frame_num, frame_img, frame_len)
        return detector.process_frame(timecode, frame, total_frames)
    return detector.process_frame(timecode, frame)


def _post_process(detector, FrameTimecode, total_frames: int, fps):
    """Call SceneDetector.post_process across the 0.6 / 0.7 signatures."""
    params = list(inspect.signature(detector.post_process).parameters)
    if len(params) >= 1:  # 0.7.x: post_process(timecode)
        return detector.post_process(FrameTimecode(max(0, total_frames - 1), fps=_fps_float(fps)))
    return detector.post_process()


def detect_scene_cuts(
    video,
    total_frames: int,
    fps: float = 24.0,
    sensitivity: str = DEFAULT_SENSITIVITY,
) -> Tuple[List[int], Dict[str, Any]]:
    """One pass over the working timeline -> interior cut frame indices.

    ``video`` is the node's IMAGE tensor [F,H,W,C] (float [0,1] or uint8): the
    very timeline the segments are cut on, so a detected index is directly a
    frame index of the output. Detection never runs on a pre-sliced timeline, and
    the source is never decoded twice - the detector sees every frame once.

    Returns ``(cuts, meta)``; ``cuts`` are interior indices, use
    normalize_boundaries()/build_smart_segments() to turn them into ranges.
    Raises ImportError with an install hint when PySceneDetect is missing.
    """
    AdaptiveDetector, FrameTimecode = _require_detector()

    key = str(sensitivity or DEFAULT_SENSITIVITY).strip().lower()
    if key not in SENSITIVITY_THRESHOLDS:
        key = DEFAULT_SENSITIVITY
    threshold = SENSITIVITY_THRESHOLDS[key]

    total = int(total_frames)
    if total <= 0:
        return [], {"method": "pyscenedetect_adaptive", "cut_count": 0, "scene_count": 0}

    detector = AdaptiveDetector(adaptive_threshold=float(threshold))
    frames = _prepare_analysis_frames(video, total)
    shape = getattr(frames, "shape", ())
    analysis = f"{int(shape[2])}x{int(shape[1])}" if len(shape) == 4 else "unknown"

    cuts: List[int] = []
    for index in range(total):
        new_cuts = _process_frame(
            detector, FrameTimecode, index, _to_bgr_uint8(frames[index]), total, fps
        )
        cuts.extend(int(cut.get_frames()) for cut in new_cuts)
    cuts.extend(int(cut.get_frames()) for cut in _post_process(detector, FrameTimecode, total, fps))

    interior = sorted({cut for cut in cuts if 0 < cut < total})
    meta = {
        "method": "pyscenedetect_adaptive",
        "detector": "AdaptiveDetector",
        "sensitivity": key,
        "adaptive_threshold": threshold,
        "min_scene_len": int(getattr(detector, "min_scene_len", 0) or 0),
        "analysis_size": analysis,
        "cut_count": len(interior),
        "scene_count": len(interior) + 1,
    }
    return interior, meta
