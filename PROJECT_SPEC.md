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

## Architecture

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
- [x] Phase 0: Environment Investigation
- [ ] Phase 1: Core Data Models
- [ ] Phase 2: Metadata Detection
- [ ] Phase 3: H3 Working Video (FPS conform, resolution)
- [ ] Phase 4: Segmentation
- [ ] Phase 5: Motion Context Range Calculation
- [ ] Phase 6: Segment Manifest
- [ ] Phase 7: Extraction Service
- [ ] Phase 8: Core Regression Tests
- [ ] Phase 9: ComfyUI VIDEO Output
- [ ] Phase 10: Segment Selection Backend
- [ ] Phase 11: Frontend Foundation
- [ ] Phase 12: Segment Cards
- [ ] Phase 13: Timeline
- [ ] Phase 14: Manual Segment Editing
- [ ] Phase 15: Export
- [ ] Phase 16: Polish

## Key Design Principles
1. Half-open intervals `[start, end)` throughout
2. Core is framework-independent and testable
3. Frontend does NOT reimplement segmentation math
4. Manifest is the source of truth
5. Motion Context = simple user-selected frame count only
6. Never modify the user's ComfyUI installation
