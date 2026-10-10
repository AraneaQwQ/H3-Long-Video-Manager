"""H3 reference size planner tests (pure functions, no ComfyUI needed)."""

import math
import unittest

from core.ref_size import (
    DEFAULT_MEGAPIXELS, DEFAULT_RESAMPLE_METHOD, DEFAULT_UPSCALE_SMALL_IMAGES,
    GRID, MAX_MEGAPIXELS, MIN_MEGAPIXELS, RESAMPLE_METHODS,
    clamp_megapixels, clamp_resampling_method, plan_grid_align, plan_reference, plan_size,
)

# Landscape, portrait, square, and deliberately awkward ratios.
SOURCES = [
    (1920, 1080), (1080, 1920), (1024, 1024), (4096, 2160), (2160, 4096),
    (640, 480), (480, 640), (2560, 1440), (1234, 567), (99, 101),
    (200, 9000), (9000, 200), (31, 31), (1, 1),
]
MEGAPIXELS = [MIN_MEGAPIXELS, 0.1, DEFAULT_MEGAPIXELS, 1.0, MAX_MEGAPIXELS]


def naive_plan(src_w, src_h, megapixels):
    """What a lazy implementation does: round each axis once. Used as a floor."""
    ratio = src_w / src_h
    area = megapixels * 1_000_000.0
    width = max(GRID, round(math.sqrt(area * ratio) / GRID) * GRID)
    height = max(GRID, round(math.sqrt(area / ratio) / GRID) * GRID)
    return width, height


class TestClampMegapixels(unittest.TestCase):
    def test_accepts_the_declared_range(self):
        for value in (MIN_MEGAPIXELS, DEFAULT_MEGAPIXELS, MAX_MEGAPIXELS, "0.4"):
            self.assertIsInstance(clamp_megapixels(value), float)

    def test_rejects_values_that_would_allocate_too_much_or_nothing(self):
        for value in (0, -1, None, "abc", float("nan"), float("inf"), float("-inf"),
                      MIN_MEGAPIXELS / 10, MAX_MEGAPIXELS * 2):
            with self.assertRaises(ValueError):
                clamp_megapixels(value)


class TestPlanSize(unittest.TestCase):
    def test_every_result_is_on_the_h3_grid(self):
        for src_w, src_h in SOURCES:
            for megapixels in MEGAPIXELS:
                plan = plan_size(src_w, src_h, megapixels)
                self.assertGreaterEqual(plan["width"], GRID)
                self.assertGreaterEqual(plan["height"], GRID)
                self.assertEqual(plan["width"] % GRID, 0, (src_w, src_h, megapixels, plan))
                self.assertEqual(plan["height"] % GRID, 0, (src_w, src_h, megapixels, plan))
                self.assertAlmostEqual(
                    plan["actual_megapixels"],
                    plan["width"] * plan["height"] / 1_000_000.0,
                    places=9,
                )

    def test_normal_aspect_ratios_stay_close_to_the_request(self):
        # 32 px steps are coarse, so these bounds are measured, not guessed: the
        # worst case in this table is 480x640 at 0.25 MP, where the planner trades
        # 9% area for 1.8% ratio because a stretched reference shows up sooner.
        for src_w, src_h in SOURCES:
            if max(src_w / src_h, src_h / src_w) > 3:
                continue
            for megapixels in MEGAPIXELS:
                if megapixels < DEFAULT_MEGAPIXELS:
                    continue
                plan = plan_size(src_w, src_h, megapixels)
                self.assertLessEqual(plan["area_error"], 0.10, (src_w, src_h, megapixels, plan))
                self.assertLessEqual(plan["ratio_error"], 0.04, (src_w, src_h, megapixels, plan))

    def test_never_worse_than_rounding_each_axis_once(self):
        # For extreme ratios the grid cannot honour both goals; the planner must
        # still beat the naive answer rather than drift arbitrarily.
        for src_w, src_h in SOURCES:
            for megapixels in MEGAPIXELS:
                width, height = naive_plan(src_w, src_h, megapixels)
                area_error = abs(width * height - megapixels * 1_000_000.0) / (megapixels * 1_000_000.0)
                ratio_error = abs((width / height) / (src_w / src_h) - 1.0)
                naive_cost = area_error + 3.0 * ratio_error
                plan = plan_size(src_w, src_h, megapixels)
                cost = plan["area_error"] + 3.0 * plan["ratio_error"]
                self.assertLessEqual(round(cost, 9), round(naive_cost, 9),
                                     (src_w, src_h, megapixels, plan, width, height))

    def test_same_input_always_gives_the_same_size(self):
        for src_w, src_h in SOURCES:
            first = plan_size(src_w, src_h, DEFAULT_MEGAPIXELS)
            for _ in range(20):
                self.assertEqual(plan_size(src_w, src_h, DEFAULT_MEGAPIXELS), first)

    def test_bigger_target_never_produces_a_smaller_frame(self):
        for src_w, src_h in [(1920, 1080), (1080, 1920), (1024, 1024)]:
            previous = 0
            for megapixels in [0.02, 0.05, 0.1, 0.2, 0.4, 0.5, 1.0, 2.0, 4.0, 8.0]:
                plan = plan_size(src_w, src_h, megapixels)
                area = plan["width"] * plan["height"]
                self.assertGreaterEqual(area, previous, (src_w, src_h, megapixels))
                previous = area

    def test_aspect_ratio_is_reported_not_promised(self):
        plan = plan_size(1920, 1080, 0.4)
        self.assertEqual((plan["width"], plan["height"]), (864, 480))
        self.assertGreater(plan["ratio_error"], 0.0)
        self.assertAlmostEqual(plan["actual_megapixels"], 0.41472, places=5)

    def test_unusable_source_sizes_are_errors(self):
        for src_w, src_h in [(0, 100), (100, 0), (-5, 100), (None, 100), ("a", 10)]:
            with self.assertRaises(ValueError):
                plan_size(src_w, src_h, DEFAULT_MEGAPIXELS)

    def test_bad_megapixels_are_errors(self):
        for value in (0, -0.5, "nope", float("inf")):
            with self.assertRaises(ValueError):
                plan_size(640, 480, value)



# Sources whose area is clearly above the targets used below, and sources clearly below.
BIG_SOURCES = [(1920, 1080), (1080, 1920), (1024, 1024), (2560, 1440), (4096, 2160)]
SMALL_SOURCES = [(640, 480), (480, 640), (320, 320), (300, 200), (320, 256)]
ALIGNED_SMALL = [(96, 96), (320, 256), (512, 512), (64, 192), (1024, 1024)]


class TestClampResamplingMethod(unittest.TestCase):
    def test_accepts_every_canonical_name(self):
        for name in RESAMPLE_METHODS:
            self.assertEqual(clamp_resampling_method(name), name)

    def test_tolerates_case_and_spaces_but_not_unknown_names(self):
        self.assertEqual(clamp_resampling_method("  lanczos "), "Lanczos")
        self.assertEqual(clamp_resampling_method("NEAREST"), "Nearest")
        for value in ("", "nearest-exact", "box", "lanczos3", None, 3, True):
            with self.assertRaises(ValueError):
                clamp_resampling_method(value)

    def test_defaults_match_the_options_the_ui_shows(self):
        self.assertIn(DEFAULT_RESAMPLE_METHOD, RESAMPLE_METHODS)
        self.assertIs(DEFAULT_UPSCALE_SMALL_IMAGES, False)


class TestPlanGridAlign(unittest.TestCase):
    def test_a_source_already_on_the_grid_is_left_alone(self):
        for width, height in ALIGNED_SMALL:
            plan = plan_grid_align(width, height)
            self.assertEqual((plan["width"], plan["height"]), (width, height), (width, height))
            self.assertEqual(plan["area_error"], 0.0)
            self.assertEqual(plan["ratio_error"], 0.0)

    def test_off_grid_sources_move_by_at_most_one_grid_step(self):
        for src_w, src_h in SOURCES:
            if src_w < GRID or src_h < GRID:
                continue
            plan = plan_grid_align(src_w, src_h)
            self.assertEqual(plan["width"] % GRID, 0, (src_w, src_h, plan))
            self.assertEqual(plan["height"] % GRID, 0, (src_w, src_h, plan))
            self.assertLessEqual(abs(plan["width"] - src_w), GRID, (src_w, src_h, plan))
            self.assertLessEqual(abs(plan["height"] - src_h), GRID, (src_w, src_h, plan))

    def test_aspect_ratio_survives_the_alignment(self):
        for src_w, src_h in SOURCES:
            if max(src_w, src_h) < 4 * GRID:
                continue
            plan = plan_grid_align(src_w, src_h)
            self.assertLessEqual(plan["ratio_error"], 0.10, (src_w, src_h, plan))

    def test_sizes_on_a_grid_boundary_are_decided_stably(self):
        # x.5 grid steps are where a bare round() flips with the platform, so the
        # tie-break has to produce one answer here too.
        for size in [(48, 48), (112, 48), (96, 112), (144, 112), (80, 80), (1000, 1000)]:
            first = plan_grid_align(*size)
            for _ in range(20):
                self.assertEqual(plan_grid_align(*size), first)
            self.assertEqual(first["width"] % GRID, 0)
            self.assertEqual(first["height"] % GRID, 0)

    def test_unusable_source_sizes_are_errors(self):
        for src_w, src_h in [(0, 100), (100, 0), (-1, -1), (None, 10), ("a", "b")]:
            with self.assertRaises(ValueError):
                plan_grid_align(src_w, src_h)


class TestPlanReference(unittest.TestCase):
    def test_large_images_reach_the_target_area_in_both_modes(self):
        for src_w, src_h in BIG_SOURCES:
            for upscale in (False, True):
                for megapixels in (0.1, DEFAULT_MEGAPIXELS, 1.0):
                    plan = plan_reference(src_w, src_h, megapixels, upscale)
                    self.assertEqual(plan["mode"], "target_mp",
                                     (src_w, src_h, megapixels, upscale, plan))
                    self.assertEqual(plan["width"] % GRID, 0)
                    self.assertEqual(plan["height"] % GRID, 0)
                    self.assertLessEqual(plan["ratio_error"], 0.04,
                                         (src_w, src_h, megapixels, upscale, plan))
                    if megapixels < DEFAULT_MEGAPIXELS:
                        # 32 px steps are coarse next to 0.1 MP, so a 15% area miss is
                        # the honest floor here; the ratio is what must stay exact.
                        continue
                    self.assertLessEqual(plan["area_error"], 0.10,
                                         (src_w, src_h, megapixels, upscale, plan))

    def test_small_images_only_follow_the_target_when_upscaling_is_on(self):
        for src_w, src_h in SMALL_SOURCES:
            off = plan_reference(src_w, src_h, 1.0, False)
            on = plan_reference(src_w, src_h, 1.0, True)
            self.assertEqual(on["mode"], "target_mp", (src_w, src_h, on))
            self.assertGreater(on["width"] * on["height"], src_w * src_h)
            self.assertEqual(off["mode"], "grid_align", (src_w, src_h, off))
            self.assertLess(off["width"] * off["height"], 500_000, (src_w, src_h, off))

    def test_small_images_keep_their_own_megapixels_when_upscaling_is_off(self):
        # The switch means "do not apply the target area", so the real MP must stay
        # next to the source MP instead of jumping to the requested target.
        for src_w, src_h in SMALL_SOURCES:
            for megapixels in (1.0, MAX_MEGAPIXELS):
                plan = plan_reference(src_w, src_h, megapixels, False)
                source_mp = src_w * src_h / 1_000_000.0
                self.assertAlmostEqual(plan["actual_megapixels"], source_mp,
                                       delta=source_mp * 0.10,
                                       msg=(src_w, src_h, megapixels, plan))

    def test_grid_aligned_small_images_are_not_touched_at_all(self):
        # "Small" is relative to the target: an image already below it must be left alone.
        for width, height in ALIGNED_SMALL:
            for megapixels in (DEFAULT_MEGAPIXELS, 1.0, MAX_MEGAPIXELS):
                if width * height > megapixels * 1_000_000.0:
                    continue
                plan = plan_reference(width, height, megapixels, False)
                self.assertEqual((plan["width"], plan["height"]), (width, height),
                                 (width, height, megapixels, plan))
                self.assertEqual(plan["mode"], "grid_align")

    def test_a_source_exactly_at_the_target_area_is_only_aligned(self):
        # "Upscaling off" is not "the pixel count never changes": 1000x1000 is 1.0 MP
        # and must not be treated as a downscale target, but it still needs the grid.
        plan = plan_reference(1000, 1000, 1.0, False)
        self.assertEqual(plan["mode"], "grid_align")
        self.assertEqual(plan["width"] % GRID, 0)
        self.assertEqual(plan["height"] % GRID, 0)
        self.assertLessEqual(plan["area_error"], 0.05)

    def test_both_modes_always_produce_legal_grid_sizes(self):
        for src_w, src_h in SOURCES:
            for upscale in (False, True):
                plan = plan_reference(src_w, src_h, DEFAULT_MEGAPIXELS, upscale)
                self.assertIn(plan["mode"], ("target_mp", "grid_align"))
                self.assertGreaterEqual(plan["width"], GRID)
                self.assertGreaterEqual(plan["height"], GRID)
                self.assertEqual(plan["width"] % GRID, 0, (src_w, src_h, upscale, plan))
                self.assertEqual(plan["height"] % GRID, 0, (src_w, src_h, upscale, plan))
                self.assertAlmostEqual(
                    plan["actual_megapixels"],
                    plan["width"] * plan["height"] / 1_000_000.0, places=9)

    def test_the_answer_is_deterministic(self):
        for src_w, src_h in SOURCES:
            for upscale in (False, True):
                first = plan_reference(src_w, src_h, DEFAULT_MEGAPIXELS, upscale)
                for _ in range(10):
                    self.assertEqual(
                        plan_reference(src_w, src_h, DEFAULT_MEGAPIXELS, upscale), first)

    def test_bad_settings_are_errors(self):
        with self.assertRaises(ValueError):
            plan_reference(0, 0, DEFAULT_MEGAPIXELS, False)
        for value in (0, -1, 99.0, "nope"):
            with self.assertRaises(ValueError):
                plan_reference(640, 480, value, False)

if __name__ == "__main__":
    unittest.main()
