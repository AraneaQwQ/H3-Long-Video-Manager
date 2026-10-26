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
- the v2 first-pass node can expose its document to the independent second-pass
  node; that link carries editor data, not conditioning or a latent.

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
    MAX_GUIDE_TOTAL, SCHEMA_VERSION, STRENGTH_MAX, audio_span_frames, count_runnable,
    execution_digest, execution_digest_v2, frame_count_from_latent_t,
    guide_fingerprint, guide_fingerprint_v2, guide_frames_for, has_reduced_strength,
    is_muted_image, normalize_strength, parse_guides, parse_guides_v2,
    serialize_guides, sort_for_execution, sort_for_execution_v2, summary,
    validate_guides, validate_guides_v2,
)
from ..core.ref_media import resolve_media_path
from ..core.ref_size import MAX_SOURCE_PIXELS
# One table of media folders and one audio decoder for the whole plugin: the two
# loader nodes already resolved both, and a second implementation here could only
# drift away from what the panels upload.
from .ref_nodes import _decode_audio_file, _media_roots
# v2 only. Importing this module never touches the model: install() does, and only
# when a v2 run actually asks for less than full strength.
from .h3_strength_patch import apply_image_strength, install_reason, install as install_strength_patch

logger = logging.getLogger(__name__)

GUIDE_NODE_ID = "H3 Guide Timeline"
# v2 is a second node, not a rename: the stable id above keeps its document format
# and its execution, and old workflows keep pointing at it.
GUIDE_NODE_V2_ID = "H3 Guide Timeline v2"
GUIDE_NODE_V2_B_ID = "H3 Guide Timeline v2 B"

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



def _keyframes_of(conditioning) -> list:
    try:
        return list(conditioning[0][1].get("minimax_keyframes") or [])
    except (AttributeError, IndexError, TypeError):
        return []


def _keyframe_ids(conditioning) -> set:
    """Identity of the keyframes a conditioning already carries.

    The native node copies the list and appends one dict, so "what is new after this
    call" is exactly the keyframe this node just created. A card number is therefore
    never treated as a keyframe number: the input positive may already hold first and
    last frames or another node's guides, and ordinary reference images are not
    keyframes at all.
    """
    return {id(keyframe) for keyframe in _keyframes_of(conditioning)}


def _mark_new_keyframe_strength(conditioning, before: set, strength: float,
                                slot: int, guide: dict) -> None:
    """Attach one card's strength to the keyframe its own encode just produced.

    "slot" is the frame the card anchors, not its position in the run: two running
    image cards can never share a frame, and a frame-keyed noise role means muting or
    reordering one card cannot change another card's guide.
    """
    created = [k for k in _keyframes_of(conditioning) if id(k) not in before]
    if len(created) != 1:
        raise ValueError(
            "「%s」的引导强度无法定位：原生 Add Guide 这次新增了 %d 个 keyframe，"
            "本节点只在恰好新增一个时写入强度，不会猜。" % (guide["label"], len(created)))
    apply_image_strength(created[0], strength, slot)


def _ui_document(guides: list, frame_count: int, with_strength: bool = False) -> dict:
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
        "digest": execution_digest_v2(guides) if with_strength else execution_digest(guides),
        "summary": summary(guides, frame_count),
    }]}


class H3GuideTimeline(io.ComfyNode):
    """Image and audio guides on a timeline; one node instead of a chain of Add Guide."""

    # The one switch between the stable node and v2. Everything else is shared code,
    # so the stable node cannot drift while v2 grows a feature.
    STRENGTH_ENABLED = False
    DUAL_CHANNEL = False
    DOCUMENT_OUTPUT = False
    SHARED_DOCUMENT_INPUT = False
    LOG_TAG = GUIDE_NODE_ID

    @classmethod
    def _parse(cls, guides) -> list:
        """v2 documents carry a strength; v1 documents never do."""
        return parse_guides_v2(guides) if cls.STRENGTH_ENABLED else parse_guides(guides)

    @classmethod
    def _ordered(cls, parsed: list) -> list:
        """The cards that will actually be encoded, in run order.

        v2 drops the 0.00 image cards here and nowhere else, so the header pass, the
        VAE requirement, the validation and the encode loop all agree about what runs.
        The cards themselves stay in the document, the digest and the cache key, which
        is what makes 0.00 -> 0.05 re-run instead of replaying a cached pass-through.
        """
        if cls.STRENGTH_ENABLED:
            return sort_for_execution_v2(parsed)
        return sort_for_execution(parsed)

    @classmethod
    def _node_output(cls, first, second, parsed: list, frame_count: int,
                     document=DEFAULT_GUIDES) -> io.NodeOutput:
        ui = _ui_document(parsed, frame_count, cls.STRENGTH_ENABLED)
        results = [first]
        if cls.DUAL_CHANNEL:
            results.append(second)
        if cls.DOCUMENT_OUTPUT:
            results.append(document)
        return io.NodeOutput(*results, ui=ui)

    @classmethod
    def _validate(cls, parsed: list, frame_count: int, spans: dict, image_frames: dict) -> list:
        if cls.STRENGTH_ENABLED:
            return validate_guides_v2(parsed, frame_count, spans=spans, image_frames=image_frames)
        return validate_guides(parsed, frame_count, spans=spans, image_frames=image_frames)

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
                        "只给编辑器的时间尺用：填目标时间轴长度（秒），面板按 秒 × 24fps 换算成帧并向上对齐到"
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
    def validate_inputs(cls, guides, length_seconds=0.0, **_):
        try:
            cls._parse(guides)
        except ValueError as exc:
            return str(exc)
        return True

    @classmethod
    def fingerprint_inputs(cls, guides, **_):
        """Execution identity: the guide list plus the real bytes behind each file.

        Deliberately not the widget string - the panel also stores the selected card
        and the timeline zoom in that JSON, and moving a slider must not re-encode
        thirty guides.
        """
        try:
            digest = guide_fingerprint_v2 if cls.STRENGTH_ENABLED else guide_fingerprint
            return digest(cls._parse(guides), _media_roots())
        except Exception:
            return repr(guides)

    @classmethod
    def execute(cls, positive=None, latent=None, guides=DEFAULT_GUIDES, length_seconds=0.0,
                vae=None, audio_vae=None, positive_b=None, enable_a=True,
                enable_b=False, latent_b=None, shared_guides=None) -> io.NodeOutput:
        return cls._run(positive, latent, guides, length_seconds=length_seconds,
                        vae=vae, audio_vae=audio_vae, positive_b=positive_b,
                        enable_a=enable_a, enable_b=enable_b, latent_b=latent_b,
                        shared_guides=shared_guides)

    @classmethod
    def _run(cls, positive=None, latent=None, guides=DEFAULT_GUIDES, length_seconds=0.0,
             vae=None, audio_vae=None, positive_b=None, enable_a=True,
             enable_b=False, latent_b=None, shared_guides=None) -> io.NodeOutput:
        if cls.SHARED_DOCUMENT_INPUT and shared_guides is not None:
            guides = shared_guides
        parsed = cls._parse(guides)
        ordered = cls._ordered(parsed)
        channels = [{"name": "一采", "active": not cls.DUAL_CHANNEL or enable_a,
                     "conditioning": positive, "latent": latent}]
        if cls.DUAL_CHANNEL:
            channels.append({"name": "二采", "active": bool(enable_b),
                             "conditioning": positive_b,
                             "latent": latent_b if latent_b is not None else latent})
            missing = [channel["name"] for channel in channels
                       if channel["active"] and channel["conditioning"] is None]
            if missing:
                raise ValueError("%s：%s通道已启用，但没有连接对应的 positive。"
                                 % (cls.LOG_TAG, "、".join(missing)))
        active_channels = [channel for channel in channels if channel["active"]]
        second = channels[1]["conditioning"] if cls.DUAL_CHANNEL else None
        if not ordered:
            muted = [guide for guide in parsed if is_muted_image(guide)]
            if muted:
                print("[%s] %d 张图片 Guide 的引导强度是 0.00，本次没有要编码的素材，positive 原样透传"
                      % (cls.LOG_TAG, len(muted)))
            else:
                print("[%s] 没有启用且已放置的 Guide，positive 原样透传" % cls.LOG_TAG)
            return cls._node_output(channels[0]["conditioning"], second, parsed, 0, guides)
        if not active_channels:
            print("[%s] 一采与二采 Guide 均已停用，两路 positive 原样透传" % cls.LOG_TAG)
            return cls._node_output(channels[0]["conditioning"], second, parsed, 0, guides)

        native, table = _native_add_guide()
        for channel in active_channels:
            channel_frames, why = _latent_frame_count(channel["latent"], table)
            if not channel_frames:
                if cls.DUAL_CHANNEL:
                    raise ValueError("%s：%s" % (channel["name"], why))
                raise ValueError(why)
            channel["frame_count"] = channel_frames
        frame_count = active_channels[0]["frame_count"]

        # Counted from what actually runs, not from the document: a 0.00 image card is
        # never encoded, so it must not be the reason the node asks for a video VAE.
        counts = count_runnable(ordered)
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

        for channel in active_channels:
            channel_problems = cls._validate(
                parsed, channel["frame_count"], spans, image_frames)
            if cls.DUAL_CHANNEL:
                problems.extend("%s：%s" % (channel["name"], problem)
                                for problem in channel_problems)
            else:
                problems.extend(channel_problems)
        if problems:
            raise ValueError("Guide 校验未通过：\n  - " + "\n  - ".join(problems))

        # Pass 2 - one media at a time: decode, hand it to the native node, drop it.
        # The conditioning is what grows across the loop, never the media, so thirty
        # guides cost one image and one waveform at a time.
        # v2 only: a card between 0.05 and 0.95 needs the model adaptation, and it has
        # to be there before the first encode. Falling back to the global strength
        # silently would run a different prompt than the one the user built. A 0.00
        # card is not in the ordered list at all, so it never asks for the adaptation.
        per_image = cls.STRENGTH_ENABLED and has_reduced_strength(ordered)
        if per_image and not install_strength_patch():
            raise ValueError("%s 需要逐图引导强度，但它无法在当前 ComfyUI 上启用：%s"
                             % (cls.LOG_TAG, install_reason()))

        for guide in ordered:
            image = audio = None
            if guide["kind"] == IMAGE_KIND:
                image = _decode_image_frames(resolve_media_path(roots, guide["asset"]))
            else:
                audio = audios.pop(guide["id"], None)
                if audio is None:
                    audio = _decode_audio_window(resolve_media_path(roots, guide["asset"]), guide)
            for channel in active_channels:
                conditioned = channel["conditioning"]
                before = _keyframe_ids(conditioned) if cls.STRENGTH_ENABLED else None
                result = native.execute(
                    conditioned, channel["latent"], int(guide["frame_index"]),
                    vae=vae, audio_vae=audio_vae, image=image, audio=audio)
                conditioned = result[0] if isinstance(result, io.NodeOutput) else result
                channel["conditioning"] = conditioned
                if cls.STRENGTH_ENABLED and guide["kind"] == IMAGE_KIND:
                    strength = normalize_strength(guide.get("strength"))
                    if strength < STRENGTH_MAX:
                        _mark_new_keyframe_strength(conditioned, before, strength,
                                                    int(guide["frame_index"]), guide)
            del image, audio

        keyframe_counts = [len(_keyframes_of(channel["conditioning"]))
                           for channel in active_channels]
        channel_note = ("；通道：" + "、".join(channel["name"] for channel in active_channels)
                        if cls.DUAL_CHANNEL else "")
        print("[%s] %d guides anchored (%d image / %d audio) on a %d frame video "
              "(%.3f s @ %d FPS); conditioning now carries %s keyframes%s%s"
              % (cls.LOG_TAG, len(ordered), counts[IMAGE_KIND], counts[AUDIO_KIND],
                 frame_count, frame_count / float(DEFAULT_FPS), DEFAULT_FPS,
                 "/".join(str(count) for count in keyframe_counts),
                 " (per-image strength)" if per_image else "", channel_note))
        second = channels[1]["conditioning"] if cls.DUAL_CHANNEL else None
        return cls._node_output(channels[0]["conditioning"], second, parsed, frame_count, guides)



class H3GuideTimelineV2(H3GuideTimeline):
    """The stable timeline plus a per-image guide strength.

    A second node, not a rename. It reuses the media reading, the validation, the
    ordering and the native Add Guide chain above, and differs only in the schema
    strings and the strength path - so the stable node and its saved workflows stay
    exactly as they are.
    """

    STRENGTH_ENABLED = True
    DOCUMENT_OUTPUT = True
    LOG_TAG = GUIDE_NODE_V2_ID
    _RETURN_TYPES = None
    _RETURN_NAMES = None
    _OUTPUT_IS_LIST = None
    _OUTPUT_TOOLTIPS = None

    @classmethod
    def define_schema(cls) -> io.Schema:
        schema = super().define_schema()
        schema.node_id = GUIDE_NODE_V2_ID
        schema.display_name = "H3 Guide 时间轴 v2"
        schema.description = (
            "与「H3 Guide 时间轴」同等的图片/音频时间轴，另外可以为每张图片 Guide 单独设置引导强度："
            "1.00 与原生 Add Guide 一致；0.05-0.95 数值越低，这张图对画面的约束越弱，动作与场景衔接的自由度越大；"
            "0.00 表示这张图片不加入 conditioning：卡片、插入位置和强度值都保留，但本次不解码、不编码。"
            "强度只作用于本节点新建的图片条件：首尾帧、上游已有的 Guide、普通参考图和全部音频条件都保持原生参数。"
            "强度范围 0.00-1.00、步进 0.05，音频没有强度项。两个 VAE 端口和接线方式与旧节点一致，可以一直连着，"
            "执行时按实际生效的素材决定是否调用：强度 0.00 的图片不需要视频 VAE。"
            "当前 ComfyUI 无法启用逐图强度时本节点会明确报错，不会静默退回全局强度。"
            "本节点只负责一采；二采使用独立的信息传输节点，避免跨采样阶段形成依赖环。")
        schema.outputs.append(io.String.Output(
            display_name="共享 Guide 文档",
            tooltip="连接到「H3 Guide 时间轴 v2（二采信息传输）」的共享 Guide 文档输入；只传编辑数据，不传 conditioning 或 latent。"))
        for item in schema.inputs:
            if getattr(item, "id", None) == "guides":
                item.tooltip = (
                    "Guide 列表的 JSON（由「打开 Guide 编辑器」的面板读写，也可以直接编辑）。格式与"
                    "「H3 Guide 时间轴」一致，只是图片条目多一个 strength（0.00-1.00，缺省 1.00，"
                    "缺字段按 1.00 读取；0.00 表示这张图片不加入 conditioning）。strength 计入执行指纹："
                    "改强度会重新编码，改选中卡片、缩放或滚动时间轴不会。")
        return schema

class H3GuideTimelineV2B(H3GuideTimelineV2):
    """Apply the first-pass v2 document to an independent second-pass condition."""

    DOCUMENT_OUTPUT = False
    LOG_TAG = GUIDE_NODE_V2_B_ID
    _RETURN_TYPES = None
    _RETURN_NAMES = None
    _OUTPUT_IS_LIST = None
    _OUTPUT_TOOLTIPS = None

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=GUIDE_NODE_V2_B_ID,
            display_name="H3 Guide 时间轴 v2（二采信息传输）",
            description=(
                "把一采 v2 的共享 Guide 文档应用到独立的二采 positive / latent。"
                "本节点没有编辑器、时间轴或本地 Guide 文档；素材、时间位置和逐图强度都在一采 v2 中编辑。"
                "关闭「启用二采 Guide」时不读取文档、不校验 latent、不调用 VAE，positive 原样透传。"),
            category="H3/Guide",
            inputs=[
                io.Conditioning.Input(
                    "positive", display_name="二采 positive",
                    tooltip="二采 Reference to Video 的 positive；关闭 Guide 或没有生效素材时原样透传。"),
                io.Latent.Input(
                    "latent", display_name="二采 latent",
                    tooltip="二采 MiniMax H3 AV latent，尺寸、帧数与音频轨长度均从本输入读取。"),
                io.String.Input(
                    "shared_guides", display_name="共享 Guide 文档", optional=True, force_input=True,
                    tooltip="连接一采 v2 的「共享 Guide 文档」输出。本端口只传编辑数据，不传 conditioning 或 latent。"),
                io.Vae.Input("vae", optional=True, tooltip="视频 VAE：共享文档中有实际生效的图片 Guide 时必须连接。"),
                io.Vae.Input("audio_vae", optional=True, tooltip="音频 VAE：共享文档中有实际生效的音频 Guide 时必须连接。"),
                io.Boolean.Input(
                    "enable_guide", display_name="启用二采 Guide", default=True,
                    label_on="开启", label_off="关闭",
                    tooltip="开启后应用共享 Guide；关闭后不读取文档、不编码，二采 positive 原样透传。"),
            ],
            outputs=[io.Conditioning.Output(display_name="二采 positive")],
        )

    @classmethod
    def validate_inputs(cls, shared_guides=None, enable_guide=True, **_):
        if not enable_guide or shared_guides is None:
            return True
        try:
            cls._parse(shared_guides)
        except ValueError as exc:
            return str(exc)
        return True

    @classmethod
    def fingerprint_inputs(cls, shared_guides=None, enable_guide=True, **_):
        if not enable_guide:
            return "guide_disabled"
        if shared_guides is None:
            return "guide_enabled|missing_shared_document"
        return super().fingerprint_inputs(shared_guides) + "|guide_enabled=1"

    @classmethod
    def execute(cls, positive=None, latent=None, shared_guides=None,
                vae=None, audio_vae=None, enable_guide=True) -> io.NodeOutput:
        if not enable_guide:
            return io.NodeOutput(positive)
        if shared_guides is None:
            raise ValueError(
                "%s：请连接一采 v2 的「共享 Guide 文档」，或关闭「启用二采 Guide」。"
                % cls.LOG_TAG)
        return cls._run(positive, latent, shared_guides,
                        vae=vae, audio_vae=audio_vae)


NODE_LIST = [H3GuideTimeline, H3GuideTimelineV2, H3GuideTimelineV2B]
