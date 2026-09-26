"""Geometry tests for person-aware crop (no detector / torchvision required)."""

import os
import sys
import unittest

import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.person_crop import apply_crop, even, fit_crop_window, sample_indices


class TestPersonCropGeometry(unittest.TestCase):
    def test_even(self):
        self.assertEqual(even(0), 0)
        self.assertEqual(even(7), 6)
        self.assertEqual(even(8), 8)

    def test_sample_indices_span(self):
        indices = sample_indices(100, 16)
        self.assertEqual(indices[0], 0)
        self.assertEqual(indices[-1], 99)
        self.assertLessEqual(len(indices), 16)

    def test_sample_short_video(self):
        self.assertEqual(sample_indices(3, 16), [0, 1, 2])
        self.assertEqual(sample_indices(0, 16), [])

    def test_expand_zero_keeps_aspect_and_covers_box(self):
        # 1080x1920 9:16, person in the middle
        x, y, w, h = fit_crop_window(
            1080, 1920, boxes=[(300, 400, 780, 1500)], expand_percent=0
        )
        self.assertEqual(x % 2, 0)
        self.assertEqual(y % 2, 0)
        self.assertEqual(w % 2, 0)
        self.assertEqual(h % 2, 0)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + w, 1080)
        self.assertLessEqual(y + h, 1920)
        self.assertLessEqual(x, 300)
        self.assertGreaterEqual(x + w, 780)
        self.assertAlmostEqual(w / h, 1080 / 1920, places=2)
        self.assertLess(w, 1080)

    def test_expand_makes_window_larger(self):
        boxes = [(400, 500, 700, 1400)]
        tight = fit_crop_window(1080, 1920, boxes, expand_percent=0)
        loose = fit_crop_window(1080, 1920, boxes, expand_percent=25)
        self.assertGreaterEqual(loose[2] * loose[3], tight[2] * tight[3])

    def test_expand_100_clamps_to_frame(self):
        x, y, w, h = fit_crop_window(
            1080, 1920, boxes=[(100, 100, 980, 1820)], expand_percent=100
        )
        self.assertEqual((x, y, w, h), (0, 0, 1080, 1920))

    def test_union_of_boxes(self):
        x, y, w, h = fit_crop_window(
            1080,
            1920,
            boxes=[(200, 200, 400, 800), (500, 900, 800, 1600)],
            expand_percent=0,
        )
        self.assertLessEqual(x, 200)
        self.assertGreaterEqual(x + w, 800)

    def test_reject_bad_expand(self):
        with self.assertRaises(ValueError):
            fit_crop_window(1080, 1920, [(0, 0, 100, 100)], expand_percent=-1)
        with self.assertRaises(ValueError):
            fit_crop_window(1080, 1920, [(0, 0, 100, 100)], expand_percent=101)
        with self.assertRaises(ValueError):
            fit_crop_window(1080, 1920, [], expand_percent=0)

    def test_apply_crop_tensor(self):
        video = torch.zeros(4, 1920, 1080, 3)
        video[:, 100:300, 40:80, :] = 1.0
        cropped = apply_crop(video, 40, 100, 40, 200)
        self.assertEqual(tuple(cropped.shape), (4, 200, 40, 3))
        self.assertEqual(float(cropped.min()), 1.0)


if __name__ == "__main__":
    unittest.main()
