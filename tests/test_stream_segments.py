"""Streaming batches must reproduce the established v1 segment ranges."""
import unittest

import torch

from core.h3_grid import generate_fixed_segments
from core.smart_split import build_smart_segments
from core.stream_segments import iter_fixed_segment_batches, iter_smart_segment_batches


def frames(total):
    return [torch.full((1, 1, 3), index, dtype=torch.int32) for index in range(total)]


class TestFixedStreamSegments(unittest.TestCase):
    def test_ranges_and_pixels_match_v1(self):
        for total in list(range(1, 170)) + [260, 261, 265, 500]:
            expected = generate_fixed_segments(total, 39, 5)
            batches = list(iter_fixed_segment_batches(frames(total), 39, 5))
            self.assertEqual([item[0] for item in batches], expected, total)
            for meta, batch in batches:
                values = [int(frame[0, 0, 0].item()) for frame in batch]
                self.assertEqual(values, list(range(meta["extract_start"], meta["extract_end"])))

    def test_exact_full_length_does_not_invent_a_context_only_tail(self):
        batches = list(iter_fixed_segment_batches(frames(39), 39, 5))
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0][0]["extract_frames"], 39)

    def test_invalid_main_length_uses_the_v1_guard(self):
        with self.assertRaisesRegex(ValueError, "至少需要 5 帧"):
            list(iter_fixed_segment_batches(frames(100), 39, 39))


class TestSmartStreamSegments(unittest.TestCase):
    def test_ranges_and_motion_context_match_v1(self):
        source = frames(100)
        segments = build_smart_segments(100, [20, 55], 5)
        batches = list(iter_smart_segment_batches(source, segments, 5))
        self.assertEqual([item[0] for item in batches], segments)
        for meta, batch in batches:
            self.assertEqual(len(batch), meta["extract_frames"])
            self.assertEqual([int(frame[0, 0, 0].item()) for frame in batch],
                             list(range(meta["extract_start"], meta["extract_end"])))

    def test_zero_context_does_not_accumulate_history(self):
        segments = build_smart_segments(100, [50], 0)
        batches = list(iter_smart_segment_batches(frames(100), segments, 0))
        self.assertEqual([len(batch) for _meta, batch in batches], [50, 50])

    def test_truncated_decode_is_an_error(self):
        segments = build_smart_segments(100, [50], 0)
        with self.assertRaisesRegex(ValueError, "提前结束"):
            list(iter_smart_segment_batches(frames(99), segments, 0))


if __name__ == "__main__":
    unittest.main()
