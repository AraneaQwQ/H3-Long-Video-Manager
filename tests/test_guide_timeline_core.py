"""Pure-logic tests for the Guide Timeline list (no ComfyUI, no torch).

Everything here is the part that decides whether a set of guides is legal and in
what order it runs. The node wraps this in decoding and VAE calls; if a rule is
wrong, it has to fail here first, where it costs milliseconds.
"""

import json
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from core.guide_timeline import (  # noqa: E402
    AUDIO_KIND, DEFAULT_FPS, IMAGE_KIND, MAX_GUIDE_IMAGES, MAX_GUIDE_TOTAL,
    SCHEMA_VERSION, align_frame_count, audio_span_frames, count_runnable,
    execution_digest,
    find_audio_overlaps, frame_count_from_latent_t, frame_to_seconds,
    frames_from_seconds, guide_fingerprint, guide_frames_for, label_for, media_kind,
    merge_guides, parse_guides, parked_guides, ensure_labels, runnable_guides,
    seconds_to_frame, serialize_guides, sort_for_execution, summary, validate_guides,
)


def image_guide(label_index=0, frame=0, name="pose.png", **extra):
    guide = {
        "id": "img%d" % label_index,
        "kind": IMAGE_KIND,
        "enabled": True,
        "frame_index": frame,
        "asset": {"filename": name, "subfolder": "", "type": "input"},
    }
    guide.update(extra)
    return guide


def audio_guide(gid="aud0", frame=0, start=0, end=105600, rate=48000, name="line.wav", **extra):
    guide = {
        "id": gid,
        "kind": AUDIO_KIND,
        "enabled": True,
        "frame_index": frame,
        "asset": {"filename": name, "subfolder": "", "type": "input"},
        "source_start_sample": start,
        "source_end_sample": end,
        "sample_rate": rate,
    }
    guide.update(extra)
    return guide


class MediaKindTests(unittest.TestCase):
    def test_extension_table(self):
        self.assertEqual(media_kind("a.wav"), "audio")
        self.assertEqual(media_kind("dir/a.MP3"), "audio")
        self.assertEqual(media_kind("a.png"), "image")
        self.assertEqual(media_kind("a.JPEG"), "image")
        self.assertEqual(media_kind("a.txt"), "other")
        self.assertEqual(media_kind(None), "other")

    def test_labels_are_per_kind(self):
        self.assertEqual(label_for(IMAGE_KIND, 0), "IMG-01")
        self.assertEqual(label_for(AUDIO_KIND, 2), "AUD-03")


class LatentFrameTests(unittest.TestCase):
    def test_matches_the_native_sum(self):
        # comfy/ldm/minimax/model.py: one token is 1, 4, 4, 4, 4 pixel frames in a
        # repeating cycle, so 37 tokens is the 124 frames the reference node defaults to.
        self.assertEqual(frame_count_from_latent_t(2), 5)
        self.assertEqual(frame_count_from_latent_t(37), 124)
        self.assertEqual(frame_count_from_latent_t(0), 0)
        self.assertEqual(frame_count_from_latent_t(None), 0)

    def test_guide_frames_follow_the_native_crop(self):
        self.assertEqual(guide_frames_for(1), 1)
        self.assertEqual(guide_frames_for(4), 1)
        self.assertEqual(guide_frames_for(5), 5)
        self.assertEqual(guide_frames_for(21), 5)
        self.assertEqual(guide_frames_for(22), 22)
        self.assertEqual(guide_frames_for(40), 39)


class TimeTests(unittest.TestCase):
    def test_seconds_are_display_only(self):
        self.assertEqual(seconds_to_frame(2.0), 48)
        self.assertEqual(frame_to_seconds(48), 2.0)
        self.assertEqual(seconds_to_frame("1.5"), 36)
        self.assertEqual(frame_to_seconds(None), 0.0)

    def test_seconds_become_the_length_the_run_produces(self):
        # The duration box is in seconds because that is how a person plans a shot. The ruler
        # needs the frame count an H3 run would produce, which is the native node's own
        # arithmetic: max(5, round(seconds * 24)) rounded up to 17n+5.
        self.assertEqual(frames_from_seconds(3.0), 73)      # 72 -> 73
        self.assertEqual(frames_from_seconds(10.0), 243)    # 240 -> 243
        self.assertEqual(frames_from_seconds(0.5), 22)      # 12 -> 22
        self.assertEqual(frames_from_seconds("10"), 243)    # a hand-typed widget value
        self.assertEqual(frames_from_seconds(1.0, fps=30), 39)
        for seconds in (0, 0.0, None, -3, "", "abc"):
            self.assertEqual(frames_from_seconds(seconds), 0, repr(seconds))

    def test_alignment_matches_the_native_rule(self):
        # comfy_extras/nodes_minimax_h3.py: align_frame_count() adds 1 until n % 17 == 5.
        for frames in (5, 22, 39, 107, 124, 141, 243):
            self.assertEqual(align_frame_count(frames), frames)
        self.assertEqual(align_frame_count(240), 243)
        self.assertEqual(align_frame_count(120), 124)
        self.assertEqual(align_frame_count(0), 5)
        self.assertEqual(align_frame_count(1), 5)

    def test_audio_span_uses_the_source_rate(self):
        # 2.2 s of audio is 2.2 s of video regardless of the sample rate, because
        # the audio VAE resamples internally.
        self.assertAlmostEqual(audio_span_frames(105600, 48000), 52.8, places=6)
        self.assertAlmostEqual(audio_span_frames(70400, 32000), 52.8, places=6)
        self.assertEqual(audio_span_frames(0, 48000), 0.0)
        self.assertEqual(audio_span_frames(100, 0), 0.0)


class ParseTests(unittest.TestCase):
    def test_empty_forms(self):
        for value in (None, "", "   ", "[]", {"guides": []}, '{"guides":[]}', [], ()):
            self.assertEqual(parse_guides(value), [])

    def test_bad_json_is_a_readable_error(self):
        with self.assertRaises(ValueError) as ctx:
            parse_guides('{"guides": [')
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_bad_shapes_are_rejected(self):
        for value in (5, "5", {"guides": {"a": 1}}):
            with self.assertRaises(ValueError):
                parse_guides(value)

    def test_normalises_a_minimal_entry(self):
        guides = parse_guides([{"kind": "image", "filename": "a.png"}])
        self.assertEqual(len(guides), 1)
        self.assertEqual(guides[0]["asset"], {"filename": "a.png", "subfolder": "", "type": "input"})
        self.assertEqual(guides[0]["label"], "IMG-01")
        self.assertTrue(guides[0]["enabled"])
        self.assertIsNone(guides[0]["frame_index"])
        self.assertRegex(guides[0]["id"], r"^[0-9a-f]{16}$")

    def test_asset_forms_and_safety(self):
        with self.assertRaises(ValueError):
            parse_guides([{"kind": "image", "asset": {"filename": "C:/x/a.png"}}])
        with self.assertRaises(ValueError):
            parse_guides([{"kind": "image", "asset": {"filename": "../a.png"}}])
        with self.assertRaises(ValueError):
            parse_guides([{"kind": "image", "asset": {"filename": ".hidden.png"}}])
        with self.assertRaises(ValueError):
            parse_guides([{"kind": "image", "asset": {"filename": "a.png", "type": "elsewhere"}}])
        with self.assertRaises(ValueError):
            parse_guides([{"kind": "image"}])
        ok = parse_guides([{"kind": "image", "asset": {"filename": "sub\\a.png", "subfolder": "s", "type": "output"}}])
        self.assertEqual(ok[0]["asset"]["filename"], "sub/a.png")
        self.assertEqual(ok[0]["asset"]["type"], "output")

    def test_frame_index_rules(self):
        self.assertIsNone(parse_guides([{"kind": "image", "filename": "a.png", "frame_index": None}])[0]["frame_index"])
        self.assertEqual(parse_guides([{"kind": "image", "filename": "a.png", "frame_idx": 12}])[0]["frame_index"], 12)
        with self.assertRaises(ValueError):
            parse_guides([{"kind": "image", "filename": "a.png", "frame_index": -1}])
        with self.assertRaises(ValueError):
            parse_guides([{"kind": "image", "filename": "a.png", "frame_index": "48f"}])
        with self.assertRaises(ValueError):
            parse_guides([{"kind": "video", "filename": "a.png"}])

    def test_ids_are_unique_even_when_supplied(self):
        guides = parse_guides([
            {"kind": "image", "filename": "a.png", "id": "same"},
            {"kind": "image", "filename": "b.png", "id": "same"},
            {"kind": "image", "filename": "c.png", "id": "not a valid id!"},
        ])
        self.assertEqual(len({guide["id"] for guide in guides}), 3)
        self.assertEqual(guides[0]["id"], "same")

    def test_labels_are_filled_in_list_order(self):
        guides = parse_guides([
            image_guide(0), audio_guide("a0"), image_guide(1), audio_guide("a1"),
        ])
        self.assertEqual([guide["label"] for guide in guides],
                         ["IMG-01", "AUD-01", "IMG-02", "AUD-02"])
        self.assertEqual([guide["id"] for guide in guides], ["img0", "a0", "img1", "a1"])

    def test_labels_are_stable_when_the_list_changes(self):
        # The label is what the panel and every error message names, so a card keeps
        # its number when another card is deleted or the order changes. The id is the
        # identity; the label only has to stop moving.
        guides = parse_guides([
            image_guide(0, frame=0, label="IMG-07"),
            image_guide(1, frame=24, label="IMG-02"),
            image_guide(2, frame=48),
        ])
        self.assertEqual([g["label"] for g in guides], ["IMG-07", "IMG-02", "IMG-01"])
        kept = [g for g in guides if g["label"] != "IMG-01"]
        self.assertEqual([g["label"] for g in ensure_labels(kept)], ["IMG-07", "IMG-02"])
        # A malformed label is not kept: it would collide with nothing and read wrong.
        odd = parse_guides([image_guide(0, frame=0, label="img-7")])
        self.assertEqual(odd[0]["label"], "IMG-01")


    def test_quota_counts_only_what_runs(self):
        parked = [image_guide(i, frame=0, enabled=False) for i in range(MAX_GUIDE_IMAGES + 5)]
        parked += [image_guide(100 + i, frame=None) for i in range(MAX_GUIDE_TOTAL)]  # 待放置
        self.assertEqual(len(parse_guides(parked)), len(parked))
        self.assertEqual(count_runnable(parse_guides(parked)), {IMAGE_KIND: 0, AUDIO_KIND: 0})
        unplaced = [image_guide(i) for i in range(MAX_GUIDE_IMAGES + 1)]
        with self.assertRaises(ValueError) as ctx:
            parse_guides(unplaced)
        self.assertIn("最多 %d 个" % MAX_GUIDE_IMAGES, str(ctx.exception))
        placed = [image_guide(i, frame=i) for i in range(MAX_GUIDE_TOTAL + 1)]
        with self.assertRaises(ValueError) as ctx:
            parse_guides(placed)
        self.assertIn("合计", str(ctx.exception))


class RunStateTests(unittest.TestCase):
    def test_parked_and_unplaced_never_run(self):
        guides = parse_guides([
            image_guide(0, frame=0),
            image_guide(1, frame=10, enabled=False),
            image_guide(2, frame=None),
        ])
        self.assertEqual([g["label"] for g in runnable_guides(guides)], ["IMG-01"])
        self.assertEqual([g["label"] for g in parked_guides(guides)], ["IMG-02", "IMG-03"])
        self.assertEqual(count_runnable(guides), {IMAGE_KIND: 1, AUDIO_KIND: 0})

    def test_digest_ignores_labels_and_cares_about_time(self):
        a = parse_guides([image_guide(0, frame=48)])
        b = parse_guides([image_guide(0, frame=48, label="IMG-99")])
        self.assertEqual(execution_digest(a), execution_digest(b))
        c = parse_guides([image_guide(0, frame=49)])
        self.assertNotEqual(execution_digest(a), execution_digest(c))
        d = parse_guides([audio_guide(frame=0, start=0, end=100)])
        e = parse_guides([audio_guide(frame=0, start=10, end=100)])
        self.assertNotEqual(execution_digest(d), execution_digest(e))

    def test_serialize_round_trips(self):
        guides = parse_guides([image_guide(0, frame=48), audio_guide(frame=12)])
        text = serialize_guides(guides, extra={"view_state": {"zoom": 2}})
        again = parse_guides(text)
        self.assertEqual(execution_digest(again), execution_digest(guides))
        document = json.loads(text)
        self.assertEqual(document["schema_version"], SCHEMA_VERSION)
        self.assertEqual(document["fps"], DEFAULT_FPS)
        self.assertEqual(document["view_state"], {"zoom": 2})
        self.assertEqual(serialize_guides(again, extra={"view_state": {"zoom": 2}}), text)


class OrderTests(unittest.TestCase):
    def test_execution_order_is_time_first(self):
        guides = parse_guides([
            audio_guide("a1", frame=48),
            image_guide(2, frame=96),
            image_guide(1, frame=48),
            image_guide(0, frame=0),
        ])
        ordered = sort_for_execution(guides)
        self.assertEqual([(g["kind"], g["frame_index"]) for g in ordered],
                         [(IMAGE_KIND, 0), (IMAGE_KIND, 48), (AUDIO_KIND, 48), (IMAGE_KIND, 96)])
        self.assertEqual(len(ordered), 4)

    def test_same_inputs_different_import_order_give_one_order(self):
        first = sort_for_execution(parse_guides([image_guide(0, frame=0), image_guide(1, frame=48)]))
        second = sort_for_execution(parse_guides([image_guide(1, frame=48), image_guide(0, frame=0)]))
        self.assertEqual([g["id"] for g in first], [g["id"] for g in second])

    def test_sorting_does_not_reorder_the_list(self):
        guides = parse_guides([image_guide(1, frame=96), image_guide(0, frame=0)])
        sort_for_execution(guides)
        self.assertEqual([g["id"] for g in guides], ["img1", "img0"])


class OverlapTests(unittest.TestCase):
    def test_back_to_back_is_not_an_overlap(self):
        guides = parse_guides([audio_guide("a", frame=0, end=64000, rate=32000),
                              audio_guide("b", frame=48, end=64000, rate=32000)])
        spans = {g["id"]: audio_span_frames(64000, 32000) for g in guides}
        self.assertEqual(find_audio_overlaps(guides, spans), [])

    def test_real_overlap_is_reported_once_with_the_window(self):
        guides = parse_guides([audio_guide("a", frame=0, end=64000, rate=32000),
                              audio_guide("b", frame=24, end=64000, rate=32000)])
        spans = {g["id"]: audio_span_frames(64000, 32000) for g in guides}
        found = find_audio_overlaps(guides, spans)
        self.assertEqual(len(found), 1)
        first, second, window = found[0]
        self.assertEqual((first["id"], second["id"]), ("a", "b"))
        self.assertEqual(window, (24.0, 48.0))

    def test_parked_audio_does_not_overlap(self):
        guides = parse_guides([audio_guide("a", frame=0, end=64000, rate=32000),
                              audio_guide("b", frame=1, end=64000, rate=32000, enabled=False)])
        spans = {g["id"]: audio_span_frames(64000, 32000) for g in guides}
        self.assertEqual(find_audio_overlaps(guides, spans), [])


class ValidateTests(unittest.TestCase):
    def test_no_latent_is_the_first_message(self):
        guides = parse_guides([image_guide(0, frame=0)])
        self.assertIn("上游", validate_guides(guides, 0)[0])

    def test_out_of_range_image(self):
        guides = parse_guides([image_guide(0, frame=124)])
        errors = validate_guides(guides, 124)
        self.assertEqual(len(errors), 1)
        self.assertIn("超出视频范围", errors[0])
        self.assertIn("IMG-01", errors[0])

    def test_two_images_on_one_frame(self):
        guides = parse_guides([image_guide(0, frame=48, name="a.png"), image_guide(1, frame=48, name="b.png")])
        errors = validate_guides(guides, 124)
        self.assertEqual(len(errors), 1)
        self.assertIn("同一帧只能锚一张图片", errors[0])

    def test_image_and_audio_on_one_frame_is_allowed(self):
        guides = parse_guides([image_guide(0, frame=48), audio_guide("a", frame=48, end=3200, rate=32000)])
        spans = {g["id"]: audio_span_frames(3200, 32000) for g in guides}
        self.assertEqual(validate_guides(guides, 124, spans=spans), [])

    def test_audio_tail_past_the_end(self):
        guides = parse_guides([audio_guide("a", frame=100, end=64000, rate=32000)])
        spans = {"a": audio_span_frames(64000, 32000)}
        errors = validate_guides(guides, 124, spans=spans)
        self.assertEqual(len(errors), 1)
        self.assertIn("超出视频结尾", errors[0])

    def test_empty_audio_window(self):
        guides = parse_guides([audio_guide("a", frame=0, start=100, end=50)])
        errors = validate_guides(guides, 124, spans={"a": 1.0})
        self.assertTrue(any("裁切区间是空的" in error for error in errors))

    def test_image_clip_that_does_not_fit(self):
        guides = parse_guides([image_guide(0, frame=110)])
        errors = validate_guides(guides, 124, image_frames={"img0": 22})
        self.assertTrue(any("22 帧的片段" in error for error in errors))

    def test_unplaced_and_parked_are_not_validated(self):
        guides = parse_guides([image_guide(0, frame=None), image_guide(1, frame=9999, enabled=False)])
        self.assertEqual(validate_guides(guides, 124), [])

    def test_quota_is_reported_again_at_validation(self):
        guides = parse_guides([image_guide(i, frame=i) for i in range(MAX_GUIDE_IMAGES)])
        self.assertEqual(validate_guides(guides, 9999), [])
        # Built by hand: parse_guides would refuse this list first, and the node
        # must still report the quota if a future caller raises the limits.
        guides = [{
            "id": "g%d" % i, "kind": IMAGE_KIND, "label": "IMG-%02d" % (i + 1),
            "enabled": True, "frame_index": i,
            "asset": {"filename": "a.png", "subfolder": "", "type": "input"},
        } for i in range(MAX_GUIDE_TOTAL + 1)]
        errors = validate_guides(guides, 99999, spans={})
        self.assertTrue(any("合计" in error for error in errors))


class SummaryAndMergeTests(unittest.TestCase):
    def test_summary_counts(self):
        guides = parse_guides([image_guide(0, frame=0), image_guide(1, frame=10, enabled=False),
                              audio_guide("a", frame=12)])
        info = summary(guides, 124)
        self.assertEqual(info["images"], 1)
        self.assertEqual(info["audios"], 1)
        self.assertEqual(info["parked"], 1)
        self.assertEqual(info["frame_count"], 124)
        self.assertAlmostEqual(info["duration_seconds"], 124 / 24.0)
        self.assertEqual(info["fps"], DEFAULT_FPS)

    def test_merge_marks_the_source(self):
        local = parse_guides([image_guide(0, frame=0)])
        external = [{"id": "x", "kind": IMAGE_KIND, "frame_index": 10,
                     "asset": {"filename": "b.png", "subfolder": "", "type": "input"}}]
        merged = merge_guides(local, external)
        self.assertEqual([g["source"] for g in merged], ["local", "external"])
        self.assertEqual(ensure_labels(merged)[1]["label"], "IMG-02")


class FingerprintTests(unittest.TestCase):
    def test_missing_files_do_not_crash_the_cache_key(self):
        guides = parse_guides([image_guide(0, frame=0)])
        key = guide_fingerprint(guides, {"input": os.path.join(REPO, "tests")})
        self.assertEqual(len(key), 64)
        self.assertEqual(key, guide_fingerprint(guides, {}))

    def test_paths_are_read_in_list_order(self):
        from core.guide_timeline import guide_paths
        guides = parse_guides([image_guide(0, name="a.png"), image_guide(1, name="b.png")])
        self.assertEqual([entry["filename"] for entry in guide_paths(guides)], ["a.png", "b.png"])


if __name__ == "__main__":
    unittest.main()