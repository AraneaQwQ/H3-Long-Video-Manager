"""The per-image strength adaptation in comfyui/h3_strength_patch.py.

Nothing here samples a model. What is checked is the contract that module claims:

- the per-block table is aligned with the order the model really packs visual
  conditions in (keyframes with a latent, then refs with a latent), which is not
  card order and not the card count;
- a block without a strength keeps core's numbers exactly, so an ordinary H3
  workflow in the same process cannot notice the patch is installed;
- the rewritten _forward keeps core's timestep table when nothing is marked and
  moves only the marked rows when something is;
- install() refuses in Chinese instead of guessing when the kernel under it has
  changed or another plugin rewrote the same block.
"""

import importlib.util
import os
import sys
import types
import unittest

import torch

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)


def _comfy_roots():
    env_root = os.environ.get("COMFYUI_ROOT")
    if env_root:
        yield env_root
    custom_nodes = os.path.dirname(REPO)
    if os.path.basename(custom_nodes) == "custom_nodes":
        yield os.path.dirname(custom_nodes)


def _load_patch():
    # The module has no package-relative imports, so it loads standalone; that also
    # keeps these tests about the patch itself rather than about the whole plugin.
    last_error = None
    for root in _comfy_roots():
        if root not in sys.path:
            sys.path.insert(0, root)
        try:
            spec = importlib.util.spec_from_file_location(
                "h3lvm_strength_patch",
                os.path.join(REPO, "comfyui", "h3_strength_patch.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module, None
        except Exception as exc:
            last_error = exc
    return None, last_error


PATCH, LOAD_ERROR = _load_patch()

MODEL = None
if PATCH is not None:
    for _root in _comfy_roots():
        if _root not in sys.path:
            sys.path.insert(0, _root)
        try:
            import comfy.ldm.minimax.model as _model_module
            MODEL = _model_module
            break
        except Exception:
            continue

needs_patch = unittest.skipIf(PATCH is None, "the strength module did not import: %s" % LOAD_ERROR)
needs_model = unittest.skipIf(MODEL is None, "this ComfyUI has no MiniMax H3 model code")


def make_latent(seed=0):
    generator = torch.Generator("cpu").manual_seed(seed)
    return torch.randn(1, 24, 2, 4, 4, generator=generator)


def seg_table(t_v=0.4, t_a=0.3, vis=0.999, aud=0.9):
    return {"text": t_v, "video": t_v, "audio": t_a, "cond": max(t_v, vis),
            "ref_img": max(t_v, vis), "cond_audio": max(t_a, aud),
            "ref_audio": max(t_a, aud)}


@needs_patch
class AlignmentTests(unittest.TestCase):
    """The per-block table must follow the payload, never the cards."""

    def test_blocks_follow_keyframes_then_refs(self):
        payload = {
            "keyframes": [{"latent": "a"}, {"resolved_frame_index": 3}, {"latent": "b"}],
            "refs": [{"kind": "image", "image": "x"}, {"kind": "video", "latent": "c"}],
        }
        self.assertEqual([b["latent"] for b in PATCH.visual_condition_blocks(payload)],
                         ["a", "b", "c"])

    def test_no_strength_anywhere_is_inert(self):
        payload = {"keyframes": [{"latent": "a"}], "refs": [],
                   "cond_video_latents": ["a"]}
        self.assertIsNone(PATCH.visual_row_augs(payload))

    def test_holes_keep_the_alignment(self):
        payload = {"keyframes": [{"latent": "a", "noise_aug": 0.8}, {"latent": "b"}],
                   "refs": [{"kind": "image", "latent": "c", "noise_aug": 0.65}],
                   "cond_video_latents": ["a", "b", "c"]}
        self.assertEqual(PATCH.visual_row_augs(payload), [0.8, None, 0.65])

    def test_a_count_mismatch_refuses_to_guess(self):
        payload = {"keyframes": [{"latent": "a", "noise_aug": 0.8}, {"latent": "b"}],
                   "refs": [], "cond_video_latents": ["a"]}
        with self.assertRaises(RuntimeError) as caught:
            PATCH.visual_row_augs(payload)
        self.assertIn("逐图强度无法对齐", str(caught.exception))


@needs_model
class LabelTests(unittest.TestCase):
    """The rewritten modulation table: core's numbers first, strengths second."""

    def pack(self, keyframes, refs=None):
        return MODEL.PackedLayout(6, 7, 4, 4, 4, keyframes=keyframes, refs=refs)

    def payload_for(self, keyframes, refs=None):
        blocks = [k for k in keyframes if k.get("latent") is not None]
        blocks += [r for r in (refs or []) if "latent" in r]
        return {"keyframes": keyframes, "refs": refs or [],
                "cond_video_latents": [b["latent"] for b in blocks]}

    def one_of_every_kind(self):
        blank = torch.zeros(1, 24, 1, 4, 4)
        keyframes = [{"resolved_frame_index": 0, "latent": blank},
                     {"resolved_frame_index": 4, "latent": blank}]
        refs = [{"kind": "image", "latent_h": 4, "latent_w": 4, "latent": blank}]
        return keyframes, refs

    def test_labels_match_core_when_nothing_is_marked(self):
        keyframes, refs = self.one_of_every_kind()
        layout = self.pack(keyframes, refs)
        table = seg_table()
        labels = PATCH.row_timestep_labels(self.payload_for(keyframes, refs), layout,
                                           dict(table), 0.4)
        self.assertEqual(labels, [table[kind] for _, _, kind in layout.segments])

    def test_only_marked_rows_move(self):
        keyframes, refs = self.one_of_every_kind()
        layout = self.pack(keyframes, refs)
        table = seg_table()
        payload = self.payload_for(keyframes, refs)
        stock = PATCH.row_timestep_labels(payload, layout, dict(table), 0.4)
        keyframes[1]["noise_aug"] = 0.7
        refs[0]["noise_aug"] = 0.65
        labels = PATCH.row_timestep_labels(payload, layout, dict(table), 0.4)
        kinds = [kind for _, _, kind in layout.segments]
        expect = list(stock)
        seen = 0
        for index, kind in enumerate(kinds):
            if kind in ("cond", "ref_img"):
                if seen == 1:
                    expect[index] = max(0.4, 0.7)
                elif seen == 2:
                    expect[index] = max(0.4, 0.65)
                seen += 1
        self.assertEqual(labels, expect)
        self.assertEqual(seen, 3)
        self.assertNotEqual(labels, stock)

    def test_a_row_is_never_labelled_below_the_target_stream(self):
        keyframes, refs = self.one_of_every_kind()
        layout = self.pack(keyframes, refs)
        table = seg_table(t_v=0.95)
        payload = self.payload_for(keyframes, refs)
        keyframes[0]["noise_aug"] = 0.7
        labels = PATCH.row_timestep_labels(payload, layout, dict(table), 0.95)
        kinds = [kind for _, _, kind in layout.segments]
        first = kinds.index("cond")
        self.assertEqual(labels[first], 0.95)

    def test_a_layout_mismatch_refuses_to_guess(self):
        keyframes, refs = self.one_of_every_kind()
        layout = self.pack(keyframes[:1])
        payload = self.payload_for(keyframes, refs)
        keyframes[0]["noise_aug"] = 0.7
        with self.assertRaises(RuntimeError) as caught:
            PATCH.row_timestep_labels(payload, layout, dict(seg_table()), 0.4)
        self.assertIn("逐图强度无法对齐", str(caught.exception))


@needs_patch
class BlendTests(unittest.TestCase):
    """a*z + (1-a)*noise with a pinned seed: the same strength is the same guide."""

    def test_flow_blend_is_pinned_to_its_seed(self):
        source = make_latent(3)
        first = PATCH.flow_blend(source, 0.8, 917)
        same = PATCH.flow_blend(source, 0.8, 917)
        other = PATCH.flow_blend(source, 0.8, 918)
        self.assertTrue(torch.equal(first, same))
        self.assertFalse(torch.equal(first, other))
        self.assertFalse(torch.equal(first, source))

    def test_flow_blend_keeps_the_encoder_dtype(self):
        source = make_latent(3).to(torch.bfloat16)
        self.assertEqual(PATCH.flow_blend(source, 0.7, 1).dtype, torch.bfloat16)

    def test_full_strength_changes_nothing(self):
        source = make_latent(3)
        self.assertIs(PATCH.flow_blend(source, 1.0, 1), source)

    @needs_model
    def test_apply_image_strength_marks_and_blends(self):
        source = make_latent(5)
        keyframe = {"latent": source}
        coefficient = PATCH.apply_image_strength(keyframe, 0.8, 2)
        self.assertAlmostEqual(coefficient, 0.8 * MODEL.VISUAL_COND_TIMESTEP, places=6)
        self.assertAlmostEqual(keyframe["noise_aug"], coefficient, places=9)
        self.assertFalse(torch.equal(keyframe["latent"], source))

    @needs_model
    def test_apply_image_strength_marks_a_keyframe_without_a_latent(self):
        keyframe = {"resolved_frame_index": 3}
        PATCH.apply_image_strength(keyframe, 0.6, 0)
        self.assertIn("noise_aug", keyframe)


class ForeignModel:
    """Another plugin already rewrote the same block (ComfyUI-H3Studio's marker)."""

    def _cond_video_rows(self, payload, device):
        return None

    def _forward(self, payload):
        return None


setattr(ForeignModel._forward, "_guide_row_aug", True)


class DriftedModel:
    """A kernel whose visual-condition blending no longer looks like the one we read."""

    def _cond_video_rows(self, payload, device):
        return None

    def _forward(self, payload):
        return None


def stub_module(model_cls=None):
    module = types.ModuleType("stub_minimax_model")
    module.VISUAL_COND_TIMESTEP = 0.999
    if model_cls is not None:
        module.MiniMaxH3Model = model_cls
    return module


class _Encoder:
    patch_size = (1, 2, 2)


@needs_patch
class InstallTests(unittest.TestCase):
    def setUp(self):
        PATCH._reason = ""

    def tearDown(self):
        PATCH._reason = ""

    def test_a_model_without_the_class_is_refused(self):
        self.assertFalse(PATCH._install(stub_module()))
        self.assertIn("MiniMaxH3Model", PATCH.install_reason())

    def test_a_foreign_patch_of_the_same_block_is_refused(self):
        self.assertFalse(PATCH._install(stub_module(ForeignModel)))
        self.assertIn("ComfyUI-H3Studio", PATCH.install_reason())

    def test_a_changed_kernel_is_refused(self):
        self.assertFalse(PATCH._install(stub_module(DriftedModel)))
        self.assertIn("_cond_video_rows", PATCH.install_reason())

    @needs_model
    def test_install_on_this_comfyui(self):
        self.assertTrue(PATCH.install(), PATCH.install_reason())
        self.assertEqual(PATCH.install_reason(), "")
        self.assertTrue(getattr(MODEL.MiniMaxH3Model._forward, PATCH.PATCH_MARKER, False))
        self.assertTrue(getattr(MODEL.MiniMaxH3Model._cond_video_rows,
                                 PATCH.PATCH_MARKER, False))

    @needs_model
    def test_installing_twice_does_not_rewrite_twice(self):
        self.assertTrue(PATCH.install(), PATCH.install_reason())
        forward = MODEL.MiniMaxH3Model._forward
        row_builder = MODEL.MiniMaxH3Model._cond_video_rows
        self.assertTrue(PATCH.install(), PATCH.install_reason())
        self.assertIs(MODEL.MiniMaxH3Model._forward, forward)
        self.assertIs(MODEL.MiniMaxH3Model._cond_video_rows, row_builder)

    @needs_model
    def test_refusals_leave_the_live_kernel_alone(self):
        for stub in (stub_module(), stub_module(ForeignModel), stub_module(DriftedModel)):
            PATCH._install(stub)
        PATCH._reason = ""
        self.assertTrue(PATCH.install(), PATCH.install_reason())
        self.assertEqual(PATCH.install_reason(), "")

    @needs_model
    def test_a_marked_condition_is_not_blended_twice(self):
        self.assertTrue(PATCH.install(), PATCH.install_reason())
        first, second = make_latent(1), make_latent(2)
        payload = {
            "keyframes": [{"latent": first, "noise_aug": 0.8}, {"latent": second}],
            "refs": [],
            "cond_video_latents": [first, second],
            "visual_cond_noise_aug": 0.5,
            "seed": 7,
        }
        rows = MODEL.MiniMaxH3Model._cond_video_rows(
            _Encoder(), payload, torch.device("cpu"))
        per_block = MODEL.patchify_video(first.to(torch.float32), (1, 2, 2)).shape[0]
        self.assertTrue(torch.equal(rows[:per_block],
                                    MODEL.patchify_video(first.to(torch.float32), (1, 2, 2))))
        plain = MODEL.patchify_video(second.to(torch.float32), (1, 2, 2))
        generator = torch.Generator("cpu").manual_seed(7)
        noise = torch.randn(plain.shape, generator=generator, dtype=torch.float32)
        self.assertTrue(torch.allclose(rows[per_block:], 0.5 * plain + 0.5 * noise,
                                       atol=1e-6))

    @needs_model
    def test_an_unmarked_prompt_keeps_the_global_blend(self):
        self.assertTrue(PATCH.install(), PATCH.install_reason())
        first, second = make_latent(4), make_latent(6)
        payload = {
            "keyframes": [{"latent": first}, {"latent": second}],
            "refs": [],
            "cond_video_latents": [first, second],
            "visual_cond_noise_aug": 0.5,
            "seed": 11,
        }
        rows = MODEL.MiniMaxH3Model._cond_video_rows(
            _Encoder(), payload, torch.device("cpu"))
        per_block = MODEL.patchify_video(first.to(torch.float32), (1, 2, 2)).shape[0]
        for index, source in enumerate((first, second)):
            plain = MODEL.patchify_video(source.to(torch.float32), (1, 2, 2))
            generator = torch.Generator("cpu").manual_seed(11)
            noise = torch.randn(plain.shape, generator=generator, dtype=torch.float32)
            part = rows[index * per_block:(index + 1) * per_block]
            self.assertTrue(torch.allclose(part, 0.5 * plain + 0.5 * noise, atol=1e-6))
