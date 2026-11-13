"""Document-level sampling schedule, independent of ComfyUI and torch."""
import json
import math

DEFAULT_RELEASE = {"enabled": False, "threshold": 0.9}
RELEASE_KEY = "h3lvm_image_release_sigma"


def parse_release(raw):
    data = json.loads(raw) if isinstance(raw, str) and raw.strip() else raw
    if not isinstance(data, dict) or "keyframe_release" not in data:
        return dict(DEFAULT_RELEASE)
    value = data["keyframe_release"]
    if not isinstance(value, dict) or not isinstance(value.get("enabled", False), bool):
        raise ValueError("关键帧阶段控制必须包含布尔 enabled 与 0–1 阈值。")
    threshold = value.get("threshold", 0.9)
    if isinstance(threshold, bool):
        raise ValueError("关键帧释放阈值必须是 0–1 的有限数值。")
    try:
        threshold = float(threshold)
    except (ValueError, TypeError):
        raise ValueError("关键帧释放阈值必须是 0–1 的有限数值。") from None
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("关键帧释放阈值必须是 0–1 的有限数值。")
    return {"enabled": value.get("enabled", False), "threshold": threshold}


def release_fingerprint(raw):
    config = parse_release(raw)
    return ("|image_release_sigma=%s" % config["threshold"]) if config["enabled"] else ""
