"""Node-level tests for H3 Guide Timeline (needs ComfyUI's comfy_api).

The contract being tested is the one the plan sets: this node must be equivalent to
wiring the native MiniMaxH3AddGuide nodes by hand. So the assertions are about the
conditioning that comes out - how many keyframes, at which frames, in which order,
carrying which media - and about the errors, which have to be readable instead of a
torch traceback.

The two VAEs are stubs. The native node only ever calls vae.encode() and
audio_vae.encode(), and what the real H3 VAEs return is opaque to this node; what
matters here is which encoder was called, with how many frames, and with what
pixels. The AV latent and every media file are real.
"""

import importlib.util
import importlib
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
import wave

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


def _load_guide_nodes():
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
            return importlib.import_module("h3lvm.comfyui.guide_nodes"), None
        except Exception as exc:
            last_error = exc
    return None, last_error


GUIDE, LOAD_ERROR = _load_guide_nodes()

TMP_ROOT = None
INPUTS = None


def setUpModule():
    global TMP_ROOT, INPUTS
    TMP_ROOT = tempfile.mkdtemp(prefix="h3lvm_guide_nodes_")
    INPUTS = os.path.join(TMP_ROOT, "input")
    os.makedirs(INPUTS, exist_ok=True)


def tearDownModule():
    if TMP_ROOT:
        shutil.rmtree(TMP_ROOT, ignore_errors=True)


def make_gray(name, size, level):
    """A solid gray PNG; its mean pixel is the marker used to identify it later."""
    from PIL import Image

    path = os.path.join(INPUTS, name)
    value = int(round(level * 255))
    Image.new("RGB", size, (value, value, value)).save(path)
    return name


def make_wav(name, seconds=2.0, sample_rate=48000):
    """A rising ramp, so a trimmed window has a different mean than the whole file."""
    path = os.path.join(INPUTS, name)
    total = int(round(seconds * sample_rate))
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"".join(
            struct.pack("<h", int((index / max(1, total - 1)) * 20000)) for index in range(total)))
    return name


class FakeVideoVae:
    """Stands in for the H3 video VAE: records what it was asked to encode."""

    def __init__(self):
        self.calls = []

    def encode(self, frames):
        self.calls.append(tuple(frames.shape))
        value = float(frames.reshape(-1).float().mean())
        tokens = max(1, int(frames.shape[0]) // 4)
        return torch.full((1, 24, tokens, 2, 2), value)


class FakeAudioVae:
    """Stands in for the H3 audio VAE: 40 latent frames per second, like the real one."""

    audio_sample_rate = 32000
    latent_fps = 40

    def __init__(self):
        self.calls = []

    def encode(self, waveform):  # [B, L, C] after the native's movedim
        self.calls.append(int(waveform.shape[1]))
        seconds = waveform.shape[1] / float(self.audio_sample_rate)
        value = float(waveform.reshape(-1).float().mean())
        frames = max(1, int(round(seconds * self.latent_fps)))
        return torch.full((1, 32, 2, frames), value)


def av_latent(width=128, height=128, length=124):
    from comfy_extras.nodes_minimax_h3 import EmptyMiniMaxH3LatentAV

    return EmptyMiniMaxH3LatentAV.execute(width, height, length).result[0]


def conditioning():
    return [[torch.zeros([1, 4]), {"ref": "keep-me"}]]


def image_entry(name, frame, gid=None, enabled=True):
    entry = {
        "kind": "image",
        "id": gid or ("img-" + name),
        "enabled": enabled,
        "frame_index": frame,
        "asset": {"filename": name, "subfolder": "", "type": "input"},
    }
    return entry


def audio_entry(name, frame, start_sample=0, end_sample=0, gid=None, enabled=True):
    return {
        "kind": "audio",
        "id": gid or ("aud-" + name),
        "enabled": enabled,
        "frame_index": frame,
        "asset": {"filename": name, "subfolder": "", "type": "input"},
        "source_start_sample": start_sample,
        "source_end_sample": end_sample,
    }


def quantized(level: float) -> float:
    """The value that survives the 8-bit round trip (0.5 -> 128 -> 0.50196)."""
    return round(level * 255) / 255


def guides_json(entries, **extra):
    document = {"schema_version": 1, "fps": 24, "guides": entries}
    document.update(extra)
    return json.dumps(document, ensure_ascii=False)


@unittest.skipIf(LOAD_ERROR is not None, "comfy_api unavailable: %s" % LOAD_ERROR)
class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = GUIDE.H3GuideTimeline.define_schema()

    def test_the_node_is_registered_with_the_plugin(self):
        from h3lvm.comfyui.nodes import NODE_LIST

        self.assertIn(GUIDE.H3GuideTimeline, NODE_LIST)

    def test_identity_and_category(self):
        self.assertEqual(self.schema.node_id, "H3 Guide Timeline")
        self.assertEqual(self.schema.display_name, "H3 Guide 时间轴")
        self.assertEqual(self.schema.category, "H3/Guide")

    def test_the_native_inputs_plus_the_ruler_hint_and_one_output(self):
        # V3 Input/Output objects carry the name in .id and the flag in .optional.
        # length_seconds is the optional ruler hint: it exists so the editor can draw a timeline
        # and check placements before anything has been run. It is in seconds, like the workflow
        # nodes a user already knows (segment_duration), not in frames.
        names = [item.id for item in self.schema.inputs]
        self.assertEqual(names, ["positive", "latent", "length_seconds", "vae", "audio_vae", "guides"])
        self.assertEqual([item.optional for item in self.schema.inputs],
                         [False, False, True, True, True, False])
        self.assertEqual(len(self.schema.outputs), 1)
        # Same convention as the loader nodes: the slot label is display_name.
        self.assertEqual(self.schema.outputs[0].display_name, "positive")

    def test_the_default_document_is_empty_but_valid(self):
        self.assertEqual(GUIDE.parse_guides(GUIDE.DEFAULT_GUIDES), [])
        self.assertEqual(json.loads(GUIDE.DEFAULT_GUIDES)["fps"], 24)

    def test_validate_inputs_reports_a_bad_list(self):
        self.assertIn("not valid JSON", GUIDE.H3GuideTimeline.validate_inputs("{"))
        self.assertTrue(GUIDE.H3GuideTimeline.validate_inputs(GUIDE.DEFAULT_GUIDES))

    def test_fingerprint_ignores_view_state(self):
        entries = [image_entry("a.png", 0)]
        first = GUIDE.H3GuideTimeline.fingerprint_inputs(guides_json(entries))
        second = GUIDE.H3GuideTimeline.fingerprint_inputs(
            guides_json(entries, view_state={"zoom": 3, "selected_id": "img-a.png"}))
        self.assertEqual(first, second)
        moved = GUIDE.H3GuideTimeline.fingerprint_inputs(guides_json([image_entry("a.png", 48)]))
        self.assertNotEqual(first, moved)


@unittest.skipIf(LOAD_ERROR is not None, "comfy_api unavailable: %s" % LOAD_ERROR)
class PassThroughTests(unittest.TestCase):
    def setUp(self):
        self._roots = GUIDE._media_roots
        GUIDE._media_roots = lambda: {"input": INPUTS}
        self.vae, self.audio_vae = FakeVideoVae(), FakeAudioVae()

    def tearDown(self):
        GUIDE._media_roots = self._roots

    def run_node(self, guides, latent=None, positive=None):
        return GUIDE.H3GuideTimeline.execute(
            positive if positive is not None else conditioning(),
            latent if latent is not None else av_latent(), guides,
            vae=self.vae, audio_vae=self.audio_vae)

    def test_no_guides_returns_the_same_conditioning_object(self):
        positive = conditioning()
        for guides in (GUIDE.DEFAULT_GUIDES, "", "[]"):
            out = GUIDE.H3GuideTimeline.execute(positive, {"samples": None}, guides)
            self.assertIs(out.result[0], positive)
            self.assertEqual(out.ui["h3_guide_timeline"][0]["frame_count"], 0)
        self.assertEqual(self.vae.calls, [])
        self.assertEqual(self.audio_vae.calls, [])

    def test_parked_and_unplaced_are_not_encoded(self):
        make_gray("a.png", (64, 64), 0.5)
        guides = guides_json([
            image_entry("a.png", 0, gid="p1", enabled=False),
            image_entry("a.png", None, gid="p2"),
        ])
        positive = conditioning()
        out = self.run_node(guides, positive=positive)
        self.assertIs(out.result[0], positive)
        self.assertEqual(self.vae.calls, [])
        summary = out.ui["h3_guide_timeline"][0]["summary"]
        self.assertEqual((summary["images"], summary["parked"]), (0, 2))

    def test_the_length_hint_does_not_change_execution(self):
        # length_seconds is for the editor's ruler only. The frame count the node reports still
        # comes from the latent, so a wrong number in that box cannot move a guide or a keyframe.
        make_gray("a.png", (64, 64), 0.5)
        guides = guides_json([image_entry("a.png", 0, gid="g1")])
        out = GUIDE.H3GuideTimeline.execute(
            conditioning(), av_latent(), guides, length_seconds=99.0,
            vae=self.vae, audio_vae=self.audio_vae)
        self.assertEqual(out.ui["h3_guide_timeline"][0]["frame_count"], 124)
        self.assertEqual(len(self.vae.calls), 1)


@unittest.skipIf(LOAD_ERROR is not None, "comfy_api unavailable: %s" % LOAD_ERROR)
class EquivalenceTests(unittest.TestCase):
    def setUp(self):
        self._roots = GUIDE._media_roots
        GUIDE._media_roots = lambda: {"input": INPUTS}
        self.vae, self.audio_vae = FakeVideoVae(), FakeAudioVae()
        make_gray("pose1.png", (64, 64), 0.25)
        make_gray("pose2.png", (64, 64), 0.5)
        make_gray("pose3.png", (64, 64), 0.75)
        make_wav("line.wav", seconds=2.0, sample_rate=48000)

    def tearDown(self):
        GUIDE._media_roots = self._roots

    def run_node(self, entries, latent=None, vae="auto", audio_vae="auto", positive=None):
        out = GUIDE.H3GuideTimeline.execute(
            positive if positive is not None else conditioning(),
            latent if latent is not None else av_latent(), guides_json(entries),
            vae=None if vae is None else self.vae,
            audio_vae=None if audio_vae is None else self.audio_vae)
        return out

    def keyframes(self, positive):
        return positive[0][1]["minimax_keyframes"]

    def test_one_image_anchors_one_keyframe(self):
        out = self.run_node([image_entry("pose2.png", 48)])
        frames = self.keyframes(out.result[0])
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["resolved_frame_index"], 48)
        self.assertIn("latent", frames[0])
        self.assertNotIn("audio_latent", frames[0])
        self.assertAlmostEqual(float(frames[0]["latent"].flatten()[0]), quantized(0.5), places=4)
        self.assertEqual(self.audio_vae.calls, [])

    def test_the_input_conditioning_is_not_mutated(self):
        positive = conditioning()
        out = self.run_node([image_entry("pose1.png", 0)])
        self.assertNotIn("minimax_keyframes", positive[0][1])
        self.assertEqual(positive[0][1], {"ref": "keep-me"})
        self.assertEqual(len(self.keyframes(out.result[0])), 1)

    def test_upstream_keyframes_are_kept_and_appended(self):
        positive = conditioning()
        positive[0][1]["minimax_keyframes"] = [{"resolved_frame_index": 3, "latent": torch.zeros(1)}]
        out = self.run_node([image_entry("pose1.png", 48)], positive=positive)
        frames = self.keyframes(out.result[0])
        self.assertEqual([frame["resolved_frame_index"] for frame in frames], [3, 48])

    def test_three_images_and_one_audio(self):
        out = self.run_node([
            audio_entry("line.wav", 12, end_sample=48000),
            image_entry("pose3.png", 96),
            image_entry("pose1.png", 0),
            image_entry("pose2.png", 48),
        ])
        frames = self.keyframes(out.result[0])
        self.assertEqual([frame["resolved_frame_index"] for frame in frames], [0, 12, 48, 96])
        self.assertEqual([("latent" in frame, "audio_latent" in frame) for frame in frames],
                         [(True, False), (False, True), (True, False), (True, False)])
        self.assertAlmostEqual(float(frames[0]["latent"].flatten()[0]), quantized(0.25), places=4)
        self.assertAlmostEqual(float(frames[2]["latent"].flatten()[0]), quantized(0.5), places=4)

    def test_image_and_audio_on_the_same_frame_are_both_anchored(self):
        out = self.run_node([
            audio_entry("line.wav", 48, end_sample=16000),
            image_entry("pose2.png", 48),
        ])
        frames = self.keyframes(out.result[0])
        self.assertEqual([frame["resolved_frame_index"] for frame in frames], [48, 48])
        self.assertTrue("latent" in frames[0] and "audio_latent" in frames[1])

    def test_import_order_does_not_change_the_result(self):
        first = self.run_node([image_entry("pose1.png", 0), image_entry("pose2.png", 48),
                              image_entry("pose3.png", 96)])
        second = self.run_node([image_entry("pose3.png", 96), image_entry("pose1.png", 0),
                               image_entry("pose2.png", 48)])
        a = self.keyframes(first.result[0])
        b = self.keyframes(second.result[0])
        self.assertEqual([frame["resolved_frame_index"] for frame in a],
                         [frame["resolved_frame_index"] for frame in b])
        for left, right in zip(a, b):
            self.assertTrue(torch.equal(left["latent"], right["latent"]))

    def test_only_the_needed_vae_is_called(self):
        self.run_node([image_entry("pose1.png", 0)])
        self.assertEqual(self.audio_vae.calls, [])
        self.vae.calls.clear()
        self.run_node([audio_entry("line.wav", 0, end_sample=16000)])
        self.assertEqual(self.vae.calls, [])
        self.assertEqual(len(self.audio_vae.calls), 1)

    def test_the_audio_window_is_cut_before_encoding(self):
        whole = self.run_node([audio_entry("line.wav", 0)])
        trimmed = self.run_node([audio_entry("line.wav", 0, start_sample=48000, end_sample=96000)])
        self.assertEqual(len(self.audio_vae.calls), 2)
        first, second = self.audio_vae.calls
        self.assertAlmostEqual(second, first / 2.0, delta=4)
        a = float(self.keyframes(whole.result[0])[0]["audio_latent"].flatten()[0])
        b = float(self.keyframes(trimmed.result[0])[0]["audio_latent"].flatten()[0])
        self.assertGreater(b, a + 0.05)

    def test_the_real_frame_count_is_reported_to_the_panel(self):
        out = self.run_node([image_entry("pose1.png", 0)])
        payload = out.ui["h3_guide_timeline"][0]
        self.assertEqual(payload["frame_count"], 124)
        self.assertEqual(payload["fps"], 24)
        self.assertEqual(payload["summary"]["images"], 1)
        self.assertEqual(len(payload["digest"]), 64)

    def test_a_non_h3_latent_is_named(self):
        for latent in ({"samples": None}, {"samples": torch.zeros(1, 24, 4, 2, 2)}, {}):
            with self.assertRaises(ValueError) as ctx:
                self.run_node([image_entry("pose1.png", 0)], latent=latent)
            self.assertIn("latent", str(ctx.exception))


@unittest.skipIf(LOAD_ERROR is not None, "comfy_api unavailable: %s" % LOAD_ERROR)
class ErrorTests(unittest.TestCase):
    def setUp(self):
        self._roots = GUIDE._media_roots
        GUIDE._media_roots = lambda: {"input": INPUTS}
        self.vae, self.audio_vae = FakeVideoVae(), FakeAudioVae()
        make_gray("a.png", (64, 64), 0.5)
        make_gray("b.png", (64, 64), 0.6)
        make_wav("line.wav", seconds=2.0, sample_rate=48000)

    def tearDown(self):
        GUIDE._media_roots = self._roots

    def expect(self, entries, fragment, vae="auto", audio_vae="auto"):
        with self.assertRaises(ValueError) as ctx:
            GUIDE.H3GuideTimeline.execute(
                conditioning(), av_latent(), guides_json(entries),
                vae=None if vae is None else self.vae,
                audio_vae=None if audio_vae is None else self.audio_vae)
        message = str(ctx.exception)
        self.assertIn("Guide 校验未通过", message)
        self.assertIn(fragment, message)
        return message

    def test_missing_video_vae(self):
        self.expect([image_entry("a.png", 0)], "需要连接视频 VAE", vae=None)
        self.assertEqual(self.vae.calls, [])

    def test_missing_audio_vae(self):
        self.expect([audio_entry("line.wav", 0)], "需要连接音频 VAE", audio_vae=None)

    def test_frame_out_of_range(self):
        self.expect([image_entry("a.png", 124)], "超出视频范围")

    def test_two_images_on_one_frame(self):
        self.expect([image_entry("a.png", 48), image_entry("b.png", 48)], "同一帧只能锚一张图片")

    def test_overlapping_audio(self):
        self.expect([audio_entry("line.wav", 0, end_sample=48000),
                     audio_entry("line.wav", 12, end_sample=48000)], "重叠")

    def test_audio_tail_past_the_end(self):
        self.expect([audio_entry("line.wav", 100)], "超出视频结尾")

    def test_empty_audio_window(self):
        self.expect([audio_entry("line.wav", 0, start_sample=1000, end_sample=500)], "裁切区间是空的")

    def test_missing_asset(self):
        self.expect([image_entry("gone.png", 0)], "素材不可用")

    def test_every_problem_is_reported_at_once(self):
        message = self.expect([image_entry("a.png", 124), image_entry("gone.png", 10)],
                              "超出视频范围")
        self.assertIn("素材不可用", message)
        self.assertEqual(self.vae.calls, [])

    def test_quota_is_refused_before_anything_runs(self):
        entries = [image_entry("a.png", index) for index in range(17)]
        with self.assertRaises(ValueError) as ctx:
            GUIDE.H3GuideTimeline.execute(conditioning(), av_latent(), guides_json(entries),
                                          vae=self.vae, audio_vae=self.audio_vae)
        self.assertIn("最多 16 个", str(ctx.exception))

    def test_a_native_without_add_guide_only_breaks_this_node(self):
        saved = (GUIDE._NATIVE, GUIDE._NATIVE_ERROR)
        GUIDE._NATIVE, GUIDE._NATIVE_ERROR = None, "simulated: this ComfyUI has no MiniMaxH3AddGuide"
        try:
            with self.assertRaises(RuntimeError) as ctx:
                GUIDE.H3GuideTimeline.execute(conditioning(), av_latent(),
                                              guides_json([image_entry("a.png", 0)]),
                                              vae=self.vae, audio_vae=self.audio_vae)
            self.assertIn("simulated", str(ctx.exception))
        finally:
            GUIDE._NATIVE, GUIDE._NATIVE_ERROR = saved
        self.assertEqual(self.vae.calls, [])


class ResourceTests(unittest.TestCase):
    """Pass 1 reads headers, pass 2 decodes one guide at a time and drops it."""

    def setUp(self):
        self._roots = GUIDE._media_roots
        GUIDE._media_roots = lambda: {"input": INPUTS}
        self.vae, self.audio_vae = FakeVideoVae(), FakeAudioVae()
        make_gray("a.png", (64, 64), 0.5)
        make_gray("b.png", (64, 64), 0.6)
        make_wav("line.wav", seconds=2.0, sample_rate=48000)
        self.events = []
        self._image = GUIDE._decode_image_frames
        self._audio = GUIDE._decode_audio_window
        GUIDE._decode_image_frames = lambda path: (
            self.events.append("decode:" + os.path.basename(path)), self._image(path))[1]
        GUIDE._decode_audio_window = lambda path, guide: (
            self.events.append("decode:" + os.path.basename(path)), self._audio(path, guide))[1]
        for tag, vae in (("vae", self.vae), ("audio_vae", self.audio_vae)):
            original = vae.encode
            vae.encode = lambda *a, _t=tag, _f=original, **k: (self.events.append(_t), _f(*a, **k))[1]

    def tearDown(self):
        GUIDE._media_roots = self._roots
        GUIDE._decode_image_frames = self._image
        GUIDE._decode_audio_window = self._audio

    def run_node(self, entries):
        return GUIDE.H3GuideTimeline.execute(
            conditioning(), av_latent(), guides_json(entries),
            vae=self.vae, audio_vae=self.audio_vae).result[0]

    def test_headers_refuse_a_bad_list_before_any_decode(self):
        # A guide that cannot work must not cost a decode of every other file first.
        with self.assertRaises(ValueError) as ctx:
            self.run_node([image_entry("a.png", 0), image_entry("b.png", 124)])
        self.assertIn("超出视频范围", str(ctx.exception))
        self.assertEqual([e for e in self.events if e.startswith("decode:")], [])
        self.assertEqual(self.vae.calls, [])

    def test_an_empty_audio_window_is_a_header_error(self):
        with self.assertRaises(ValueError) as ctx:
            self.run_node([audio_entry("line.wav", 0, start_sample=1000, end_sample=500)])
        self.assertIn("裁切区间是空的", str(ctx.exception))
        self.assertEqual([e for e in self.events if e.startswith("decode:")], [])
        self.assertEqual(self.audio_vae.calls, [])

    def test_media_is_decoded_one_at_a_time(self):
        self.run_node([image_entry("a.png", 0), image_entry("b.png", 24)])
        decodes = [index for index, event in enumerate(self.events) if event.startswith("decode:")]
        self.assertEqual([self.events[i] for i in decodes], ["decode:a.png", "decode:b.png"])
        # The second file is only opened after the first one has been encoded, which is
        # what keeps thirty guides from holding thirty tensors at once.
        self.assertIn("vae", self.events[decodes[0] + 1:decodes[1]])

    def test_a_headerless_audio_is_decoded_once(self):
        # mp3 has no cheap header here, so pass 1 decodes it and pass 2 reuses it.
        saved = GUIDE._audio_meta
        GUIDE._audio_meta = lambda path: None
        try:
            self.run_node([audio_entry("line.wav", 0, end_sample=48000)])
        finally:
            GUIDE._audio_meta = saved
        self.assertEqual([e for e in self.events if e.startswith("decode:")], ["decode:line.wav"])
        self.assertEqual(len(self.audio_vae.calls), 1)


if __name__ == "__main__":
    unittest.main()