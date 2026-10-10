"""H3 reference image size planning (pure functions: no torch, no file IO).

MiniMax H3 only accepts canvases whose width and height are multiples of 32
(comfy_extras/nodes_minimax_h3.py builds its own sizes with CANVAS_MULTIPLE = 32),
so a reference loader cannot promise "exactly N megapixels at the source aspect
ratio". It picks the legal grid size that is closest to BOTH the target area and
the source ratio, and reports what it actually produced.

Nothing here crops or pads: the caller resizes the whole frame to (width, height).

Two modes decide the target area (see plan_reference):
  - upscale_small_images=True  -> every image is scaled to the target megapixels;
  - upscale_small_images=False -> only images bigger than the target are scaled down,
    smaller ones are only nudged onto the 32 grid, which is the least change that is
    legal. "Not upscaled" therefore does not mean "the pixel count never changes".
"""
from __future__ import annotations

import math

# H3 canvas grid. Reference images and generated frames share it.
GRID = 32

# Kept in the same place as the node's widget range so the UI and the planner
# cannot disagree about what is accepted.
MIN_MEGAPIXELS = 0.02
MAX_MEGAPIXELS = 8.0
DEFAULT_MEGAPIXELS = 0.25

# Refuse to decode anything bigger than this before touching pixels: a 100 MP
# "image bomb" would be decoded, resized and uploaded to the GPU for nothing.
MAX_SOURCE_PIXELS = 40_000_000

# A wrong aspect ratio is more visible in a reference image than a slightly wrong
# area (H3 downscales the area anyway), so ratio error costs more in the score.
RATIO_WEIGHT = 3.0

# How many grid steps around the ideal size are scored. Two steps is enough to
# recover from rounding at both ends, and keeps the candidate set tiny.
SEARCH_STEPS = 2

# The resampling method is the user's choice, and the node has to use exactly what the
# widget says, so the option list lives here: the node, the UI labels and the tests all
# read the same tuple.
RESAMPLE_LANCZOS = "Lanczos"
RESAMPLE_BICUBIC = "Bicubic"
RESAMPLE_BILINEAR = "Bilinear"
RESAMPLE_NEAREST = "Nearest"
RESAMPLE_METHODS = (RESAMPLE_LANCZOS, RESAMPLE_BICUBIC, RESAMPLE_BILINEAR, RESAMPLE_NEAREST)
DEFAULT_RESAMPLE_METHOD = RESAMPLE_LANCZOS

# Off by default: blowing a small image up to the target area costs memory and time in
# the H3 encoder for detail the source does not have.
DEFAULT_UPSCALE_SMALL_IMAGES = False


def clamp_megapixels(value) -> float:
    """Validate a target megapixel value and return it as a float.

    Raises ValueError with the supported range so a bad widget value produces a
    readable node error instead of a huge allocation.
    """
    try:
        megapixels = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            "target_megapixels must be a number between "
            f"{MIN_MEGAPIXELS} and {MAX_MEGAPIXELS}"
        )
    if not math.isfinite(megapixels):
        raise ValueError("target_megapixels must be a finite number")
    if megapixels < MIN_MEGAPIXELS or megapixels > MAX_MEGAPIXELS:
        raise ValueError(
            f"target_megapixels={megapixels} is outside the supported range "
            f"{MIN_MEGAPIXELS}-{MAX_MEGAPIXELS}"
        )
    return megapixels


def clamp_resampling_method(value) -> str:
    """Return the canonical method name for whatever the widget sent.

    Tolerant about case and surrounding spaces (a hand-written API call is allowed to
    say "lanczos"), strict about everything else: a name that is not on the list must
    fail here rather than quietly resize with the default filter.
    """
    if not isinstance(value, str):
        raise ValueError(
            "resampling_method must be one of " + ", ".join(RESAMPLE_METHODS))
    wanted = value.strip().lower()
    for name in RESAMPLE_METHODS:
        if name.lower() == wanted:
            return name
    raise ValueError(
        f"resampling_method={value!r} is not one of " + ", ".join(RESAMPLE_METHODS))


def _source_size(src_width, src_height) -> tuple:
    """Validate a source size once, for every planner below."""
    try:
        width = int(src_width)
        height = int(src_height)
    except (TypeError, ValueError):
        raise ValueError("source width and height must be integers")
    if width <= 0 or height <= 0:
        raise ValueError(f"source size {width}x{height} is not a usable image")
    return width, height


def _score(width: int, height: int, target_area: float, ratio: float) -> tuple:
    area_error = abs(width * height - target_area) / target_area
    ratio_error = abs((width / height) / ratio - 1.0)
    cost = area_error + RATIO_WEIGHT * ratio_error
    # Full tie-break: cost, then each error on its own, then the smaller frame.
    # Same input must always give the same output, from any call path.
    return (round(cost, 12), round(ratio_error, 12), round(area_error, 12),
            width * height, width, height, area_error, ratio_error)


def plan_size(src_width: int, src_height: int, target_megapixels) -> dict:
    """Return the legal 32-grid size closest to the target MP and source ratio.

    The image is never cropped, so an arbitrary source ratio cannot be reproduced
    exactly; the returned actual_megapixels / errors are what the UI shows.
    """
    src_w, src_h = _source_size(src_width, src_height)
    megapixels = clamp_megapixels(target_megapixels)
    target_area = megapixels * 1_000_000.0
    ratio = src_w / src_h

    ideal_w = math.sqrt(target_area * ratio)
    ideal_h = math.sqrt(target_area / ratio)
    base_iw = max(1, int(round(ideal_w / GRID)))
    base_ih = max(1, int(round(ideal_h / GRID)))

    # Candidates come from three ideas of "right": the ideal size, the size that
    # hits the target area for this height, and the size that hits the source
    # ratio for this height. Clamping to one grid unit (very wide/tall sources or
    # tiny targets) is exactly where the ideal size alone goes wrong.
    candidates = set()
    for ih in range(max(1, base_ih - SEARCH_STEPS), base_ih + SEARCH_STEPS + 1):
        height = ih * GRID
        iw_area = max(1, int(round(target_area / height / GRID)))
        iw_ratio = max(1, int(round((height * ratio) / GRID)))
        for iw in (base_iw, iw_area, iw_ratio):
            for step in (-1, 0, 1):
                jw = iw + step
                if jw >= 1:
                    candidates.add((jw, ih))

    best_key = None
    best_units = None
    for iw, ih in candidates:
        key = _score(iw * GRID, ih * GRID, target_area, ratio)
        if best_key is None or key < best_key:
            best_key = key
            best_units = (iw, ih)

    width, height = best_units[0] * GRID, best_units[1] * GRID
    return {
        "width": width,
        "height": height,
        "actual_megapixels": (width * height) / 1_000_000.0,
        "area_error": best_key[6],
        "ratio_error": best_key[7],
    }

def _align_score(src_w: int, src_h: int, width: int, height: int) -> tuple:
    source_area = src_w * src_h
    area_change = abs(width * height - source_area) / source_area
    ratio_error = abs((width / height) / (src_w / src_h) - 1.0)
    axis_change = max(abs(width - src_w) / src_w, abs(height - src_h) / src_h)
    # "Least change" has to be written down, not left to rounding: smallest change of
    # total pixels, then smallest ratio error, then the smallest single-axis move, then
    # the smaller frame. Same input, same answer, from any call path.
    return (round(area_change, 12), round(ratio_error, 12), round(axis_change, 12),
            width * height, width, height, area_change, ratio_error)


def plan_grid_align(src_width, src_height) -> dict:
    """The nearest legal 32-grid size to the source, with no target area involved.

    This is what a small image gets when upscaling is off: at most one grid step per
    axis, so the pixel count moves by a few percent instead of jumping to the target
    megapixels. A source already on the grid is returned unchanged, which is how the
    caller knows to skip resampling it.
    """
    src_w, src_h = _source_size(src_width, src_height)
    if src_w % GRID == 0 and src_h % GRID == 0:
        return {
            "width": src_w,
            "height": src_h,
            "actual_megapixels": (src_w * src_h) / 1_000_000.0,
            "area_error": 0.0,
            "ratio_error": 0.0,
        }

    base_iw = max(1, int(round(src_w / GRID)))
    base_ih = max(1, int(round(src_h / GRID)))
    best_key = None
    best_size = None
    for iw in range(max(1, base_iw - 1), base_iw + 2):
        for ih in range(max(1, base_ih - 1), base_ih + 2):
            key = _align_score(src_w, src_h, iw * GRID, ih * GRID)
            if best_key is None or key < best_key:
                best_key = key
                best_size = (iw * GRID, ih * GRID)

    width, height = best_size
    return {
        "width": width,
        "height": height,
        "actual_megapixels": (width * height) / 1_000_000.0,
        "area_error": best_key[6],
        "ratio_error": best_key[7],
    }


def plan_reference(src_width, src_height, target_megapixels,
                   upscale_small_images=DEFAULT_UPSCALE_SMALL_IMAGES) -> dict:
    """The size a reference image actually gets, for the node's two settings.

    Scaling stays proportional in both modes: the source aspect ratio is the target,
    nothing is cropped, padded or stretched to a common frame, and both output axes are
    multiples of 32. "Upscaling off" means the target area is not applied to a small
    image - the grid alignment may still change its size very slightly.

    mode is part of the answer because the card has to explain a small image that
    stayed small: "target_mp" applied the target area, "grid_align" only applied the
    grid.
    """
    src_w, src_h = _source_size(src_width, src_height)
    megapixels = clamp_megapixels(target_megapixels)

    if upscale_small_images or src_w * src_h > megapixels * 1_000_000.0:
        plan = plan_size(src_w, src_h, megapixels)
        plan["mode"] = "target_mp"
        return plan

    plan = plan_grid_align(src_w, src_h)
    plan["mode"] = "grid_align"
    return plan
