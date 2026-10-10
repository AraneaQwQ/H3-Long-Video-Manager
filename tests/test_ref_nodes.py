"""Node-level tests for the H3 reference loaders (needs ComfyUI's comfy_api).

These check the contract the workflow depends on: nine IMAGE / three AUDIO slots
that always exist, real None in the unused ones, card order = slot order, and one
single-image tensor per slot. Real files are decoded, so a broken decode path
fails here instead of inside a 3-minute H3 generation.
"""

import importlib.util
import io as _io
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
import wave

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, REPO)

from core.ref_media import trim_audio  # noqa: E402  (the repo path is set up above)
from core.ref_size import (  # noqa: E402  (the repo path is set up above)
    DEFAULT_RESAMPLE_METHOD, RESAMPLE_LANCZOS, RESAMPLE_METHODS,
)


def _comfy_roots():
    env_root = os.environ.get("COMFYUI_ROOT")
    if env_root:
        yield env_root
    custom_nodes = os.path.dirname(REPO)
    if os.path.basename(custom_nodes) == "custom_nodes":
        yield os.path.dirname(custom_nodes)


def _load_ref_nodes():
    last_error = None
    for root in _comfy_roots():
        if root not in sys.path:
            sys.path.insert(0, root)
        try:
            spec = importlib.util.spec_from_file_location(
                "h3lvm",
                os.path.join(REPO, "__init__.py"),
                submodule_search_locations=[REPO],
            )
            package = importlib.util.module_from_spec(spec)
            sys.modules["h3lvm"] = package
            spec.loader.exec_module(package)
            return importlib.import_module("h3lvm.comfyui.ref_nodes"), None
        except Exception as exc:
            last_error = exc
    return None, last_error


REF, LOAD_ERROR = _load_ref_nodes()

TMP_ROOT = None


def setUpModule():
    global TMP_ROOT
    TMP_ROOT = tempfile.mkdtemp(prefix="h3lvm_ref_nodes_")


def tearDownModule():
    if TMP_ROOT:
        shutil.rmtree(TMP_ROOT, ignore_errors=True)


def make_image(name, size, color, mode="RGB", exif_orientation=None):
    from PIL import Image

    path = os.path.join(TMP_ROOT, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image = Image.new(mode, size, color)
    if exif_orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        image.save(path, exif=exif)
    else:
        image.save(path)
    return path


def make_wav(name, seconds=0.25, sample_rate=8000):
    path = os.path.join(TMP_ROOT, name)
    frames = int(seconds * sample_rate)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"".join(struct.pack("<h", int(4000 * (i % 24) / 24 - 2000))
                                    for i in range(frames)))
    return path


def json_names(names):
    return json.dumps([{"filename": name, "subfolder": "", "type": "input"} for name in names])


@unittest.skipIf(REF is None, f"comfy_api unavailable: {LOAD_ERROR}")
class TestReferenceSchema(unittest.TestCase):
    def _node(self, name):
        import h3lvm.comfyui.nodes as nodes

        return next(cls for cls in nodes.NODE_LIST if cls.__name__ == name)

    def test_both_loaders_are_registered(self):
        import h3lvm.comfyui.nodes as nodes

        names = [cls.__name__ for cls in nodes.NODE_LIST]
        self.assertIn("H3ImageReferenceLoader", names)
        self.assertIn("H3AudioReferenceLoader", names)

    def test_image_node_has_nine_numbered_image_outputs(self):
        schema = self._node("H3ImageReferenceLoader").define_schema()
        self.assertEqual([out.display_name for out in schema.outputs],
                         [f"ref_image_{index}" for index in range(9)])
        self.assertEqual({out.get_io_type() for out in schema.outputs}, {"IMAGE"})

    def test_audio_node_has_three_numbered_audio_outputs(self):
        schema = self._node("H3AudioReferenceLoader").define_schema()
        self.assertEqual([out.display_name for out in schema.outputs],
                         [f"ref_audio_{index}" for index in range(3)])
        self.assertEqual({out.get_io_type() for out in schema.outputs}, {"AUDIO"})

    def test_image_node_inputs(self):
        schema = self._node("H3ImageReferenceLoader").define_schema()
        # project_name is last on purpose: configure() restores widget values by
        # position, so a new field must never shift an existing one.
        self.assertEqual([item.id for item in schema.inputs],
                         ["media_files", "target_megapixels", "resampling_method",
                          "upscale_small_images", "project_name"])
        megapixels = next(item for item in schema.inputs if item.id == "target_megapixels")
        self.assertEqual(megapixels.default, 0.25)
        self.assertGreaterEqual(megapixels.min, 0.02)
        self.assertLessEqual(megapixels.max, 8.0)

    def test_resampling_options_are_exactly_the_planner_options(self):
        # The UI must never offer a filter the backend cannot honour, and the label
        # list and the backend enum have to come from the same tuple.
        schema = self._node("H3ImageReferenceLoader").define_schema()
        field = next(item for item in schema.inputs if item.id == "resampling_method")
        self.assertEqual(list(field.options), list(RESAMPLE_METHODS))
        self.assertEqual(list(REF.RESAMPLE_METHODS), list(RESAMPLE_METHODS))
        self.assertEqual(field.default, DEFAULT_RESAMPLE_METHOD)

    def test_upscaling_small_images_defaults_to_off(self):
        schema = self._node("H3ImageReferenceLoader").define_schema()
        field = next(item for item in schema.inputs if item.id == "upscale_small_images")
        self.assertIs(field.default, False)

    def test_audio_node_has_no_pixel_controls(self):
        schema = self._node("H3AudioReferenceLoader").define_schema()
        self.assertEqual([item.id for item in schema.inputs], ["media_files", "project_name"])

    def test_the_project_field_defaults_to_the_default_bin(self):
        for name in ("H3ImageReferenceLoader", "H3AudioReferenceLoader"):
            schema = self._node(name).define_schema()
            field = next(item for item in schema.inputs if item.id == "project_name")
            self.assertEqual(field.default, "H3_LVM")

    def test_media_field_defaults_to_an_empty_list(self):
        for name in ("H3ImageReferenceLoader", "H3AudioReferenceLoader"):
            schema = self._node(name).define_schema()
            field = next(item for item in schema.inputs if item.id == "media_files")
            self.assertEqual(field.default, "[]")


@unittest.skipIf(REF is None, f"comfy_api unavailable: {LOAD_ERROR}")
class TestImageNodeExecution(unittest.TestCase):
    def setUp(self):
        self._real_roots = REF._media_roots
        REF._media_roots = lambda: {"input": TMP_ROOT}

    def tearDown(self):
        REF._media_roots = self._real_roots

    def _run(self, names, megapixels=0.05, resampling=RESAMPLE_LANCZOS, upscale=False):
        return REF.H3ImageReferenceLoader.execute(media_files=json_names(names),
                                                  target_megapixels=megapixels,
                                                  resampling_method=resampling,
                                                  upscale_small_images=upscale).result

    def test_no_images_means_nine_none_slots(self):
        result = self._run([])
        self.assertEqual(len(result), 9)
        self.assertEqual(result, (None,) * 9)

    def test_one_image_fills_only_the_first_slot(self):
        make_image("one.png", (320, 240), (255, 0, 0))
        result = self._run(["one.png"])
        self.assertIsNotNone(result[0])
        self.assertEqual(result[1:], (None,) * 8)

    def test_slot_order_matches_card_order(self):
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255),
                  (255, 0, 255), (10, 20, 30), (200, 100, 50), (1, 2, 3)]
        names = [f"pic{index}.png" for index in range(9)]
        for name, color in zip(names, colors):
            make_image(name, (160, 120), color)
        result = self._run(names)
        for tensor, color in zip(result, colors):
            self.assertEqual(tensor.shape[0], 1, "one card must not become a batch")
            mean = tensor[0].reshape(-1, 3).mean(dim=0).tolist()
            for channel, expected in zip(mean, color):
                self.assertAlmostEqual(channel, expected / 255.0, places=2)

    def test_ten_cards_are_truncated_to_the_nine_slots(self):
        names = [f"t{index}.png" for index in range(10)]
        for name in names:
            make_image(name, (96, 96), (10, 10, 10))
        result = self._run(names)
        self.assertEqual(len(result), 9)
        self.assertEqual(sum(1 for value in result if value is None), 0)

    def test_a_parked_card_holds_no_slot_and_the_rest_close_the_gap(self):
        import json

        for index in range(3):
            make_image(f"park{index}.png", (96, 96), (20, 30, 40))
        raw = json.dumps([
            {"filename": "park0.png", "subfolder": "", "type": "input"},
            {"filename": "park1.png", "subfolder": "", "type": "input", "skip": True},
            {"filename": "park2.png", "subfolder": "", "type": "input"},
        ])
        result = REF.H3ImageReferenceLoader.execute(media_files=raw, target_megapixels=0.05,
                                                   resampling_method=RESAMPLE_LANCZOS,
                                                   upscale_small_images=False).result
        self.assertIsNotNone(result[0])
        self.assertIsNotNone(result[1])
        self.assertEqual(result[2:], (None,) * 7, "the parked card must not take a slot")

    def test_parked_cards_do_not_push_used_cards_out(self):
        import json

        names = [f"q{index}.png" for index in range(9)] + ["extra1.png", "extra2.png"]
        for name in names:
            make_image(name, (96, 96), (10, 10, 10))
        raw = json.dumps(
            [{"filename": name, "subfolder": "", "type": "input"} for name in names[:9]]
            + [{"filename": name, "subfolder": "", "type": "input", "skip": True} for name in names[9:]]
        )
        result = REF.H3ImageReferenceLoader.execute(media_files=raw, target_megapixels=0.05,
                                                   resampling_method=RESAMPLE_LANCZOS,
                                                   upscale_small_images=False).result
        self.assertEqual(sum(1 for value in result if value is None), 0)

    def test_a_parked_card_does_not_change_the_cache_key(self):
        import json

        make_image("keep.png", (96, 96), (10, 10, 10))
        make_image("park.png", (96, 96), (10, 10, 10))
        args = {"target_megapixels": 0.05, "resampling_method": RESAMPLE_LANCZOS,
                "upscale_small_images": False}
        plain = REF.H3ImageReferenceLoader.fingerprint_inputs(media_files=json_names(["keep.png"]), **args)
        with_parked = REF.H3ImageReferenceLoader.fingerprint_inputs(
            media_files=json.dumps([
                {"filename": "keep.png", "subfolder": "", "type": "input"},
                {"filename": "park.png", "subfolder": "", "type": "input", "skip": True},
            ]), **args)
        self.assertEqual(plain, with_parked, "a parked card never reaches the node, so nothing to decode")

    def test_the_project_field_never_changes_the_cache_key(self):
        # The preset bin is a panel convenience: pointing the same nine cards at
        # another project must not re-decode a single image.
        make_image("proj.png", (96, 96), (10, 10, 10))
        args = {"media_files": json_names(["proj.png"]), "target_megapixels": 0.05,
                "resampling_method": RESAMPLE_LANCZOS, "upscale_small_images": False}
        first = REF.H3ImageReferenceLoader.fingerprint_inputs(**args, project_name="story-a")
        second = REF.H3ImageReferenceLoader.fingerprint_inputs(**args, project_name="story-b")
        self.assertEqual(first, second)

    def test_output_tensor_matches_the_h3_image_convention(self):
        make_image("shape.png", (1280, 720), (9, 9, 9))
        tensor = self._run(["shape.png"], megapixels=0.25)[0]
        self.assertEqual(tensor.dtype, __import__("torch").float32)
        self.assertEqual(tensor.ndim, 4)
        _, height, width, channels = tensor.shape
        self.assertEqual(channels, 3)
        self.assertEqual(width % 32, 0)
        self.assertEqual(height % 32, 0)
        self.assertGreaterEqual(tensor.min().item(), 0.0)
        self.assertLessEqual(tensor.max().item(), 1.0)

    def test_alpha_and_grayscale_sources_still_produce_three_channels(self):
        make_image("alpha.png", (200, 100), (255, 0, 0, 128), mode="RGBA")
        make_image("gray.png", (200, 100), 128, mode="L")
        for name in ("alpha.png", "gray.png"):
            tensor = self._run([name], megapixels=0.05)[0]
            self.assertEqual(tensor.shape[-1], 3, name)

    def test_exif_orientation_is_applied_before_planning(self):
        # Stored 200x100 with orientation 6 means the picture is really 100x200,
        # so the planned frame must be portrait - same as LoadImage behaviour.
        make_image("rot.jpg", (200, 100), (200, 200, 200), exif_orientation=6)
        tensor = self._run(["rot.jpg"], megapixels=0.05)[0]
        _, height, width, _ = tensor.shape
        self.assertGreater(height, width)

    def test_missing_file_names_the_file(self):
        with self.assertRaises(ValueError) as ctx:
            self._run(["not_there.png"])
        self.assertIn("not_there.png", str(ctx.exception))

    def test_bad_json_is_reported_before_decoding(self):
        message = REF.H3ImageReferenceLoader.validate_inputs(media_files="[oops", target_megapixels=0.25,
                                                resampling_method=RESAMPLE_LANCZOS, upscale_small_images=False)
        self.assertIsInstance(message, str)
        self.assertIn("not valid JSON", message)
        self.assertIs(True, REF.H3ImageReferenceLoader.validate_inputs(media_files="[]",
                                                                     target_megapixels=0.25,
                                                resampling_method=RESAMPLE_LANCZOS, upscale_small_images=False))

    def test_out_of_range_megapixels_is_a_readable_error(self):
        message = REF.H3ImageReferenceLoader.validate_inputs(media_files="[]", target_megapixels=99.0,
                                                resampling_method=RESAMPLE_LANCZOS, upscale_small_images=False)
        self.assertIn("supported range", message)

    def test_replacing_a_file_invalidates_the_cache_key(self):
        make_image("cache.png", (120, 120), (5, 5, 5))
        before = REF.H3ImageReferenceLoader.fingerprint_inputs(media_files=json_names(["cache.png"]),
                                                             target_megapixels=0.05,
                                                resampling_method=RESAMPLE_LANCZOS, upscale_small_images=False)
        make_image("cache.png", (120, 120), (200, 5, 5))
        after = REF.H3ImageReferenceLoader.fingerprint_inputs(media_files=json_names(["cache.png"]),
                                                             target_megapixels=0.05,
                                                resampling_method=RESAMPLE_LANCZOS, upscale_small_images=False)
        self.assertNotEqual(before, after)

    def test_megapixels_are_part_of_the_cache_key(self):
        low = REF.H3ImageReferenceLoader.fingerprint_inputs(media_files="[]", target_megapixels=0.05,
                                                resampling_method=RESAMPLE_LANCZOS, upscale_small_images=False)
        high = REF.H3ImageReferenceLoader.fingerprint_inputs(media_files="[]", target_megapixels=1.0,
                                                resampling_method=RESAMPLE_LANCZOS, upscale_small_images=False)
        self.assertNotEqual(low, high)



@unittest.skipIf(REF is None, f"comfy_api unavailable: {LOAD_ERROR}")
class TestImageResizeSettings(unittest.TestCase):
    """The two resize widgets: what they promise and what the pixels actually do."""

    def setUp(self):
        self._real_roots = REF._media_roots
        REF._media_roots = lambda: {"input": TMP_ROOT}

    def tearDown(self):
        REF._media_roots = self._real_roots

    def _run(self, names, megapixels=0.05, resampling=RESAMPLE_LANCZOS, upscale=False):
        return REF.H3ImageReferenceLoader.execute(media_files=json_names(names),
                                                  target_megapixels=megapixels,
                                                  resampling_method=resampling,
                                                  upscale_small_images=upscale).result

    def _frame(self, tensor):
        height, width = int(tensor.shape[1]), int(tensor.shape[2])
        return width, height

    def test_every_option_maps_to_a_real_filter(self):
        self.assertEqual(sorted(REF.RESAMPLE_FILTERS), sorted(RESAMPLE_METHODS))

    def test_nearest_keeps_hard_edges_and_bilinear_does_not(self):
        # A 2x2 four-colour source is the smallest honest test of the filter: Nearest
        # may only ever repeat the original colours, anything interpolating cannot.
        from PIL import Image

        path = os.path.join(TMP_ROOT, "hard_edges.png")
        image = Image.new("RGB", (2, 2))
        image.putpixel((0, 0), (0, 0, 0))
        image.putpixel((1, 0), (255, 255, 255))
        image.putpixel((0, 1), (255, 0, 0))
        image.putpixel((1, 1), (0, 0, 255))
        image.save(path)

        import torch

        nearest = self._run(["hard_edges.png"], megapixels=0.05,
                            resampling="Nearest", upscale=True)[0]
        smooth = self._run(["hard_edges.png"], megapixels=0.05,
                           resampling="Bilinear", upscale=True)[0]
        nearest_colors = torch.unique(nearest[0].reshape(-1, 3).mul(255).round().int(), dim=0)
        smooth_colors = torch.unique(smooth[0].reshape(-1, 3).mul(255).round().int(), dim=0)
        self.assertEqual(nearest_colors.shape[0], 4, "Nearest must not invent colours")
        self.assertGreater(smooth_colors.shape[0], 4, "Bilinear must actually interpolate")

    def test_the_filter_choice_changes_the_pixels(self):
        # A hard-edged source, so two filters really disagree; a flat colour would
        # make every filter produce the same bytes and prove nothing.
        import torch
        from PIL import Image

        path = os.path.join(TMP_ROOT, "stripes.png")
        image = Image.new("RGB", (96, 96), (0, 0, 0))
        for x in range(0, 96, 8):
            for y in range(96):
                image.putpixel((x, y), (255, 255, 255))
        image.save(path)

        # upscale=True on purpose: a 96x96 source is already legal, and a legal source
        # is never resampled, which would make every filter look identical.
        sharp = self._run(["stripes.png"], megapixels=0.05, resampling="Nearest", upscale=True)[0]
        soft = self._run(["stripes.png"], megapixels=0.05, resampling="Bicubic", upscale=True)[0]
        self.assertEqual(sharp.shape, soft.shape, "the filter must not change the frame size")
        self.assertFalse(torch.equal(sharp, soft))

    def test_a_grid_aligned_small_image_is_returned_untouched(self):
        # Upscaling off must not resample an image that is already legal: the tensor
        # has to keep the source size exactly.
        make_image("keep.png", (320, 256), (10, 200, 30))
        tensor = self._run(["keep.png"], megapixels=1.0, upscale=False)[0]
        self.assertEqual(self._frame(tensor), (320, 256))

    def test_turning_upscaling_on_does_change_the_frame(self):
        make_image("grow.png", (320, 256), (10, 200, 30))
        kept = self._run(["grow.png"], megapixels=1.0, upscale=False)[0]
        grown = self._run(["grow.png"], megapixels=1.0, upscale=True)[0]
        self.assertGreater(grown.shape[1] * grown.shape[2], kept.shape[1] * kept.shape[2])
        self.assertEqual(grown.shape[1] % 32, 0)
        self.assertEqual(grown.shape[2] % 32, 0)

    def test_the_cache_key_follows_every_resize_setting(self):
        base = REF.H3ImageReferenceLoader.fingerprint_inputs(
            media_files="[]", target_megapixels=0.25,
            resampling_method=RESAMPLE_LANCZOS, upscale_small_images=False)
        for change in (
            {"target_megapixels": 1.0},
            {"resampling_method": "Nearest"},
            {"upscale_small_images": True},
        ):
            args = {"media_files": "[]", "target_megapixels": 0.25,
                    "resampling_method": RESAMPLE_LANCZOS, "upscale_small_images": False}
            args.update(change)
            self.assertNotEqual(base, REF.H3ImageReferenceLoader.fingerprint_inputs(**args),
                                change)

    def test_an_unknown_filter_is_a_readable_error(self):
        message = REF.H3ImageReferenceLoader.validate_inputs(
            media_files="[]", target_megapixels=0.25, resampling_method="Box",
            upscale_small_images=False)
        self.assertIsInstance(message, str)
        self.assertIn("resampling_method", message)
        self.assertIs(True, REF.H3ImageReferenceLoader.validate_inputs(
            media_files="[]", target_megapixels=0.25, resampling_method="nearest",
            upscale_small_images=True))


@unittest.skipIf(REF is None, f"comfy_api unavailable: {LOAD_ERROR}")
class TestAudioNodeExecution(unittest.TestCase):
    def setUp(self):
        self._real_roots = REF._media_roots
        REF._media_roots = lambda: {"input": TMP_ROOT}

    def tearDown(self):
        REF._media_roots = self._real_roots

    def _run(self, names):
        return REF.H3AudioReferenceLoader.execute(media_files=json_names(names)).result

    def test_no_audio_means_three_none_slots(self):
        self.assertEqual(self._run([]), (None, None, None))

    def test_two_audios_keep_their_order_and_are_not_resampled(self):
        if REF._decode_audio_file is None:
            self.skipTest("ComfyUI's audio decoder is not importable here")
        make_wav("a_short.wav", seconds=0.2)
        make_wav("b_long.wav", seconds=0.5)
        first, second, third = self._run(["a_short.wav", "b_long.wav"])
        self.assertIsNone(third)
        self.assertEqual(first["waveform"].shape[0], 1)
        self.assertEqual(first["sample_rate"], 8000)
        self.assertEqual(second["sample_rate"], 8000)
        self.assertGreater(second["waveform"].shape[-1], first["waveform"].shape[-1])

    def test_a_card_window_is_cut_before_it_reaches_h3(self):
        if REF._decode_audio_file is None:
            self.skipTest("ComfyUI's audio decoder is not importable here")
        import torch

        make_wav("clip.wav", seconds=1.0)
        rate = 8000
        raw = json.dumps([
            {"filename": "clip.wav", "subfolder": "", "type": "input", "start": 0.25, "duration": 0.2},
            {"filename": "clip.wav", "subfolder": "", "type": "input", "start": -0.1},
            {"filename": "clip.wav", "subfolder": "", "type": "input"},
        ])
        first, second, third = REF.H3AudioReferenceLoader.execute(media_files=raw).result
        full = third["waveform"][0, 0]
        self.assertEqual(third["waveform"].shape[-1], int(1.0 * rate), "no window means the whole file")
        window = int(0.2 * rate)
        offset = int(0.25 * rate)
        self.assertEqual(first["waveform"].shape[-1], window, "the card asked for 0.2 s")
        self.assertTrue(torch.equal(first["waveform"][0, 0], full[offset:offset + window]),
                        "the window starts where the card said")
        tail = int(0.1 * rate)
        self.assertTrue(torch.equal(second["waveform"][0, 0], full[-tail:]),
                        "a negative start counts back from the end")
        self.assertEqual(first["sample_rate"], rate, "trimming never resamples")

    def test_a_window_past_the_end_is_a_readable_error(self):
        if REF._decode_audio_file is None:
            self.skipTest("ComfyUI's audio decoder is not importable here")
        make_wav("too_short.wav", seconds=0.2)
        raw = json.dumps([{"filename": "too_short.wav", "subfolder": "", "type": "input", "start": 5}])
        with self.assertRaises(ValueError) as ctx:
            REF.H3AudioReferenceLoader.execute(media_files=raw)
        self.assertIn("裁切后没有音频样本", str(ctx.exception))

    def test_missing_audio_names_the_file(self):
        with self.assertRaises(ValueError) as ctx:
            self._run(["gone.wav"])
        self.assertIn("gone.wav", str(ctx.exception))

    def test_more_than_three_audios_are_truncated(self):
        for index in range(4):
            make_wav(f"m{index}.wav", seconds=0.1)
        result = self._run([f"m{index}.wav" for index in range(4)])
        self.assertEqual(len(result), 3)
        self.assertEqual(sum(1 for value in result if value is None), 0)

    def test_bad_json_is_reported(self):
        self.assertIsInstance(REF.H3AudioReferenceLoader.validate_inputs(media_files="{oops"), str)
        self.assertIs(True, REF.H3AudioReferenceLoader.validate_inputs(media_files="[]"))


class TestTrimAudio(unittest.TestCase):
    """The window math is ComfyUI's own TrimAudioDuration, so it is checked on samples."""

    @staticmethod
    def _audio(seconds, rate=100):
        import torch

        return {
            "waveform": torch.arange(int(seconds * rate), dtype=torch.float32).reshape(1, 1, -1),
            "sample_rate": rate,
        }

    def test_no_window_returns_the_same_dict(self):
        audio = self._audio(1)
        self.assertIs(trim_audio(audio), audio)

    def test_a_window_keeps_exactly_the_right_samples(self):
        cut = trim_audio(self._audio(1), 0.2, 0.3)
        self.assertEqual(cut["waveform"].shape[-1], 30)
        self.assertEqual(int(cut["waveform"][0, 0, 0]), 20)
        self.assertEqual(cut["sample_rate"], 100, "trimming never resamples")

    def test_a_negative_start_counts_back_from_the_end(self):
        cut = trim_audio(self._audio(1), -0.2)
        self.assertEqual(cut["waveform"].shape[-1], 20)
        self.assertEqual(int(cut["waveform"][0, 0, 0]), 80)

    def test_both_ends_are_clamped_into_the_file(self):
        self.assertEqual(trim_audio(self._audio(1), 0.9, 5)["waveform"].shape[-1], 10)
        self.assertEqual(trim_audio(self._audio(1), -5)["waveform"].shape[-1], 100)

    def test_a_window_with_no_samples_says_so_in_chinese(self):
        with self.assertRaises(ValueError) as ctx:
            trim_audio(self._audio(1), 1.5)
        self.assertIn("裁切后没有音频样本", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
