"""Per-image guide strength for MiniMax H3, without touching the ComfyUI kernel.

Why this file exists: native H3 has exactly one visual-condition strength, the
global minimax_visual_cond_noise_aug conditioning kwarg, and it applies to every
keyframe and reference in the prompt at once. Chaining several Add Guide calls with
different global values cannot produce per-image strengths either - the last one
wins, because the payload carries a single number. Scaling the latent by a factor is
not a strength either: the row keeps its near-clean timestep label, so the model
reads the injected noise as CONTENT and paints it as texture distortion.

The two things a per-image strength actually needs (the same split ComfyUI-H3Studio
arrived at, and the reason core's own global knob works):

1. blend that one condition latent toward noise, a*z + (1-a)*noise - the
   flow-matching forward process at time a;
2. relabel that one condition row's modulation timestep to max(t_video, a), so the
   model is told "this row is this uncertain" and reads the noise as UNCERTAINTY
   instead of content.

Doing only one of the two is the failure mode the task forbids: noise without a
matching label. So both are installed together or neither is, and install() says
plainly why it refused.

Contract with the model (installed by install(), verified against the live source):
  a keyframe/reference dict may carry "noise_aug": float - one value per visual
  condition BLOCK, in the real payload order (keyframes with a latent, then refs
  with a latent), which is NOT the card order and is not the card count.
  * blocks without the key keep stock behaviour bit for bit, including core's own
    global blend and the global timestep label;
  * no block carries it -> the patch is inert, so ordinary H3 workflows in the same
    process are unaffected;
  * the payload/segment counts must agree, or this raises instead of guessing.

Only H3 Guide Timeline v2 writes the key, and only when a runnable image card asks
for less than full strength. The stable node never installs this.
"""
from __future__ import annotations

import inspect
import logging
import textwrap

import torch

logger = logging.getLogger(__name__)

# The key one visual condition block carries its own strength in. Core ignores
# unknown keyframe keys (comfy/model_base.py only reads resolved_frame_index /
# latent / audio_latent), so adding it cannot change what a v1 prompt does.
NOISE_AUG_KEY = "noise_aug"

# Marker attribute on the patched methods, so a second install() is a no-op and a
# foreign patch of the same region is recognisable instead of a silent double edit.
PATCH_MARKER = "_h3lvm_row_strength"

# Foreign marker we know about: ComfyUI-H3Studio rewrites the same timestep table
# with its own per-row mechanism. Two rewrites of one block is not a stack we can
# reason about, so v2 refuses to run at reduced strength rather than guess.
FOREIGN_MARKERS = (("_guide_row_aug", "ComfyUI-H3Studio"),)

# Role-pinned noise seeds, one per image card, keyed by the frame it anchors. Not the
# sampler seed and deliberately not the position in the run: a given strength must
# always produce the same guide, and muting or reordering another card must not change
# this card's noise. Two running image cards never share a frame, so the key is unique.
# Same reasoning as core's "every condition intentionally restarts the same RNG stream".
STRENGTH_NOISE_SEED_BASE = 917

_installed = None
_reason = ""


def install_reason() -> str:
    """Why install() refused, in the words the node shows the user."""
    return _reason



# --- The per-condition table ---
def visual_condition_blocks(payload: dict) -> list:
    """The visual condition blocks in the order the model actually packs them.

    Mirrors comfy/model_base.py:2237 (keyframes with a latent, in list order) plus
    :2242 (refs that carry a latent, in list order). Card order and card count are
    irrelevant here: the input positive may already hold first/last frames or guides
    from other nodes, and ordinary reference images ride in refs.
    """
    blocks = []
    for keyframe in payload.get("keyframes") or ():
        if keyframe.get("latent") is not None:
            blocks.append(keyframe)
    for ref in payload.get("refs") or ():
        if "latent" in ref:
            blocks.append(ref)
    return blocks


def visual_row_augs(payload: dict) -> list:
    """Per-block strengths aligned with cond_video_latents; None when none carry one.

    Entries are float for a block with its own strength and None for a block that
    must keep the global behaviour, so a mixed prompt stays exact on both sides.
    """
    blocks = visual_condition_blocks(payload)
    if not any(NOISE_AUG_KEY in block for block in blocks):
        return None
    augs = [float(block[NOISE_AUG_KEY]) if NOISE_AUG_KEY in block else None
            for block in blocks]
    rows = len(payload.get("cond_video_latents") or ())
    if rows != len(augs):
        raise RuntimeError(
            "H3 Guide Timeline v2: 逐图强度无法对齐 - payload 里有 %d 个视觉条件 latent，"
            "但按 keyframes/refs 推出的条件块是 %d 个。当前 ComfyUI 或另一个插件改变了"
            "视觉条件的组装顺序，本节点已停止执行而不是猜测对应关系。" % (rows, len(augs)))
    return augs


def row_timestep_labels(payload: dict, layout, seg_t: dict, t_video: float) -> list:
    """One modulation timestep per packed segment.

    With no per-block strength anywhere this returns exactly what core computes
    today, which is what keeps ordinary workflows untouched.
    """
    augs = visual_row_augs(payload)
    if augs is None:
        return [seg_t[kind] for _, _, kind in layout.segments]
    labels = []
    index = 0
    for _, _, kind in layout.segments:
        if kind in ("cond", "ref_img"):
            if index >= len(augs):
                raise RuntimeError(
                    "H3 Guide Timeline v2: 逐图强度无法对齐 - 打包布局里的第 %d 个视觉条件段"
                    "没有对应的条件块。" % (index + 1))
            value = augs[index]
            labels.append(seg_t[kind] if value is None else max(t_video, float(value)))
            index += 1
        else:
            labels.append(seg_t[kind])
    if index != len(augs):
        raise RuntimeError(
            "H3 Guide Timeline v2: 逐图强度无法对齐 - 条件块有 %d 个，布局里的视觉条件段只有 %d 个。"
            % (len(augs), index))
    return labels


# --- Node side: mark one keyframe and blend its latent to match ---
def flow_blend(latent, coefficient: float, seed: int):
    """a*z + (1-a)*noise - the flow forward at time a, with a pinned seed.

    The dtype is preserved: core casts to float32 when it builds the rows anyway, so
    storing the blended latent in the encoder's own dtype keeps memory behaviour the
    same as an unblended guide.
    """
    if coefficient >= 1.0:
        return latent
    original = latent.dtype
    work = latent.to(torch.float32)
    generator = torch.Generator("cpu").manual_seed(int(seed))
    noise = torch.randn(work.shape, generator=generator, dtype=torch.float32)
    blended = coefficient * work + (1.0 - coefficient) * noise.to(work.device)
    return blended.to(original)


def apply_image_strength(keyframe: dict, strength: float, slot: int) -> float:
    """Attach one image keyframe's strength and blend its latent to match.

    a = strength * VISUAL_COND_TIMESTEP: the blend coefficient and the row label are
    the same number, which is the point of the patch. "slot" only picks the noise
    role and must be stable for one card across runs. Returns the coefficient so the
    caller can log it.
    """
    from comfy.ldm.minimax.model import VISUAL_COND_TIMESTEP

    coefficient = round(float(strength) * float(VISUAL_COND_TIMESTEP), 6)
    keyframe[NOISE_AUG_KEY] = coefficient
    if keyframe.get("latent") is not None:
        keyframe["latent"] = flow_blend(
            keyframe["latent"], coefficient, STRENGTH_NOISE_SEED_BASE + int(slot))
    return coefficient



# --- The model adaptation ---
_CVR_EXPECTED = '''def _cond_video_rows(self, payload, device):
    """Concatenated visual condition rows (normalized latents -> patchified), with condition noise augmentation."""
    rows = []
    aug = payload.get("visual_cond_noise_aug", VISUAL_COND_TIMESTEP)
    seed = int(payload.get("seed", 0))
    # every condition intentionally restarts the same RNG stream
    for z in payload.get("cond_video_latents", []):
        r = patchify_video(z.to(torch.float32), self.patch_size)
        if aug < 1.0:
            gen = torch.Generator("cpu").manual_seed(seed)
            noise = torch.randn(r.shape, generator=gen, dtype=torch.float32)
            r = aug * r + (1.0 - aug) * noise.to(r.device)
        rows.append(r.to(device))
    return torch.cat(rows, dim=0) if rows else None
'''

# anchor 1: the distinct-timestep set (the labels themselves come from the helper)
_FWD_OLD_1 = """\
    unique_t = sorted({t_v, t_a} | {seg_t[k] for _, _, k in layout.segments}
                      | (set(video_rows_t.unique().tolist()) if video_rows_t is not None else set())
                      | (set(audio_rows_t.unique().tolist()) if audio_rows_t is not None else set()))
    t_row = {t: i for i, t in enumerate(unique_t)}
"""

_FWD_NEW_1 = """\
    _h3lvm_seg_t = _h3lvm_row_labels(payload, layout, seg_t, t_v)
    unique_t = sorted({t_v, t_a} | set(_h3lvm_seg_t)
                      | (set(video_rows_t.unique().tolist()) if video_rows_t is not None else set())
                      | (set(audio_rows_t.unique().tolist()) if audio_rows_t is not None else set()))
    t_row = {t: i for i, t in enumerate(unique_t)}
"""

# anchor 2: the per-segment modulation table
_FWD_OLD_2 = """\
    mod_segments = []
    for a, b, kind in layout.segments:
        row_base = t_row[seg_t[kind]] * 3
"""

_FWD_NEW_2 = """\
    mod_segments = []
    for _h3lvm_si, (a, b, kind) in enumerate(layout.segments):
        row_base = t_row[_h3lvm_seg_t[_h3lvm_si]] * 3
"""


def _cond_video_rows_patched(self, payload, device):
    """Row builder that leaves already-blended conditions alone.

    A block with its own strength arrives final - the node blended it with a pinned
    seed, and re-blending it with the global value would change both the coefficient
    and the noise. Every other block keeps core's global blend exactly as written.
    """
    import comfy.ldm.minimax.model as minimax_model

    rows = []
    aug = payload.get("visual_cond_noise_aug", minimax_model.VISUAL_COND_TIMESTEP)
    row_augs = visual_row_augs(payload)
    seed = int(payload.get("seed", 0))
    for index, z in enumerate(payload.get("cond_video_latents", [])):
        r = minimax_model.patchify_video(z.to(torch.float32), self.patch_size)
        own = row_augs[index] if row_augs is not None else None
        if own is None and aug < 1.0:
            gen = torch.Generator("cpu").manual_seed(seed)
            noise = torch.randn(r.shape, generator=gen, dtype=torch.float32)
            r = aug * r + (1.0 - aug) * noise.to(r.device)
        rows.append(r.to(device))
    return torch.cat(rows, dim=0) if rows else None


def _forget_helpers(minimax_model) -> None:
    for name in ("_h3lvm_row_labels",):
        minimax_model.__dict__.pop(name, None)


def install() -> bool:
    """Install the model adaptation once per process. Cached; install_reason() explains a no."""
    global _installed
    if _installed is None:
        _installed = _install()
    return _installed


def _install(minimax_model=None) -> bool:
    # The module argument is a test seam: a stub module can exercise the refusal
    # paths without touching the live kernel. install() itself stays no-argument.
    global _reason
    if minimax_model is None:
        try:
            import comfy.ldm.minimax.model as minimax_model
        except Exception:
            _reason = ("当前 ComfyUI 里没有 MiniMax H3 的模型代码（comfy.ldm.minimax.model "
                       "无法导入），逐图强度无法启用。")
            return False

    model_cls = getattr(minimax_model, "MiniMaxH3Model", None)
    if model_cls is None:
        _reason = "当前 ComfyUI 的模型代码里找不到 MiniMaxH3Model，逐图强度无法启用。"
        return False
    row_builder = getattr(model_cls, "_cond_video_rows", None)
    forward = getattr(model_cls, "_forward", None)
    if getattr(forward, PATCH_MARKER, False) and getattr(row_builder, PATCH_MARKER, False):
        _reason = ""
        return True
    for marker, name in FOREIGN_MARKERS:
        if getattr(forward, marker, False) or getattr(row_builder, marker, False):
            _reason = ("另一个插件（%s）已经改写过 H3 的逐条件加噪与时间标签，两处改写无法可靠"
                       "叠加，本节点不会猜测合并后的结果。" % name)
            return False
    try:
        cvr_src = textwrap.dedent(inspect.getsource(row_builder))
        fwd_src = textwrap.dedent(inspect.getsource(forward))
    except Exception as error:
        _reason = "读取当前 ComfyUI 的 H3 模型源码失败：%s" % error
        return False
    if cvr_src != _CVR_EXPECTED:
        _reason = ("当前 ComfyUI 的视觉条件加噪实现与本节点适配所依据的版本不一致"
                   "（comfy/ldm/minimax/model.py 的 _cond_video_rows 已经变化）。")
        return False

    new_src = fwd_src
    for old, new in ((_FWD_OLD_1, _FWD_NEW_1), (_FWD_OLD_2, _FWD_NEW_2)):
        if new_src.count(old) != 1:
            _reason = ("当前 ComfyUI 的 H3 _forward 与本节点适配所依据的锚点不一致"
                       "（时间标签表或调制段表没有唯一匹配）。")
            return False
        new_src = new_src.replace(old, new)

    minimax_model.__dict__["_h3lvm_row_labels"] = row_timestep_labels
    try:
        namespace = {}
        exec(compile(new_src, "<h3lvm row strength _forward>", "exec"),
             minimax_model.__dict__, namespace)
        new_forward = namespace["_forward"]
    except Exception as error:
        _forget_helpers(minimax_model)
        _reason = "逐图强度的模型适配编译失败：%s" % error
        return False
    if not _self_check(new_src, minimax_model):
        _forget_helpers(minimax_model)
        return False

    setattr(new_forward, PATCH_MARKER, True)
    setattr(_cond_video_rows_patched, PATCH_MARKER, True)
    model_cls._forward = new_forward
    model_cls._cond_video_rows = _cond_video_rows_patched
    _reason = ""
    logger.info("H3 Guide Timeline v2: 已启用逐图引导强度的模型适配。")
    return True


def _self_check(new_src: str, minimax_model) -> bool:
    """Run the rewritten timestep table on a real layout before trusting it.

    Two cheap invariants: one label per packed segment, and every label is a key of
    the modulation index table. With no per-block strength anywhere the labels must
    equal what core computes today - that is what keeps ordinary H3 workflows in the
    same process untouched. With strengths set, only the marked rows move.
    """
    global _reason
    head = "    _h3lvm_seg_t = "
    tail = "    t_row = {t: i for i, t in enumerate(unique_t)}"
    if head not in new_src or tail not in new_src:
        _reason = "逐图强度的模型适配自检失败：改写后的源码里找不到时间标签表。"
        return False
    start = new_src.index(head)
    end = new_src.index(tail, start) + len(tail)
    body = ("def _h3lvm_probe(payload, layout, seg_t, t_v, t_a, video_rows_t, audio_rows_t):\n"
            + new_src[start:end] + "\n    return _h3lvm_seg_t, t_row\n")
    try:
        env = {"_h3lvm_row_labels": row_timestep_labels}
        exec(compile(body, "<h3lvm row strength self-check>", "exec"), env)
        probe = env["_h3lvm_probe"]

        t_v, t_a = 0.4, 0.3
        vis_t = float(minimax_model.VISUAL_COND_TIMESTEP)
        seg_t = {"text": t_v, "video": t_v, "audio": t_a,
                 "cond": max(t_v, vis_t), "ref_img": max(t_v, vis_t),
                 "cond_audio": max(t_a, 0.9), "ref_audio": max(t_a, 0.9)}
        keyframes = [{"resolved_frame_index": 0, "latent": torch.zeros(1, 24, 1, 4, 4)},
                     {"resolved_frame_index": 4, "latent": torch.zeros(1, 24, 1, 4, 4)}]
        refs = [{"kind": "image", "latent_h": 4, "latent_w": 4,
                 "latent": torch.zeros(1, 24, 1, 4, 4)}]
        layout = minimax_model.PackedLayout(6, 7, 4, 4, 4, keyframes=keyframes, refs=refs)
        kinds = [kind for _, _, kind in layout.segments]

        # the blocks come from the payload, exactly as model_base.py assembles them
        payload = {"keyframes": keyframes, "refs": refs,
                   "cond_video_latents": [None, None, None]}
        stock, t_row = probe(payload, layout, dict(seg_t), t_v, t_a, None, None)
        if len(stock) != len(kinds) or any(v != seg_t[k] for v, k in zip(stock, kinds)):
            _reason = "逐图强度的模型适配自检失败：没有强度时，时间标签与原生实现不一致。"
            return False
        if not set(stock) <= set(t_row):
            _reason = "逐图强度的模型适配自检失败：时间标签没有进入调制索引表。"
            return False

        keyframes[1]["noise_aug"] = 0.7
        refs[0]["noise_aug"] = 0.65
        marked, t_row2 = probe(payload, layout, dict(seg_t), t_v, t_a, None, None)
        expect = [seg_t["text"], seg_t["cond"], max(t_v, 0.7), max(t_v, 0.65)]
        expect += [seg_t["audio"], seg_t["video"]]
        if marked != expect:
            _reason = "逐图强度的模型适配自检失败：带强度的条件段没有拿到自己的时间标签。"
            return False
        if not set(marked) <= set(t_row2):
            _reason = "逐图强度的模型适配自检失败：带强度的时间标签没有进入调制索引表。"
            return False
    except Exception as error:
        _reason = "逐图强度的模型适配自检未通过：%s" % error
        return False
    return True
