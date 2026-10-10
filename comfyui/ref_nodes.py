"""H3 reference loaders: one node per media type, fixed numbered output slots.

Why these exist: the official MiniMaxH3ReferenceToVideo takes ref_image_0..8 and
ref_audio_0..2 as separate numbered slots, so a real workflow needs nine image
links and three audio links. Loading each file with its own LoadImage plus a
resize node makes a wall of nodes; these two nodes manage the media as cards and
keep the nine/three links permanent. Unused slots output None, which the official
node skips (its execute does "if img is None: continue"). A card the user parked
(跳过) is filtered out before the slots are filled, so it neither outputs anything
nor shifts the numbered ports.

Image sizes follow core/ref_size.py: proportional scaling onto the 32 px H3 grid, no
cropping, and the card shows the size that was actually produced. The user picks the
resampling filter, and whether a small image is scaled up to the target megapixels or
only aligned to the grid. Audio is never resampled or remixed - H3 resamples
internally for its audio VAE - but a card may ask for a time window of it
(start / duration in seconds), and that window is the only thing cut here.
"""
from __future__ import annotations

import logging

import numpy as np
import torch
from comfy_api.latest import io
from PIL import Image, ImageOps

import folder_paths

from ..core.ref_media import (
    MAX_REF_AUDIOS, MAX_REF_IMAGES, active_entries, fill_slots, media_fingerprint,
    parse_media_list, resolve_media_path, trim_audio, trim_range,
)
from ..core.ref_size import (
    DEFAULT_MEGAPIXELS, DEFAULT_RESAMPLE_METHOD, DEFAULT_UPSCALE_SMALL_IMAGES,
    MAX_MEGAPIXELS, MAX_SOURCE_PIXELS, MIN_MEGAPIXELS, RESAMPLE_BICUBIC,
    RESAMPLE_BILINEAR, RESAMPLE_LANCZOS, RESAMPLE_METHODS, RESAMPLE_NEAREST,
    clamp_megapixels, clamp_resampling_method, plan_reference,
)
from .segment_store import DEFAULT_PROJECT

logger = logging.getLogger(__name__)

# The widget names and the Pillow filters are one table, so "the UI says Nearest"
# cannot quietly mean a different filter. Pillow moved the constants into an enum in
# 10.x; the getattr covers both.
_RESAMPLING = getattr(Image, "Resampling", Image)
RESAMPLE_FILTERS = {
    RESAMPLE_LANCZOS: _RESAMPLING.LANCZOS,
    RESAMPLE_BICUBIC: _RESAMPLING.BICUBIC,
    RESAMPLE_BILINEAR: _RESAMPLING.BILINEAR,
    RESAMPLE_NEAREST: _RESAMPLING.NEAREST,
}

IMAGE_NODE_ID = "H3 Image Reference Loader"
AUDIO_NODE_ID = "H3 Audio Reference Loader"

try:  # ComfyUI's own decoder - the same one LoadAudio uses.
    from comfy_extras.nodes_audio import load as _decode_audio_file
except Exception:  # pragma: no cover - only if ComfyUI moves the helper
    _decode_audio_file = None


def _media_roots() -> dict:
    """The folders a media reference may point at, by ComfyUI type name."""
    roots = {}
    try:
        roots["input"] = folder_paths.get_input_directory()
    except Exception:
        logger.warning("[H3 Ref Loader] input folder is unavailable")
    for name in ("output", "temp"):
        try:
            folder = folder_paths.get_directory_by_type(name)
        except Exception:
            folder = None
        if folder:
            roots[name] = folder
    return roots


def build_image_slot(path: str, megapixels, resampling_method=DEFAULT_RESAMPLE_METHOD,
                     upscale_small_images=DEFAULT_UPSCALE_SMALL_IMAGES) -> tuple:
    """Decode one image and scale the whole frame to the planned grid size.

    Returns (tensor, plan, source_size). The tensor is [1, H, W, 3] float32 in
    0..1 - the shape LoadImage produces and the H3 image encoder consumes. Alpha
    is dropped for the same reason LoadImage drops it, and an animated source
    contributes its first frame.
    """
    with Image.open(path) as image:
        source = (image.width, image.height)
        if source[0] <= 0 or source[1] <= 0:
            raise ValueError(f"{path} has no usable size")
        if source[0] * source[1] > MAX_SOURCE_PIXELS:
            raise ValueError(
                f"{source[0]}x{source[1]} is over the {MAX_SOURCE_PIXELS} pixel limit "
                "for reference images; resize it before loading it"
            )
        frame = ImageOps.exif_transpose(image)
        plan = plan_reference(frame.width, frame.height, megapixels, upscale_small_images)
        if (frame.width, frame.height) == (plan["width"], plan["height"]):
            # Already on the grid: resampling here would only soften the frame.
            rgb = frame.convert("RGB")
        else:
            resized = frame.resize(
                (plan["width"], plan["height"]), RESAMPLE_FILTERS[clamp_resampling_method(resampling_method)])
            rgb = resized.convert("RGB")

    array = np.asarray(rgb, dtype=np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0), plan, source


def build_audio_slot(path: str, start: float = 0.0, duration: float = 0.0) -> dict:
    """Decode one audio file into ComfyUI's AUDIO dict, cut to the card's window.

    H3 resamples to its audio VAE rate inside _encode_ref_audio, so the loader keeps
    the original sample rate and channel count. The only thing it may change is where
    the clip starts and how long it is, because that is what the card asked for.
    """
    if _decode_audio_file is None:
        raise RuntimeError(
            "ComfyUI's audio decoder (comfy_extras.nodes_audio) is not available in "
            "this ComfyUI version, so audio references cannot be decoded here."
        )
    waveform, sample_rate = _decode_audio_file(path)
    audio = {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}
    return trim_audio(audio, start, duration)


def _safe_fingerprint(media_files, max_items: int, extra: str = "") -> str:
    """Cache key for the media set; falls back to the raw value if it is broken."""
    try:
        entries = active_entries(parse_media_list(media_files, max_items))
        return media_fingerprint(entries, _media_roots(), extra=extra)
    except Exception:
        return repr(media_files)


class H3ImageReferenceLoader(io.ComfyNode):
    """Nine reference images in one node; card order is ref_image_0..8."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=IMAGE_NODE_ID,
            display_name="H3 图片参考加载器",
            description="集中管理 0-9 张参考图，按卡片顺序输出 ref_image_0..8；空槽输出 None；已跳过的卡片不输出、不占槽位。可按项目存取参考图预设（只存路径，不复制图片）。",
            category="H3/Reference",
            inputs=[
                io.String.Input(
                    "media_files",
                    default="[]",
                    tooltip="面板写入的 JSON 列表；卡片顺序就是 ref_image_0..8 的槽位顺序。手动写 API 时也可以直接填文件名列表。带 skip: true 的条目是已跳过的卡片：保留在列表里，但不输出、也不占槽位。",
                ),
                io.Float.Input(
                    "target_megapixels",
                    default=DEFAULT_MEGAPIXELS, min=MIN_MEGAPIXELS, max=MAX_MEGAPIXELS,
                    step=0.01, round=0.01,
                    tooltip="每张图的目标像素量（百万像素）。每张图按自己的比例算尺寸并对齐 32 像素网格，不裁切；卡片上会显示实际输出尺寸和实际 MP。",
                ),
                io.Combo.Input(
                    "resampling_method", options=list(RESAMPLE_METHODS),
                    default=DEFAULT_RESAMPLE_METHOD,
                    tooltip="缩放用的重采样算法：Lanczos 质量最好、缩小首选（较慢）；Bicubic 质量与速度折中；Bilinear 更快更柔和；Nearest 保留像素硬边，适合像素风素材。界面选哪个，后端就用哪个。",
                ),
                io.Boolean.Input(
                    "upscale_small_images", default=DEFAULT_UPSCALE_SMALL_IMAGES,
                    label_on="放大小图至目标 MP", label_off="不放大",
                    tooltip="关闭时，小图不会被放大到目标 MP，但仍会调整到 32 的倍数，以满足 H3 输入尺寸要求；最终尺寸可能略有变化。开启时，小于目标面积的图也按目标面积放大。",
                ),
                # Appended last: LGraphNode.configure() restores widget values by position.
                # It only names the project whose preset the panel reads and writes, so it
                # is deliberately not part of the cache key and never changes a pixel.
                io.String.Input(
                    "project_name",
                    default=DEFAULT_PROJECT,
                    tooltip="面板的项目预设库：决定「存为项目预设 / 载入项目预设」读写哪个项目文件夹。预设里只有参考图的路径，不复制图片；这个字段不影响本节点输出的图片。",
                ),
            ],
            outputs=[io.Image.Output(display_name=f"ref_image_{index}")
                     for index in range(MAX_REF_IMAGES)],
        )

    @classmethod
    def validate_inputs(cls, media_files, target_megapixels, resampling_method,
                        upscale_small_images, project_name=DEFAULT_PROJECT):
        try:
            parse_media_list(media_files, MAX_REF_IMAGES)
            clamp_megapixels(target_megapixels)
            clamp_resampling_method(resampling_method)
        except ValueError as exc:
            return str(exc)
        return True

    @classmethod
    def fingerprint_inputs(cls, media_files, target_megapixels, resampling_method,
                           upscale_small_images, project_name=DEFAULT_PROJECT):
        # Same file name with new bytes must not reuse the previous decode, and neither
        # may a new filter or a new size setting: all three change the pixels.
        try:
            extra = repr((
                clamp_megapixels(target_megapixels),
                clamp_resampling_method(resampling_method),
                bool(upscale_small_images),
            ))
        except ValueError:
            extra = repr((target_megapixels, resampling_method, upscale_small_images))
        return _safe_fingerprint(media_files, MAX_REF_IMAGES, extra=extra)

    @classmethod
    def execute(cls, media_files, target_megapixels, resampling_method,
                upscale_small_images, project_name=DEFAULT_PROJECT) -> io.NodeOutput:
        entries = active_entries(parse_media_list(media_files, MAX_REF_IMAGES))
        megapixels = clamp_megapixels(target_megapixels)
        method = clamp_resampling_method(resampling_method)
        upscale = bool(upscale_small_images)
        roots = _media_roots()

        def build(entry):
            path = resolve_media_path(roots, entry)
            tensor, plan, source = build_image_slot(path, megapixels, method, upscale)
            logger.info("[H3 Ref Loader] ref_image %s: %dx%d -> %dx%d (%.3f MP, %s, %s, area err %.1f%%, ratio err %.1f%%)",
                        entry["filename"], source[0], source[1], plan["width"], plan["height"],
                        plan["actual_megapixels"], plan["mode"], method,
                        plan["area_error"] * 100.0, plan["ratio_error"] * 100.0)
            return tensor

        slots = fill_slots(entries, MAX_REF_IMAGES, build)
        used = sum(1 for value in slots if value is not None)
        print(f"[H3 Ref Loader] image slots: {used}/{MAX_REF_IMAGES} filled, "
              f"{MAX_REF_IMAGES - used} are None")
        return io.NodeOutput(*slots)


class H3AudioReferenceLoader(io.ComfyNode):
    """Three standalone reference audios in one node; card order is ref_audio_0..2."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=AUDIO_NODE_ID,
            display_name="H3 音频参考加载器",
            description="集中管理 0-3 个独立参考音频，按卡片顺序输出 ref_audio_0..2；空槽输出 None；已跳过的卡片不输出、不占槽位。每张卡片可设开始时间与时长（秒，同 ComfyUI 的 TrimAudioDuration 语义），只把这一段交给 H3；不重采样、不混音。可按项目存取音频预设（只存路径与裁切窗口，不复制音频）。",
            category="H3/Reference",
            inputs=[
                io.String.Input(
                    "media_files",
                    default="[]",
                    tooltip="面板写入的 JSON 列表；卡片顺序就是 ref_audio_0..2 的槽位顺序。带 skip: true 的条目是已跳过的卡片：保留在列表里，但不输出、也不占槽位。带 start / duration（秒）的音频卡片只输出那一段：start 为负数是从片尾往前算，duration 为 0 表示到片尾。",
                ),
                # Appended last, and only used by the panel's preset buttons; see the
                # image node for why the order matters.
                io.String.Input(
                    "project_name",
                    default=DEFAULT_PROJECT,
                    tooltip="面板的项目预设库：决定「存为项目预设 / 载入项目预设」读写哪个项目文件夹。预设里只有音频的路径，不复制音频；这个字段不影响本节点输出的音频。",
                ),
            ],
            outputs=[io.Audio.Output(display_name=f"ref_audio_{index}")
                     for index in range(MAX_REF_AUDIOS)],
        )

    @classmethod
    def validate_inputs(cls, media_files, project_name=DEFAULT_PROJECT):
        try:
            parse_media_list(media_files, MAX_REF_AUDIOS)
        except ValueError as exc:
            return str(exc)
        return True

    @classmethod
    def fingerprint_inputs(cls, media_files, project_name=DEFAULT_PROJECT):
        return _safe_fingerprint(media_files, MAX_REF_AUDIOS)

    @classmethod
    def execute(cls, media_files, project_name=DEFAULT_PROJECT) -> io.NodeOutput:
        entries = active_entries(parse_media_list(media_files, MAX_REF_AUDIOS))
        roots = _media_roots()

        def build(entry):
            path = resolve_media_path(roots, entry)
            start, duration = trim_range(entry)
            audio = build_audio_slot(path, start, duration)
            waveform = audio["waveform"]
            logger.info("[H3 Ref Loader] ref_audio %s: %d samples @ %dHz, %d channel(s) "
                        "(start %.3fs, duration %.3fs)", entry["filename"], waveform.shape[-1],
                        audio["sample_rate"], waveform.shape[1], start, duration)
            return audio

        slots = fill_slots(entries, MAX_REF_AUDIOS, build)
        used = sum(1 for value in slots if value is not None)
        print(f"[H3 Ref Loader] audio slots: {used}/{MAX_REF_AUDIOS} filled, "
              f"{MAX_REF_AUDIOS - used} are None")
        return io.NodeOutput(*slots)


NODE_LIST = [H3ImageReferenceLoader, H3AudioReferenceLoader]
