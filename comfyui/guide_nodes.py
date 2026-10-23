"""H3 Guide Timeline: many native Add Guide nodes in one node, edited on a timeline.

Why this exists: the native MiniMaxH3AddGuide anchors exactly one image or one
audio per node, so a shot with three pose images and one voice line is three or
four nodes chained by hand, and the frame numbers only exist inside each node's
widget. This node keeps the same semantics and one list instead: the user wires
positive, the H3 AV latent and both VAEs once, and places guides on a two-lane
timeline.

What is deliberately NOT here (see GUIDE_TIMELINE.md for the full contract):
- no ref_images / ref_audios outputs - reference material is the two loader nodes;
  a guide is a time anchor, not a reference slot.
- no fixed row of 32 media sockets - the list is walked at run time.
- no snapping to 17n+5 or the Motion Context options - the native node does not
  snap, so neither do we.
- no guide_list socket - nothing in this plugin produces one yet, so the merge
  point stays internal (core.guide_timeline.merge_guides).

Execution is the native node, called once per guide, each result feeding the next.
That is what makes "same guides, same frames" equal to a hand-wired chain: the
keyframe list is appended in call order and PackedLayout packs it in list order,
so the list is sorted by frame before anything is encoded.
"""
from __future__ import annotations

import logging
import wave

import numpy as np
import torch
from PIL import Image, ImageOps

from comfy_api.latest import io

from ..core.guide_timeline import (
    AUDIO_KIND, DEFAULT_FPS, IMAGE_KIND, MAX_GUIDE_AUDIOS, MAX_GUIDE_IMAGES,
    MAX_GUIDE_TOTAL, SCHEMA_VERSION, audio_span_frames, count_runnable,
    execution_digest, frame_count_from_latent_t, guide_fingerprint,
    guide_frames_for, parse_guides, serialize_guides, sort_for_execution, summary,
    validate_guides,
)
from ..core.ref_media import resolve_media_path
from ..core.ref_size import MAX_SOURCE_PIXELS
# One table of media folders and one audio decoder for the whole plugin: the two
# loader nodes already resolved both, and a second implementation here could only
# drift away from what the panels upload.
from .ref_nodes import _decode_audio_file, _media_roots

logger = logging.getLogger(__name__)

GUIDE_NODE_ID = "H3 Guide Timeline"

# The empty document, not "[]": the panel and the node always see the same shape,
# and a saved workflow carries the version it was written with.
DEFAULT_GUIDES = '{"schema_version":%d,"fps":%d,"guides":[]}' % (SCHEMA_VERSION, DEFAULT_FPS)

# Resolved once per process. A ComfyUI without the native node must not break the
# plugin import, so this is lazy and the failure is a message about this node only.
_NATIVE = None
_NATIVE_ERROR = None


def _native_add_guide():
    """Return (MiniMaxH3AddGuide, FRAME_PER_TOKEN) from the running ComfyUI."""
    global _NATIVE, _NATIVE_ERROR
    if _NATIVE is not None:
        return _NATIVE
    if _NATIVE_ERROR is not None:
        raise RuntimeError(_NATIVE_ERROR)
    try:
        from comfy.ldm.minimax.model import FRAME_PER_TOKEN as table
        from comfy_extras.nodes_minimax_h3 import MiniMaxH3AddGuide
    except Exception as exc:  # pragma: no cover - depends on the ComfyUI build
        _NATIVE_ERROR = (
            "本插件的「H3 Guide 时间轴」需要当前 ComfyUI 提供原生 MiniMaxH3AddGuide "
            "(comfy_extras.nodes_minimax_h3)。这个版本里没有该节点，所以本节点不可用；"
            "本插件的其他节点不受影响。原因：%s" % exc
        )
        logger.warning("[H3 Guide Timeline] native Add Guide unavailable: %s", exc)
        raise RuntimeError(_NATIVE_ERROR)
    _NATIVE = (MiniMaxH3AddGuide, tuple(table))
    return _NATIVE


def _latent_frame_count(latent, table=None) -> tuple:
    """(frame_count, reason) for an H3 AV latent; frame_count 0 means "not one".

    Same check and same sum as the native node (nodes_minimax_h3.py:193-200). The
    panel needs the number before a run to draw a ruler, so this is a shape read,
    never a decode.
    """
    samples = None
    if isinstance(latent, dict):
        samples = latent.get("samples")
    if samples is None:
        return 0, "latent 输入是空的：请连接 MiniMax H3 的 AV latent（例如 MiniMax H3 Reference to Video 的 latent 输出）。"
    if not getattr(samples, "is_nested", False):
        return 0, "latent 不是 MiniMax H3 的 AV latent（samples 不是嵌套张量）。"
    tensors = getattr(samples, "tensors", None) or []
    if len(tensors) != 2 or tensors[0].ndim != 5 or tensors[0].shape[1] != 24:
        return 0, "latent 不是 MiniMax H3 的 AV latent：需要 [视频 24 通道 + 音频] 两个张量。"
    return frame_count_from_latent_t(int(tensors[0].shape[2]), table), ""


def _audio_window(total: int, guide: dict) -> tuple:
    """The sample range a card asks for, clamped to the real file.

    Sample points, not seconds: the card stores source_start_sample /
    source_end_sample because a float second is a rounding step away from the
    boundary the user typed. An end of 0 means "to the end of the file". Shared by
    the metadata pass and the decode so they cannot disagree about what is empty.
    """
    start = max(0, min(int(guide.get("source_start_sample") or 0), total))
    end = int(guide.get("source_end_sample") or 0)
    end = total if end <= 0 else max(0, min(end, total))
    if end <= start:
        raise ValueError(
            "裁切区间是空的：起点 %d 采样点已经在终点 %d 之后（文件只有 %d 个采样点）。"
            % (start, end, total))
    return start, end


def _image_meta(path: str) -> tuple:
    """Width and height from the file header only - no pixels decoded.

    Size is all the validator needs from an image, so it is checked before anything is
    decoded: an oversized pose image must be refused without holding it in RAM.
    """
    with Image.open(path) as image:
        if image.width <= 0 or image.height <= 0:
            raise ValueError("%s has no usable size" % path)
        if image.width * image.height > MAX_SOURCE_PIXELS:
            raise ValueError(
                "%dx%d 超过参考图允许的 %d 像素上限，请先缩小这张图"
                % (image.width, image.height, MAX_SOURCE_PIXELS))
        return int(image.width), int(image.height)


def _audio_meta(path: str):
    """Sample count and rate without loading the waveform; None when a decode is needed.

    A WAV header carries both numbers, which covers what this plugin uploads. Other
    containers have no cheap portable header here, so the caller decodes that one file
    and reuses it - the "can only be confirmed by decoding it" case.
    """
    try:
        with wave.open(path, "rb") as handle:
            frames, rate = int(handle.getnframes()), int(handle.getframerate())
    except (wave.Error, EOFError, OSError):
        return None
    if frames <= 0 or rate <= 0:
        return None
    return {"sample_count": frames, "sample_rate": rate}



def _decode_image_frames(path: str) -> torch.Tensor:
    """Decode one image file as [1, H, W, 3] float32 in 0..1.

    No resizing here on purpose: the native node resizes the guide to the latent's
    own size and aspect ("center" crop), so scaling it first would only lose detail
    and change what the user sees on the card. EXIF orientation is applied and alpha
    is dropped exactly like LoadImage does, so a transparent PNG does not become a
    random background.
    """
    with Image.open(path) as image:
        if image.width <= 0 or image.height <= 0:
            raise ValueError("%s has no usable size" % path)
        if image.width * image.height > MAX_SOURCE_PIXELS:
            raise ValueError(
                "%dx%d 超过参考图允许的 %d 像素上限，请先缩小这张图"
                % (image.width, image.height, MAX_SOURCE_PIXELS))
        rgb = ImageOps.exif_transpose(image).convert("RGB")

    array = np.asarray(rgb, dtype=np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0)


def _decode_audio_window(path: str, guide: dict) -> dict:
    """Decode an audio file and cut it to the card's sample window."""
    if _decode_audio_file is None:
        raise RuntimeError(
            "当前 ComfyUI 没有 comfy_extras.nodes_audio 的解码器，无法读取音频 Guide。")
    waveform, sample_rate = _decode_audio_file(path)
    if waveform.ndim == 2:
        waveform = waveform.unsqueeze(0)
    start, end = _audio_window(int(waveform.shape[-1]), guide)
    return {"waveform": waveform[..., start:end].clone(), "sample_rate": int(sample_rate)}



def _ui_document(guides: list, frame_count: int) -> dict:
    """The one thing the node tells the panel back: the real total frames.

    The ruler has to be drawn from the latent the workflow actually carries, and the
    only authoritative source for that is a run. Everything else in the editor comes
    from the widget, so this stays a small number plus a digest the panel can check
    against its own state.
    """
    return {"h3_guide_timeline": [{
        "schema_version": SCHEMA_VERSION,
        "fps": DEFAULT_FPS,
        "frame_count": int(frame_count or 0),
        "digest": execution_digest(guides),
        "summary": summary(guides, frame_count),
    }]}


class H3GuideTimeline(io.ComfyNode):
    """Image and audio guides on a timeline; one node instead of a chain of Add Guide."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=GUIDE_NODE_ID,
            display_name="H3 Guide 时间轴",
            description=(
                "在一个节点里管理图片与音频 Guide，并按帧把它们锚定到 MiniMax H3 的 AV latent 上："
                "内部按时间顺序逐条调用原生 Add Guide，结果依次相接，与手动串联多个 Add Guide 等价。"
                "两个 VAE 常连即可，只有图片时不调用音频编码，只有音频时不调用视频编码；"
                "没有任何启用且已放置的 Guide 时原样透传 positive。不输出 ref_images / ref_audios，"
                "也不把时间吸附到 17n+5 或 Motion Context。"),
            category="H3/Guide",
            inputs=[
                io.Conditioning.Input("positive"),
                io.Latent.Input("latent", tooltip="MiniMax H3 的 AV latent。视频总帧数由它实际算出，编辑器的时间尺也用这个数。"),
                io.Float.Input(
                    "length_seconds",
                    optional=True,
                    default=0.0,
                    min=0.0,
                    max=150.0,
                    step=0.1,
                    tooltip=(
                        "只给编辑器的时间尺用：填目标时长（秒），面板按 秒 × 24fps 换算成帧并向上对齐到"
                        " H3 的 17n+5（10 秒 → 240 → 243 帧）。0 或留空表示不设置。运行后仍以 latent 的"
                        "实际帧数为准；这个值不参与执行，也不改变输出。"),
                ),
                io.Vae.Input("vae", optional=True, tooltip="视频 VAE：有启用且已放置的图片 Guide 时必须连接；没有图片 Guide 时可以留空。"),
                io.Vae.Input("audio_vae", optional=True, tooltip="音频 VAE：有启用且已放置的音频 Guide 时必须连接；没有音频 Guide 时可以留空。"),
                io.String.Input(
                    "guides",
                    default=DEFAULT_GUIDES,
                    tooltip=(
                        "Guide 列表的 JSON（由「打开 Guide 编辑器」的面板读写，也可以直接编辑）。"
                        "每条包含 kind / label / enabled / frame_index 与素材路径；音频另有 "
                        "source_start_sample / source_end_sample 两个采样点边界。enabled=false 是停用，"
                        "frame_index 为 null 是待放置：两者都保留在列表里，但不编码、不占配额。"
                        "文档里的 resolved_frame_count 与 view_state 只是面板状态，不参与执行。"),
                ),
            ],
            outputs=[io.Conditioning.Output(display_name="positive")],
        )

    @classmethod
    def validate_inputs(cls, guides, length_seconds=0.0):
        try:
            parse_guides(guides)
        except ValueError as exc:
            return str(exc)
        return True

    @classmethod
    def fingerprint_inputs(cls, guides):
        """Execution identity: the guide list plus the real bytes behind each file.

        Deliberately not the widget string - the panel also stores the selected card
        and the timeline zoom in that JSON, and moving a slider must not re-encode
        thirty guides.
        """
        try:
            return guide_fingerprint(parse_guides(guides), _media_roots())
        except Exception:
            return repr(guides)

    @classmethod
    def execute(cls, positive, latent, guides, length_seconds=0.0, vae=None, audio_vae=None) -> io.NodeOutput:
        parsed = parse_guides(guides)
        ordered = sort_for_execution(parsed)
        if not ordered:
            print("[H3 Guide Timeline] 没有启用且已放置的 Guide，positive 原样透传")
            return io.NodeOutput(positive, ui=_ui_document(parsed, 0))

        native, table = _native_add_guide()
        frame_count, why = _latent_frame_count(latent, table)
        if not frame_count:
            raise ValueError(why)

        counts = count_runnable(parsed)
        roots = _media_roots()
        problems = []
        if counts[IMAGE_KIND] and vae is None:
            problems.append("有 %d 个启用的图片 Guide，需要连接视频 VAE（vae 输入）。" % counts[IMAGE_KIND])
        if counts[AUDIO_KIND] and audio_vae is None:
            problems.append("有 %d 个启用的音频 Guide，需要连接音频 VAE（audio_vae 输入）。" % counts[AUDIO_KIND])

        # Pass 1 - headers only. An image's size and a WAV's sample count come from
        # the file header, so an out-of-range or empty-trim guide at position 30 is
        # reported before a single pixel or sample is decoded, and no big tensor is
        # ever held while we are still deciding whether the list is legal. Only a
        # container with no cheap header (mp3, m4a, ...) is decoded here, and that
        # one waveform is reused by pass 2 instead of being decoded twice.
        image_frames, spans, audios = {}, {}, {}
        for guide in ordered:
            try:
                path = resolve_media_path(roots, guide["asset"])
                if guide["kind"] == IMAGE_KIND:
                    _image_meta(path)
                    image_frames[guide["id"]] = 1
                else:
                    meta = _audio_meta(path)
                    if meta is None:
                        audio = _decode_audio_window(path, guide)
                        audios[guide["id"]] = audio
                        meta = {
                            "sample_count": int(audio["waveform"].shape[-1]),
                            "sample_rate": int(audio["sample_rate"]),
                        }
                    start, end = _audio_window(meta["sample_count"], guide)
                    spans[guide["id"]] = audio_span_frames(end - start, meta["sample_rate"])
            except (ValueError, OSError, RuntimeError) as exc:
                problems.append("%s 的素材不可用：%s" % (guide["label"], exc))

        problems.extend(validate_guides(parsed, frame_count, spans=spans, image_frames=image_frames))
        if problems:
            raise ValueError("Guide 校验未通过：\n  - " + "\n  - ".join(problems))

        # Pass 2 - one media at a time: decode, hand it to the native node, drop it.
        # The conditioning is what grows across the loop, never the media, so thirty
        # guides cost one image and one waveform at a time.
        conditioned = positive
        for guide in ordered:
            image = audio = None
            if guide["kind"] == IMAGE_KIND:
                image = _decode_image_frames(resolve_media_path(roots, guide["asset"]))
            else:
                audio = audios.pop(guide["id"], None)
                if audio is None:
                    audio = _decode_audio_window(resolve_media_path(roots, guide["asset"]), guide)
            result = native.execute(
                conditioned, latent, int(guide["frame_index"]),
                vae=vae, audio_vae=audio_vae, image=image, audio=audio)
            conditioned = result[0] if isinstance(result, io.NodeOutput) else result
            del image, audio

        keyframes = conditioned[0][1].get("minimax_keyframes", []) if conditioned else []
        print("[H3 Guide Timeline] %d guides anchored (%d image / %d audio) on a %d frame "
              "video (%.3f s @ %d FPS); conditioning now carries %d keyframes"
              % (len(ordered), counts[IMAGE_KIND], counts[AUDIO_KIND], frame_count,
                 frame_count / float(DEFAULT_FPS), DEFAULT_FPS, len(keyframes)))
        return io.NodeOutput(conditioned, ui=_ui_document(parsed, frame_count))



NODE_LIST = [H3GuideTimeline]