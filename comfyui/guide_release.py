"""Instance-local H3 keyframe release: no global or kernel modifications."""
from __future__ import annotations
import logging
import math

from comfy_api.latest import io
from ..core.guide_release import RELEASE_KEY

logger = logging.getLogger(__name__)
WRAPPER_KEY = "h3lvm_image_keyframe_release"
WINDOW_MARKER = "_h3lvm_release_native_window"


def condition_latents(keyframes, refs):
    keyframes, refs = keyframes or [], refs or []
    return {
        "cond_video_latents": [k["latent"] for k in keyframes if k.get("latent") is not None]
                              + [r["latent"] for r in refs if "latent" in r],
        "cond_audio_latents": [k["audio_latent"] for k in keyframes if k.get("audio_latent") is not None]
                              + [r["audio_latent"] for r in refs if r.get("audio_latent") is not None],
    }


def release_payload(payload, sigma):
    """Pure filter; untouched calls return the exact original payload."""
    if not payload or not payload.get("keyframes"):
        return payload
    retained = []
    changed = False
    for keyframe in payload["keyframes"]:
        threshold = keyframe.get(RELEASE_KEY)
        if threshold is not None and keyframe.get("latent") is not None:
            if not math.isfinite(float(threshold)) or not 0 <= float(threshold) <= 1:
                raise ValueError("H3 时间轴的关键帧释放阈值无效。")
            if sigma < float(threshold):
                changed = True
                # A combined block may still contain an audio guide: release only its image.
                if keyframe.get("audio_latent") is not None:
                    retained.append({k: v for k, v in keyframe.items()
                                     if k not in ("latent", RELEASE_KEY, "noise_aug")})
                continue
        retained.append(keyframe)
    if not changed:
        return payload
    result = dict(payload, keyframes=retained, layout=None)
    result.update(condition_latents(retained, payload.get("refs")))
    return result


def preserve_window_metadata(native_window):
    """Delegate all cropping to core; copy metadata onto each source's own outputs.

    Core reconstructs dictionaries when slicing. Running its unchanged implementation
    on each original block avoids matching by frame, tensor identity, or card position.
    This stays local to the MODEL object patch and preserves existing noise_aug too.
    """
    native_window = getattr(native_window, WINDOW_MARKER, native_window)

    def window_payload(payload, window):
        keyframes = payload.get("keyframes") or []
        if not any(RELEASE_KEY in k for k in keyframes):
            return native_window(payload, window)
        retained = []
        result = None
        for original in keyframes:
            result = native_window(dict(payload, keyframes=[original]), window)
            for cropped in result.get("keyframes") or []:
                if cropped.get("latent") is not None:
                    cropped = dict(cropped)
                    for key in (RELEASE_KEY, "noise_aug"):
                        if key in original:
                            cropped[key] = original[key]
                retained.append(cropped)
        result = dict(result, keyframes=retained, layout=None)
        result.update(condition_latents(retained, payload.get("refs")))
        return result

    setattr(window_payload, WINDOW_MARKER, native_window)
    return window_payload


def patch_model(model, log_forwards=False):
    import comfy.patcher_extension

    # Resolve from this patcher so an earlier instance-local adaptation is respected.
    try:
        native_window = model.get_model_object("_window_payload")
    except (AttributeError, KeyError):
        raise ValueError("关键帧阶段控制需要支持 H3 _window_payload 的 ComfyUI MODEL。") from None
    if not callable(native_window):
        raise ValueError("当前 MODEL 不支持 H3 关键帧分窗，无法启用阶段控制。")

    def release(executor, x, timestep, context, transformer_options, minimax_payload=None, **kwargs):
        sigma = float(timestep.flatten()[0]) / 1000.0
        filtered = release_payload(minimax_payload, sigma)
        if log_forwards and any(RELEASE_KEY in k for k in (minimax_payload or {}).get("keyframes", [])):
            before = sum(k.get("latent") is not None for k in minimax_payload["keyframes"])
            after = sum(k.get("latent") is not None for k in filtered["keyframes"])
            logger.info("[H3 Guide Release] sigma=%.9f image_keyframes=%d->%d", sigma, before, after)
        return executor(x, timestep, context, transformer_options,
                        minimax_payload=filtered, **kwargs)

    patched = model.clone()
    wrapper_type = comfy.patcher_extension.WrappersMP.DIFFUSION_MODEL
    patched.remove_wrappers_with_key(wrapper_type, WRAPPER_KEY)
    patched.add_wrapper_with_key(wrapper_type, WRAPPER_KEY, release)
    patched.add_object_patch("_window_payload", preserve_window_metadata(native_window))
    return patched


class H3GuideKeyframeRelease(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3 Guide Keyframe Release", display_name="H3 Guide 关键帧阶段控制",
            category="H3/Guide",
            description="连接时间轴阶段控制的 MODEL 补丁。低于文档阈值后停止直接提供本时间轴图片；保留其他条件。无需 Remake LoRA。",
            inputs=[io.Model.Input("model"),
                    io.Boolean.Input("enabled", default=True, label_on="开启", label_off="关闭"),
                    io.Boolean.Input("log_forwards", default=False,
                                     tooltip="在控制台记录每次模型前向的 sigma 与图片关键帧保留数量，用于验证释放。")],
            outputs=[io.Model.Output(display_name="model")])

    @classmethod
    def execute(cls, model, enabled=True, log_forwards=False):
        return io.NodeOutput(patch_model(model, log_forwards) if enabled else model)
