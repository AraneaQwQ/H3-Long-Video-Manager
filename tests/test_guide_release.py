"""Sampling-stage filtering tested against native H3 AddGuide/window/patcher APIs."""
import copy
import importlib
import json
import math
import os
import shutil
import types
import unittest
from unittest import mock

import torch
from PIL import Image
from core.guide_release import RELEASE_KEY, parse_release, release_fingerprint
from tests import test_guide_nodes as native
from tests._temp_dir import make_temp_dir


class DocumentTests(unittest.TestCase):
    def test_legacy_documents_keep_the_old_fingerprint(self):
        for raw in (None, "", "[]", [], {"guides": []}, '{"keyframe_release":{"enabled":false}}'):
            self.assertFalse(parse_release(raw)["enabled"])
            self.assertEqual(release_fingerprint(raw), "")

    def test_threshold_is_not_an_inverted_progress_percentage(self):
        config = {"keyframe_release": {"enabled": True, "threshold": 0.9}}
        self.assertEqual(parse_release(json.dumps(config)), {"enabled": True, "threshold": 0.9})
        self.assertIn("0.9", release_fingerprint(config))

    def test_invalid_configuration_is_rejected(self):
        for value in (None, [], {"enabled": "yes"}, {"threshold": None}, {"threshold": True},
                      {"threshold": -0.1}, {"threshold": 1.1}, {"threshold": math.nan}, {"threshold": math.inf}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_release({"keyframe_release": value})


@unittest.skipIf(native.LOAD_ERROR is not None, str(native.LOAD_ERROR))
class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.release = importlib.import_module("h3lvm.comfyui.guide_release")
        self.marked = {"resolved_frame_index": 0, "latent": torch.ones(1, 24, 1, 4, 4),
                       RELEASE_KEY: 0.9, "noise_aug": 0.5}
        self.video = {"resolved_frame_index": 5, "latent": torch.ones(1, 24, 6, 4, 4)}
        self.audio = {"resolved_frame_index": 0, "audio_latent": torch.zeros(1, 32, 2, 20)}
        self.refs = [{"latent": torch.zeros(1, 24, 1, 4, 4)},
                     {"audio_latent": torch.ones(1, 32, 2, 20)}]
        self.payload = {"keyframes": [self.marked, self.audio, self.video], "refs": self.refs,
                        "layout": object(), "seed": 123, "other": object()}
        self.payload.update(self.release.condition_latents(self.payload["keyframes"], self.refs))

    def test_high_and_equal_sigma_preserve_original_identity(self):
        for sigma in (1.0, 0.9):
            self.assertIs(self.release.release_payload(self.payload, sigma), self.payload)

    def test_low_sigma_rebuilds_layout_and_both_latent_lists_without_mutation(self):
        out = self.release.release_payload(self.payload, 0.8)
        self.assertEqual(out["keyframes"], [self.audio, self.video])
        self.assertIsNone(out["layout"])
        self.assertIs(out["refs"], self.refs)
        self.assertIs(out["other"], self.payload["other"])
        self.assertEqual(len(out["cond_video_latents"]), 2)
        self.assertIs(out["cond_video_latents"][0], self.video["latent"])
        self.assertIs(out["cond_video_latents"][1], self.refs[0]["latent"])
        self.assertIs(out["cond_audio_latents"][0], self.audio["audio_latent"])
        self.assertIs(out["cond_audio_latents"][1], self.refs[1]["audio_latent"])
        self.assertEqual(len(self.payload["keyframes"]), 3)
        self.assertIsNotNone(self.payload["layout"])
        self.assertIs(self.release.release_payload(self.payload, 1.0), self.payload)

    def test_threshold_zero_and_starting_below_one(self):
        self.marked[RELEASE_KEY] = 0.0
        self.assertIs(self.release.release_payload(self.payload, 0.0), self.payload)
        self.marked[RELEASE_KEY] = 1.0
        self.assertEqual(len(self.release.release_payload(self.payload, 0.99)["keyframes"]), 2)

    def test_combined_audio_is_preserved_when_image_is_released(self):
        self.marked["audio_latent"] = self.audio["audio_latent"]
        out = self.release.release_payload(self.payload, 0.1)
        self.assertIs(out["keyframes"][0]["audio_latent"], self.marked["audio_latent"])
        self.assertNotIn("latent", out["keyframes"][0])
        self.assertNotIn("noise_aug", out["keyframes"][0])

    def test_real_native_window_retains_schedule_and_strength(self):
        from comfy.model_base import MiniMaxH3
        base = MiniMaxH3.__new__(MiniMaxH3)
        torch.nn.Module.__init__(base)
        window = types.SimpleNamespace(total_frames=12, index_list=list(range(7)))
        window.get_window_for_modality = lambda _: types.SimpleNamespace(index_list=list(range(20)))
        expected = base._window_payload(self.payload, window)
        wrapped = self.release.preserve_window_metadata(base._window_payload)
        out = wrapped(self.payload, window)
        self.assertEqual(len(out["keyframes"]), len(expected["keyframes"]))
        self.assertEqual(out["keyframes"][0][RELEASE_KEY], 0.9)
        self.assertEqual(out["keyframes"][0]["noise_aug"], 0.5)
        for actual, old in zip(out["keyframes"], expected["keyframes"]):
            self.assertEqual(actual["resolved_frame_index"], old["resolved_frame_index"])
            for kind in ("latent", "audio_latent"):
                if kind in old:
                    torch.testing.assert_close(actual[kind], old[kind], rtol=0, atol=0)
        self.assertEqual(len(self.release.release_payload(out, 0.1)["cond_video_latents"]), 2)
        self.assertIs(getattr(self.release.preserve_window_metadata(wrapped), self.release.WINDOW_MARKER).__self__, base)

    def test_real_model_patcher_cloning_and_wrapper_execution(self):
        from comfy.model_base import MiniMaxH3
        from comfy.model_patcher import ModelPatcher
        from comfy.patcher_extension import WrappersMP, WrapperExecutor
        base = MiniMaxH3.__new__(MiniMaxH3)
        torch.nn.Module.__init__(base)
        model = ModelPatcher(base, torch.device("cpu"), torch.device("cpu"))
        foreign_wrapper = lambda executor, *args, **kwargs: executor(*args, **kwargs)
        model.add_wrapper_with_key(WrappersMP.DIFFUSION_MODEL, "other_plugin", foreign_wrapper)
        schema = self.release.H3GuideKeyframeRelease.define_schema()
        self.assertEqual(schema.node_id, "H3 Guide Keyframe Release")
        self.assertEqual([i.id for i in schema.inputs], ["model", "enabled", "log_forwards"])
        from h3lvm.comfyui.nodes import NODE_LIST
        self.assertIn(self.release.H3GuideKeyframeRelease, NODE_LIST)
        patched = self.release.patch_model(model, log_forwards=True)
        twice = self.release.patch_model(patched)
        self.assertFalse(model.object_patches)
        self.assertIs(patched.get_wrappers(WrappersMP.DIFFUSION_MODEL, "other_plugin")[0], foreign_wrapper)
        self.assertEqual(len(model.get_wrappers(WrappersMP.DIFFUSION_MODEL, self.release.WRAPPER_KEY)), 0)
        self.assertEqual(len(twice.get_wrappers(WrappersMP.DIFFUSION_MODEL, self.release.WRAPPER_KEY)), 1)
        wrapper = patched.get_wrappers(WrappersMP.DIFFUSION_MODEL, self.release.WRAPPER_KEY)[0]
        # The wrapper sees the actual sigma scaling used by core; repeat low -> high.
        for sigma, count in ((1.0, 3), (0.9, 3), (0.8, 2), (1.0, 3)):
            executor = WrapperExecutor.new_executor(lambda *args, **kw: kw, [wrapper])
            result = executor.execute(None, torch.tensor([sigma * 1000], dtype=torch.float64), None, {},
                                      minimax_payload=self.payload, audio_denoise_mask="keep")
            self.assertEqual(len(result["minimax_payload"]["keyframes"]), count)
            self.assertEqual(result["audio_denoise_mask"], "keep")
        self.assertIs(self.release.H3GuideKeyframeRelease.execute(model, enabled=False).result[0], model)


@unittest.skipIf(native.LOAD_ERROR is not None, str(native.LOAD_ERROR))
class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.root = make_temp_dir("h3_release_")
        Image.new("RGB", (64, 64), "gray").save(os.path.join(self.root, "pose.png"))
        self.roots = mock.patch.object(native.GUIDE, "_media_roots", return_value={"input": self.root})
        self.roots.start()
        self.document = {"guides": [native.image_entry("pose.png", 4)],
                         "keyframe_release": {"enabled": True, "threshold": 0.9}}
        self.latent = native.av_latent()
        self.vae = native.FakeVideoVae()

    def tearDown(self):
        self.roots.stop()
        shutil.rmtree(self.root)

    def test_stable_and_v2_mark_only_new_image(self):
        upstream = {"resolved_frame_index": 0, "latent": torch.zeros(1, 24, 1, 8, 8)}
        for cls in (native.GUIDE.H3GuideTimeline, native.GUIDE.H3GuideTimelineV2):
            positive = [[torch.zeros(1, 4), {"minimax_keyframes": [upstream]}]]
            result = cls.execute(positive, self.latent, json.dumps(self.document), vae=self.vae)
            keyframes = result.result[0][0][1]["minimax_keyframes"]
            self.assertNotIn(RELEASE_KEY, keyframes[0])
            self.assertEqual(keyframes[1][RELEASE_KEY], 0.9)
            self.assertNotIn(RELEASE_KEY, upstream)

    def test_shared_document_preserves_schedule_for_second_pass(self):
        result = native.GUIDE.H3GuideTimelineV2.execute(native.conditioning(), self.latent, json.dumps(self.document), vae=self.vae)
        shared = result.result[1]
        self.assertEqual(json.loads(shared)["keyframe_release"], self.document["keyframe_release"])
        second = native.GUIDE.H3GuideTimelineV2B.execute(native.conditioning(), self.latent, shared, vae=self.vae)
        self.assertEqual(second.result[0][0][1]["minimax_keyframes"][0][RELEASE_KEY], 0.9)

    def test_release_and_strength_can_coexist_and_zero_strength_stays_muted(self):
        self.document["guides"][0]["strength"] = 0.5
        result = native.GUIDE.H3GuideTimelineV2.execute(native.conditioning(), self.latent, json.dumps(self.document), vae=self.vae)
        keyframe = result.result[0][0][1]["minimax_keyframes"][0]
        self.assertEqual(keyframe[RELEASE_KEY], 0.9)
        from comfy.ldm.minimax.model import VISUAL_COND_TIMESTEP
        self.assertEqual(keyframe["noise_aug"], 0.5 * VISUAL_COND_TIMESTEP)
        self.document["guides"][0]["strength"] = 0
        positive = native.conditioning()
        self.assertIs(native.GUIDE.H3GuideTimelineV2.execute(positive, self.latent, json.dumps(self.document)).result[0], positive)

    def test_threshold_changes_cache_but_disabled_config_does_not(self):
        cls = native.GUIDE.H3GuideTimelineV2
        first = cls.fingerprint_inputs(json.dumps(self.document))
        self.document["keyframe_release"]["threshold"] = 0.8
        self.assertNotEqual(first, cls.fingerprint_inputs(json.dumps(self.document)))
        self.document["keyframe_release"]["enabled"] = False
        disabled = cls.fingerprint_inputs(json.dumps(self.document))
        self.document.pop("keyframe_release")
        self.assertEqual(disabled, cls.fingerprint_inputs(json.dumps(self.document)))
