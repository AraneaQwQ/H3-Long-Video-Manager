"""H3 Long Video Manager — H3 Frame Grid Alignment & Seamless Segmentation.

MiniMax H3 video VAE requires frame counts to satisfy:
    num_frames = 17n + 5   (n >= 0)

Valid frame counts: 5, 22, 39, 56, 73, 90, 107, 124, 141, 158, 175, 192, ...

Seamless segmentation principle (user requirement):
- Every main segment is a valid 17n+5 frame count
- Segments are contiguous: seg[i+1].start == seg[i].end (NO GAPS)
- Truncated frames from alignment "slide" to the next segment (carry-forward)
- Only the final segment may lose a few frames (unavoidable end-of-video compromise)
"""

from __future__ import annotations


def align_down_to_h3_grid(frame_count: int) -> int:
    """Align frame count DOWN to the nearest valid 17n+5 value.
    
    Args:
        frame_count: desired frame count (positive integer)
    
    Returns:
        Largest valid (17n+5) value that is <= frame_count.
        Minimum return is 5 (the smallest valid H3 frame count).
    
    Examples:
        >>> align_down_to_h3_grid(5)
        5
        >>> align_down_to_h3_grid(22)
        22
        >>> align_down_to_h3_grid(144)
        141
        >>> align_down_to_h3_grid(166)
        158
        >>> align_down_to_h3_grid(240)
        226
        >>> align_down_to_h3_grid(254)
        243
    """
    if frame_count <= 0:
        return 0
    if frame_count <= 5:
        return 5
    k = (frame_count - 5) // 17
    return 17 * k + 5


def align_up_to_h3_grid(frame_count: int) -> int:
    """Align frame count UP to the nearest valid 17n+5 value."""
    if frame_count <= 5:
        return 5
    k = (frame_count - 5 + 16) // 17
    result = 17 * k + 5
    return max(5, result)


def is_valid_h3_frame_count(frame_count: int) -> bool:
    """Check if a frame count is valid for H3 (17n + 5 form)."""
    if frame_count < 5:
        return False
    return (frame_count - 5) % 17 == 0


def nearest_valid_range(desired: int) -> tuple[int, int]:
    """Return (lower, upper) valid H3 frame counts bracketing `desired`."""
    lower = align_down_to_h3_grid(desired)
    if lower == desired:
        return (desired, desired)
    upper = align_up_to_h3_grid(desired)
    return (lower, upper)


# ---------------------------------------------------------------------------
# Seamless Aligned Segmentation (Carry-Forward Algorithm)
# ---------------------------------------------------------------------------


def generate_aligned_segments(
    total_frames: int,
    target_frames_per_segment: int,
) -> list[tuple[int, int]]:
    """Generate seamless H3-aligned segments using carry-forward.

    Core principle:
    1. Each segment's frame count is a valid 17n+5 value
    2. Segments are contiguous: seg[i+1].start == seg[i].end (no gaps)
    3. Frames "lost" from alignment are carried forward to the next segment
    4. Only the final segment may lose frames (end-of-video compromise)

    Algorithm (carry-forward):
    - Start at position 0 with carry=0
    - For each non-final segment:
      effective_target = target + carry
      aligned = align_down(effective_target)
      new_carry = effective_target - aligned  (pushed to next segment)
    - For the final segment (remaining <= target + carry):
      aligned = align_down(remaining)
      Any residual loss is the unavoidable end-of-video compromise

    Example:
        total=1440, target=240:
        Seg 0: eff=240, aligned=226, carry=14  → [0, 226)
        Seg 1: eff=254, aligned=243, carry=11  → [226, 469)
        Seg 2: eff=251, aligned=243, carry=8   → [469, 712)
        Seg 3: eff=248, aligned=243, carry=5   → [712, 955)
        Seg 4: eff=245, aligned=243, carry=2   → [955, 1198)
        Seg 5: FINAL, remaining=242, aligned=226 → [1198, 1424)
        
        Verify: 226+243+243+243+243+226 = 1424 ≤ 1440 ✓
        Contiguous: 226=226, 469=469, 712=712, 955=955, 1198=1198 ✓
        All valid 17n+5: 226(17×13+5), 243(17×14+5) ✓
        Lost: 1440-1424 = 16 frames (final segment compromise) ✓

    Args:
        total_frames: total frames in the video
        target_frames_per_segment: desired frames per segment (will be aligned)
    
    Returns:
        List of (start, end) half-open intervals, all contiguous, all 17n+5
    """
    if total_frames <= 0:
        return []
    if target_frames_per_segment < 5:
        target_frames_per_segment = 5

    # Edge case: video too short for even one valid H3 segment
    if total_frames < 5:
        return [(0, total_frames)]

    segments: list[tuple[int, int]] = []
    current_pos = 0
    carry = 0

    while current_pos < total_frames:
        remaining = total_frames - current_pos

        # Check if this is (or will be) the final segment
        if remaining <= target_frames_per_segment + carry:
            # Final segment: take all remaining, align down
            aligned = align_down_to_h3_grid(remaining)
            if aligned > remaining:
                # Can't align up — use remaining as-is (extreme edge)
                aligned = remaining
            if aligned < 5:
                # Merge into previous segment (extreme edge case)
                if segments:
                    prev_start = segments[-1][0]
                    segments[-1] = (prev_start, total_frames)
                else:
                    segments.append((0, remaining))
                break
            end = current_pos + aligned
            segments.append((current_pos, end))
            # Frames beyond `end` are lost (end-of-video compromise)
            break

        # Non-final segment: use target + carry
        effective_target = target_frames_per_segment + carry
        aligned = align_down_to_h3_grid(effective_target)
        if aligned < 5:
            aligned = 5

        end = current_pos + aligned
        carry = effective_target - aligned  # Push lost frames to next segment

        segments.append((current_pos, end))
        current_pos = end

    return segments


def generate_aligned_segments_with_mc(
    total_frames: int,
    target_frames_per_segment: int,
    motion_context_frames: int = 0,
) -> list[dict]:
    """Generate segments with both main range and optional context range.
    
    The main segments are seamless (contiguous, no gaps, each 17n+5).
    The context range extends backward into the previous segment (for
    Motion Context use). The total extraction (context + main) may not
    be 17n+5 — H3 auto-snaps when receiving the video.
    
    Args:
        total_frames: total frames in the video
        target_frames_per_segment: desired main frames per segment
        motion_context_frames: MC context frames (0, 5, 22, 39, or 56)
    
    Returns:
        List of dicts with main/context/extraction ranges
    """
    main_segments = generate_aligned_segments(total_frames, target_frames_per_segment)
    
    results = []
    for idx, (main_start, main_end) in enumerate(main_segments):
        main_frames = main_end - main_start
        
        # Context: preceding MC frames (clamped at 0)
        ctx_start = max(0, main_start - motion_context_frames)
        ctx_end = main_start
        ctx_frames = ctx_end - ctx_start
        
        results.append({
            "segment_id": idx,
            "main_start": main_start,
            "main_end": main_end,
            "main_frames": main_frames,
            "context_start": ctx_start,
            "context_end": ctx_end,
            "context_frames": ctx_frames,
            "extract_start": ctx_start,
            "extract_end": main_end,
            "extract_frames": ctx_frames + main_frames,
        })
    
    return results
