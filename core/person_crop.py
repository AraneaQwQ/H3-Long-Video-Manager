"""Person-aware crop for H3 Long Video Manager.

Detects the main person across sampled frames, then crops a window that
covers the union of those boxes, optionally expanded, while keeping the
source aspect ratio.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from typing import Optional, Sequence

import torch

logger = logging.getLogger(__name__)

PERSON_CLASS_ID = 1  # COCO
_DEFAULT_SAMPLES = 16
_SCORE_THRESHOLD = 0.45
_WEIGHT_FILENAME = "fasterrcnn_mobilenet_v3_large_fpn-fb6a3cc7.pth"
_WEIGHT_URL = "https://download.pytorch.org/models/fasterrcnn_mobilenet_v3_large_fpn-fb6a3cc7.pth"
_WEIGHT_SHA_PREFIX = "fb6a3cc7"
_WEIGHT_MIN_BYTES = 70 * 1024 * 1024
_MODEL = None
_TRANSFORM = None


def even(value: int) -> int:
    return int(value) // 2 * 2


def align(value: int, step: int = 2) -> int:
    return max(step, int(value) // step * step)


def sample_indices(frame_count: int, sample_count: int = _DEFAULT_SAMPLES) -> list[int]:
    if frame_count <= 0:
        return []
    if frame_count <= sample_count:
        return list(range(frame_count))
    positions = torch.linspace(0, frame_count - 1, sample_count)
    return sorted({int(i) for i in positions.round().tolist()})


def fit_crop_window(
    width: int,
    height: int,
    boxes: Sequence[tuple[float, float, float, float]],
    expand_percent: float,
    keep_aspect: bool = True,
) -> tuple[int, int, int, int]:
    """Return (x, y, w, h) covering person boxes, expanded and clamped."""
    if not boxes:
        raise ValueError("boxes must not be empty")
    if not 0 <= expand_percent <= 100:
        raise ValueError("expand_percent must be in [0, 100]")

    xs1, ys1, xs2, ys2 = zip(*boxes)
    x1, y1, x2, y2 = min(xs1), min(ys1), max(xs2), max(ys2)
    bw = max(x2 - x1, 1.0)
    bh = max(y2 - y1, 1.0)
    margin = expand_percent / 100.0
    x1 -= bw * margin
    x2 += bw * margin
    y1 -= bh * margin
    y2 += bh * margin

    crop_w = x2 - x1
    crop_h = y2 - y1
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0

    if keep_aspect and height > 0:
        src_aspect = width / height
        crop_aspect = crop_w / max(crop_h, 1e-6)
        if crop_aspect > src_aspect:
            crop_h = crop_w / src_aspect
        else:
            crop_w = crop_h * src_aspect

    crop_w = min(crop_w, width)
    crop_h = min(crop_h, height)
    x = min(max(cx - crop_w / 2.0, 0.0), width - crop_w)
    y = min(max(cy - crop_h / 2.0, 0.0), height - crop_h)

    x, y = even(round(x)), even(round(y))
    w, h = align(round(crop_w)), align(round(crop_h))
    if x + w > width:
        w = align(width - x)
    if y + h > height:
        h = align(height - y)
    if w < 64 or h < 64:
        raise ValueError(f"computed crop is too small: {w}x{h}")
    return x, y, w, h


def apply_crop(video: torch.Tensor, x: int, y: int, w: int, h: int) -> torch.Tensor:
    """Crop IMAGE tensor [F,H,W,C] to [F,h,w,C]."""
    return video[:, y : y + h, x : x + w, :].contiguous()


def _candidate_weight_dirs() -> list[str]:
    dirs: list[str] = []
    try:
        dirs.append(os.path.join(torch.hub.get_dir(), "checkpoints"))
    except Exception:
        pass
    env_homes = [
        os.environ.get("TORCH_HOME"),
        os.environ.get("XDG_CACHE_HOME"),
        os.path.join(os.path.expanduser("~"), ".cache"),
        os.path.join(os.environ.get("USERPROFILE", ""), ".cache"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "torch"),
    ]
    for home in env_homes:
        if not home:
            continue
        dirs.append(os.path.join(home, "torch", "hub", "checkpoints"))
        dirs.append(os.path.join(home, "hub", "checkpoints"))
        dirs.append(os.path.join(home, "checkpoints"))
    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dirs.append(os.path.join(plugin_root, "weights"))
    seen: set[str] = set()
    unique: list[str] = []
    for path in dirs:
        norm = os.path.normpath(path)
        key = os.path.normcase(norm)
        if key in seen:
            continue
        seen.add(key)
        unique.append(norm)
    return unique


def _file_sha256_prefix(path: str, length: int = 8) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:length]


def _is_valid_weight_file(path: str, verify_hash: bool = False) -> bool:
    if not os.path.isfile(path):
        return False
    if os.path.getsize(path) < _WEIGHT_MIN_BYTES:
        return False
    if not verify_hash:
        return True
    try:
        return _file_sha256_prefix(path).lower() == _WEIGHT_SHA_PREFIX
    except OSError:
        return False


def _copy_into_hub_cache(src: str) -> str:
    try:
        dest_dir = os.path.join(torch.hub.get_dir(), "checkpoints")
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, _WEIGHT_FILENAME)
        if os.path.normcase(os.path.abspath(src)) != os.path.normcase(os.path.abspath(dest)):
            if not _is_valid_weight_file(dest):
                shutil.copy2(src, dest)
                print(f"[H3 LVM] person_crop: copied detector weights -> {dest}")
        return dest if os.path.isfile(dest) else src
    except Exception as exc:
        print(f"[H3 LVM] person_crop: could not copy weights into hub cache: {exc}")
        return src


def _find_local_weights() -> Optional[str]:
    found: list[str] = []
    for directory in _candidate_weight_dirs():
        path = os.path.join(directory, _WEIGHT_FILENAME)
        if _is_valid_weight_file(path):
            found.append(path)
    for path in found:
        if _is_valid_weight_file(path, verify_hash=True):
            return path
    return found[0] if found else None


def _download_weights(dest: str) -> str:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"[H3 LVM] person_crop: downloading detector weights from {_WEIGHT_URL}")
    torch.hub.download_url_to_file(_WEIGHT_URL, dest, hash_prefix=None, progress=True)
    if not _is_valid_weight_file(dest):
        raise RuntimeError(f"downloaded weights look corrupt: {dest}")
    return dest


def _resolve_weight_path() -> str:
    local = _find_local_weights()
    if local:
        print(f"[H3 LVM] person_crop: using local detector weights {local}")
        return _copy_into_hub_cache(local)
    dest = os.path.join(torch.hub.get_dir(), "checkpoints", _WEIGHT_FILENAME)
    return _download_weights(dest)


def _load_detector():
    global _MODEL, _TRANSFORM
    if _MODEL is not None:
        return _MODEL, _TRANSFORM
    try:
        from torchvision.models.detection import (
            FasterRCNN_MobileNet_V3_Large_FPN_Weights,
            fasterrcnn_mobilenet_v3_large_fpn,
        )
    except ImportError as exc:
        raise RuntimeError(
            "person_crop 需要 torchvision。请在 ComfyUI 的 Python 环境中安装: pip install torchvision"
        ) from exc

    weight_path = _resolve_weight_path()
    # Do not use Weights.DEFAULT: it re-downloads into ComfyUI cache and hash-checks.
    # weights_backbone=None avoids a second ImageNet download.
    model = fasterrcnn_mobilenet_v3_large_fpn(weights=None, weights_backbone=None, num_classes=91)
    state = torch.load(weight_path, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model.eval()
    model.to(torch.device("cpu"))
    _MODEL = model
    _TRANSFORM = FasterRCNN_MobileNet_V3_Large_FPN_Weights.COCO_V1.transforms()
    print("[H3 LVM] person_crop: Faster R-CNN detector ready")
    return _MODEL, _TRANSFORM


def _frame_to_uint8_rgb(frame: torch.Tensor):
    rgb = frame.detach().float().clamp(0.0, 1.0).cpu().numpy()
    return (rgb * 255.0).round().astype("uint8")


def _detect_torchvision(
    video: torch.Tensor,
    sample_count: int,
) -> list[tuple[float, float, float, float]]:
    from PIL import Image

    model, transform = _load_detector()
    indices = sample_indices(video.shape[0], sample_count)
    boxes: list[tuple[float, float, float, float]] = []
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    try:
        with torch.no_grad():
            for index in indices:
                rgb = _frame_to_uint8_rgb(video[index])
                tensor = transform(Image.fromarray(rgb, mode="RGB")).to(device)
                output = model([tensor])[0]
                labels = output["labels"].detach().cpu()
                scores = output["scores"].detach().cpu()
                raw_boxes = output["boxes"].detach().cpu()
                person = [
                    raw_boxes[i]
                    for i in range(raw_boxes.shape[0])
                    if int(labels[i]) == PERSON_CLASS_ID and float(scores[i]) >= _SCORE_THRESHOLD
                ]
                if not person:
                    continue
                areas = [(b[2] - b[0]) * (b[3] - b[1]) for b in person]
                best = person[int(max(range(len(areas)), key=lambda i: areas[i]))]
                boxes.append((float(best[0]), float(best[1]), float(best[2]), float(best[3])))
    finally:
        model.to("cpu")
        if device.type == "cuda":
            torch.cuda.empty_cache()
    return boxes


def _detect_mediapipe(
    video: torch.Tensor,
    sample_count: int,
) -> list[tuple[float, float, float, float]]:
    import mediapipe as mp

    pose_api = mp.solutions.pose
    height, width = int(video.shape[1]), int(video.shape[2])
    indices = sample_indices(video.shape[0], sample_count)
    boxes: list[tuple[float, float, float, float]] = []
    with pose_api.Pose(static_image_mode=True, model_complexity=1, min_detection_confidence=0.5) as pose:
        for index in indices:
            rgb = _frame_to_uint8_rgb(video[index])
            result = pose.process(rgb)
            if result.pose_landmarks is None:
                continue
            xs, ys = [], []
            for landmark in result.pose_landmarks.landmark:
                if landmark.visibility < 0.4:
                    continue
                xs.append(landmark.x * width)
                ys.append(landmark.y * height)
            if len(xs) < 4:
                continue
            # Pose landmarks sit inside the body; pad to approximate a person box.
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            bw, bh = max(x2 - x1, 1.0), max(y2 - y1, 1.0)
            x1 = max(0.0, x1 - bw * 0.18)
            x2 = min(float(width), x2 + bw * 0.18)
            y1 = max(0.0, y1 - bh * 0.22)
            y2 = min(float(height), y2 + bh * 0.08)
            boxes.append((x1, y1, x2, y2))
    return boxes


def detect_person_boxes(
    video: torch.Tensor,
    sample_count: int = _DEFAULT_SAMPLES,
) -> list[tuple[float, float, float, float]]:
    """Detect the largest person box on sampled frames. video is [F,H,W,C] RGB 0-1."""
    errors: list[str] = []
    try:
        boxes = _detect_torchvision(video, sample_count)
        if boxes:
            return boxes
        errors.append("torchvision: no person box")
    except Exception as exc:
        errors.append(f"torchvision: {exc}")
        print(f"[H3 LVM] person_crop: Faster R-CNN 不可用，尝试备用检测: {exc}")

    try:
        boxes = _detect_mediapipe(video, sample_count)
        if boxes:
            print(f"[H3 LVM] person_crop: using MediaPipe Pose fallback, detections={len(boxes)}")
            return boxes
        errors.append("mediapipe: no person box")
    except Exception as exc:
        errors.append(f"mediapipe: {exc}")

    raise RuntimeError(" ; ".join(errors))


def crop_video_to_person(
    video: torch.Tensor,
    expand_percent: float = 0.0,
    sample_count: int = _DEFAULT_SAMPLES,
) -> tuple[torch.Tensor, Optional[tuple[int, int, int, int]]]:
    """Crop video to the detected person window.

    Returns (cropped_or_original_video, crop_rect_or_None).
    If detection fails, the original tensor is returned unchanged.
    """
    if video.ndim != 4:
        raise ValueError(f"Expected IMAGE tensor [F,H,W,C], got shape {tuple(video.shape)}")

    height, width = int(video.shape[1]), int(video.shape[2])
    try:
        boxes = detect_person_boxes(video, sample_count=sample_count)
    except Exception as exc:
        logger.warning("H3 LVM person_crop: detection failed: %s", exc)
        print(f"[H3 LVM] person_crop: 人物检测失败，跳过裁剪: {exc}")
        return video, None

    if not boxes:
        logger.warning("H3 LVM person_crop: no person detected, skip crop")
        print("[H3 LVM] person_crop: 未检测到人物，跳过裁剪")
        return video, None

    try:
        x, y, w, h = fit_crop_window(width, height, boxes, expand_percent, keep_aspect=True)
    except ValueError as exc:
        print(f"[H3 LVM] person_crop: 裁剪窗口无效，跳过: {exc}")
        return video, None
    if x == 0 and y == 0 and w == width and h == height:
        print("[H3 LVM] person_crop: 检测框已覆盖全画幅，无需裁剪")
        return video, (x, y, w, h)

    cropped = apply_crop(video, x, y, w, h)
    print(
        f"[H3 LVM] person_crop: {width}x{height} -> {w}x{h} @ ({x},{y}), "
        f"expand={expand_percent:g}%, detections={len(boxes)}"
    )
    return cropped, (x, y, w, h)
