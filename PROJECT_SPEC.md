# H3 Long Video Manager — Project Specification

## Overview

A ComfyUI custom node and frontend extension for managing long videos in MiniMax H3 workflows.
Provides video preparation, segmentation, selection, and direct VIDEO/IMAGE output for downstream H3 nodes.

## Phase 0 — Environment Investigation Results

### Target ComfyUI Installation
- **Location**: `E:\ai\ComfyUI-aki-v3\ComfyUI\`
- **Python**: 3.13 (64-bit, Windows)
- **Primary video library**: PyAV (`av>=17.0.0`)
- **No decord, no imageio**

### VIDEO Type System (this ComfyUI version)
- **Type definition**: `VideoInput` ABC in `comfy_api/latest/_input/video_types.py`
- **Create from file**: `InputImpl.VideoFromFile(path_or_bytesio)`
- **Create from tensors**: `InputImpl.VideoFromComponents(Types.VideoComponents(images=tensor, frame_rate=Fraction(24), audio=None))`
- **Core LoadVideo node**: outputs `VideoFromFile(video_path)` as VIDEO type

### Downstream H3 Node Compatibility
| Node | Input Type for Video | Notes |
|------|---------------------|-------|
| `MiniMaxH3ReferenceToVideo` (core) | **IMAGE** (tensor `[F,H,W,C]`) | Accepts video frames as image tensor |
| Motion Context (`context_frames`) | **IMAGE** | Decoded frames of previous clip |
| Motion Context (`context_latent`) | **LATENT** | Sampler output latent |
| Cloud H3 node | **VIDEO** (VideoInput) | Currently disabled |

### Output Strategy Decision
- **Primary output: IMAGE** (torch tensor `[F, H, W, C]`) — directly compatible with core H3 node
- **Secondary output: VIDEO** (VideoInput) — for broader compatibility, saving, future use
- This satisfies "directly connectable to a downstream MiniMax H3 video/reference-video node"

### Key Constraint
The core H3 `MiniMaxH3ReferenceToVideo` node declares `ref_videos` as `io.Image.Input` (autogrow, 0-3).
It expects a plain tensor of shape `[F, H, W, C]` with values in [0, 1] range.

## Architecture (original Phase 0 plan — historical)

The tree below is the plan written at Phase 0 and is kept for reference only.
Actual layout (verified against `git ls-files`) is in [README.md](README.md) → "Project structure".
Naming differences: `metadata.py`/`conform.py` were not created as separate modules — metadata probing lives in
`core/extraction.py` (`get_video_metadata()`) and scaling lives in `core/models.py` (`WorkingVideoConfig`) plus
`comfyui/nodes.py` (`_slice_and_scale()`). There is no `docs/` folder; the notes are top-level `.md` files.

```
H3-Long-Video-Manager/
├── core/              # Framework-independent logic (Layer A)
│   ├── __init__.py
│   ├── models.py      # Data models
│   ├── metadata.py    # Metadata detection
│   ├── conform.py     # FPS/resolution conform
│   ├── segmentation.py # Segment generation
│   ├── manifest.py    # Manifest generation
│   └── extraction.py  # Frame extraction
├── comfyui/           # ComfyUI integration (Layer B)
│   ├── __init__.py    # Node registration
│   └── nodes.py       # Custom node definitions
├── web/               # Frontend
│   └── extension.js
├── tests/             # Core unit tests
├── docs/              # Documentation
└── PROJECT_SPEC.md    # This file
```

## Development Status

Updated 2026-10-02 against the shipped code (`a9b7a46`). Version history: [VERSION.md](VERSION.md);
change record: [RAFOLIE_DEVELOPMENT.md](RAFOLIE_DEVELOPMENT.md).

- [x] Phase 0: Environment Investigation
- [x] Phase 1: Core Data Models — `core/models.py`
- [x] Phase 2: Metadata Detection — `core/extraction.py` → `get_video_metadata()` (no separate `metadata.py`)
- [~] Phase 3: H3 Working Video — resolution scaling via `WorkingVideoConfig` + `scale_percent`; FPS is supplied by the `video_fps` input, no automatic FPS conform
- [x] Phase 4: Segmentation — `core/h3_grid.py`, `core/segmentation.py`
- [x] Phase 5: Motion Context Range Calculation — `motion_context_frames` (5/22/39/56) + extraction ranges
- [x] Phase 6: Segment Manifest — `core/manifest.py`
- [x] Phase 7: Extraction Service — `core/extraction.py`
- [x] Phase 8: Core Regression Tests — `tests/` (77 tests)
- [~] Phase 9: ComfyUI Output — ships `IMAGE` + `AUDIO` (+ `frame_count`, `total_segments` / `segment_id`); the planned `VIDEO` (VideoInput) output was not implemented
- [x] Phase 10: Segment Selection Backend — `comfyui/segment_store.py`, `comfyui/server_api.py`
- [x] Phase 11: Frontend Foundation — `web/`
- [x] Phase 12: Segment Cards — `web/h3lvm_picker.js` (+ delete button)
- [ ] Phase 13: Timeline — not implemented
- [ ] Phase 14: Manual Segment Editing — not implemented
- [~] Phase 15: Export — only optional MP4 preview (`save_preview_mp4`); no general export
- [~] Phase 16: Polish — ComfyUI V3 API + Nodes 2.0 migration done (see [V3_MIGRATION.md](V3_MIGRATION.md))

Extra beyond this spec (not part of the original phase list): local segment bin with lossless
safetensors storage and thumbnails, person-detect crop (`core/person_crop.py`), segment deletion,
and the `segment_id` echo output for original-vs-regen alignment ([SEGMENT_ID_OUTPUT.md](SEGMENT_ID_OUTPUT.md)).

## Key Design Principles
1. Half-open intervals `[start, end)` throughout
2. Core is framework-independent and testable
3. Frontend does NOT reimplement segmentation math
4. Manifest is the source of truth
5. Motion Context = simple user-selected frame count only
6. Never modify the user's ComfyUI installation
