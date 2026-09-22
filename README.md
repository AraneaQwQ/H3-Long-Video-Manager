# H3 Long Video Manager

**[English](#english)** | **[简体中文](#简体中文)**

---

## English

> **Seamless 17n+5 video segmenter + local segment bin** for MiniMax H3 long-video workflows.

Cut any long video into H3-compatible segments (each satisfying the `17n + 5` frame rule), save them all to a local library with thumbnails, and retrieve any segment on-demand — no re-loading the source video.

### What it does

| Node | Role |
|------|------|
| **H3 Long Video Manager** | Input: video + audio → Output: all segments saved to bin + selected segment live |
| **H3 Segment Picker** | Input: project name + segment ID → Output: IMAGE + AUDIO (feeds H3 directly) |

### Key features

- **17n+5 grid alignment** — every segment is a valid H3 frame count (no auto-snap surprises)
- **Carry-forward seamless segmentation** — no frames lost between segments, only the final segment may be short
- **Motion Context aware** — extraction range includes MC context frames for continuity
- **Local segment bin** — lossless safetensors storage, thumbnail covers, optional MP4 preview
- **Visual card picker** — click a thumbnail to select a segment, no re-loading video
- **Zero dependency** beyond `torch` + `safetensors` (both already in ComfyUI)

### How it works

```
Long video (e.g. 430 frames @ 24fps)
  │
  ▼
H3 Long Video Manager
  ├── Segments: [0,158) [158,333) [333,423)   ← all 17n+5, contiguous
  ├── Saves all → output/h3-lvm/<project>/seg01/, seg02/, seg03/
  └── Outputs selected segment live (IMAGE + AUDIO)
  │
  ▼ (later, without re-loading video)
H3 Segment Picker
  ├── Loads from bin → IMAGE + AUDIO
  └── Feeds directly into MiniMaxH3ReferenceToVideo (ref_videos + ref_audio)
```

### Use Cases

| Scenario | How |
|----------|-----|
| **Long video → H3 generation** | 60s reference video → cut into 6×10s segments → generate stylized versions per segment with H3 ref2va → stitch |
| **Motion Context chaining** | Picker outputs segment N → use as ref_video + MC context for segment N+1 → coherent long-video generation |
| **Rapid iteration** | Same segment, different prompts/params → no re-loading, just Picker → H3 |
| **Parallel generation** | Cut once into 6 segments → run 6 H3 workflows in parallel → merge |
| **Asset library** | Different projects use different `project_name` — isolated, searchable, persistent |

**Where it fits in your H3 workflow:**

```
[Before]  Load Video → manual cut → H3 ref2va → output
[After]   First:  Load Video → [Manager] → saves all + outputs
          Later:  [Picker] → H3 ref2va → output
                            ↑ no Load Video, no manual cut, frames already 17n+5
```

### Not for

- Real-time streaming (this is an offline cut + store tool)
- Non-H3 models (frame grid rule differs)
- GPU inference (pure CPU: slice + file I/O only)

---

### Installation

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/AraneaQwQ/H3-Long-Video-Manager.git
```

Restart ComfyUI, hard-refresh browser (`Ctrl+F5`).

> **Requires**: ComfyUI ≥ 0.34.0, `torch`, `safetensors` (all standard in ComfyUI installs).

### Storage layout

```
ComfyUI/output/h3-lvm/<project_name>/
├── h3lvm_index.json          # project manifest
├── seg01/
│   ├── seg01.safetensors     # lossless: video f16 + audio f32 + metadata
│   ├── seg01_first.png       # thumbnail (card cover)
│   └── seg01.mp4             # optional preview (only if save_preview_mp4=True)
├── seg02/
│   └── ...
```

### Node parameters

#### H3 Long Video Manager

| Parameter | Default | Notes |
|-----------|---------|-------|
| `video_fps` | 24 | Source video frame rate |
| `segment_duration` | 6.0s | Target duration per segment |
| `motion_context_frames` | 22 | MC context (5/22/39/56) |
| `segment_id` | 1 | Which segment to output live |
| `scale_percent` | 100 | Downscale (e.g. 50 = half resolution) |
| `align_to_h3_grid` | true | Enforce 17n+5 |
| `project_name` | H3_LVM | Bin folder name |
| `save_enabled` | true | Save to bin (disable for pure-live mode) |
| `save_preview_mp4` | false | Also encode MP4 preview |

#### H3 Segment Picker

| Parameter | Default | Notes |
|-----------|---------|-------|
| `project_name` | H3_LVM | Which bin to read from |
| `segment_id` | 1 | Which segment to load |

### API endpoints

| Endpoint | Returns |
|----------|---------|
| `GET /h3_lvm/projects` | `{"projects": [...], "default": "H3_LVM"}` |
| `GET /h3_lvm/segments?project=<name>` | Full segment list with thumbnail URLs |

### Project structure

```
H3-Long-Video-Manager/
├── __init__.py              # Entry: nodes + routes + web
├── README.md
├── comfyui/
│   ├── __init__.py
│   ├── nodes.py             # Manager (v3) + Picker nodes
│   ├── nodes_v2.py          # backup (pre-save-bin)
│   ├── nodes_v1.py          # backup (pre-audio)
│   ├── segment_store.py     # Storage layer (save/load/list/delete)
│   └── server_api.py        # HTTP API routes
├── core/
│   ├── __init__.py
│   ├── models.py            # Dataclasses (Segment, Manifest, etc.)
│   ├── h3_grid.py           # 17n+5 alignment + carry-forward segmentation
│   ├── manifest.py          # build_manifest()
│   ├── segmentation.py      # Duration → frames computation
│   └── extraction.py        # (reserved)
├── web/
│   ├── h3lvm_picker.js      # Phase B2: card gallery frontend
│   ├── h3lvm_picker.css     # Styling
│   └── extension.js         # (placeholder, intentionally empty)
└── tests/
    ├── __init__.py
    ├── test_segment_store.py
    ├── test_h3_grid.py
    ├── test_core.py
    └── test_frame_integrity.py
```

---
---

## 简体中文

> **MiniMax H3 长视频工作流的无缝分段器 + 本地片段库。**

将任意长视频按 **17n+5** 帧规则裁切为 H3 兼容片段，全部保存到本地库（含缩略图），后续无需重新载入源视频即可随时取用任何一段。

### 功能

| 节点 | 作用 |
|------|------|
| **H3 Long Video Manager** | 接入视频 → 分段 → 全部存库 → 实时输出选中段 |
| **H3 Segment Picker** | 从库中读取 → 输出 IMAGE + AUDIO（直接喂 H3） |

### 核心特性

- **17n+5 网格对齐** — 每段都是合法 H3 帧数，不会自动 snap 导致时长偏移
- **Carry-forward 无缝分段** — 中间段零帧丢失，仅最后一段可能偏短
- **Motion Context 感知** — 提取范围包含 MC 上下文帧，保证接续连贯
- **本地片段库** — 无损 safetensors 存储 + 首帧缩略图 + 可选 MP4 预览
- **视觉卡片选择** — 点击缩略图选段，无需重新加载视频
- **零额外依赖** — 仅需 `torch` + `safetensors`（ComfyUI 自带）

### 工作流程

```
长视频 (如 430帧 @ 24fps)
  │
  ▼
H3 Long Video Manager
  ├── 分段: [0,158) [158,333) [333,423)   ← 全部 17n+5，连续无间隙
  ├── 保存全部 → output/h3-lvm/<项目名>/seg01/, seg02/, seg03/
  └── 实时输出选中段 (IMAGE + AUDIO)
  │
  ▼ (之后，无需重新载入视频)
H3 Segment Picker
  ├── 从库读取 → IMAGE + AUDIO
  └── 直接接入 MiniMaxH3ReferenceToVideo (ref_videos + ref_audio)
```

### 使用场景

| 场景 | 怎么用 |
|------|--------|
| **长视频分镜生成** | 60s 参考视频 → 切成 6×10s 段 → 逐段用 H3 ref2va 生成风格化版本 → 拼接 |
| **Motion Context 接续** | Picker 输出段 N → 作为段 N+1 的 ref_video + MC 上下文 → 连贯长视频生成 |
| **反复实验同一段** | 同一段素材试不同 prompt/参数 → 不用重新 Load，直接 Picker 取 |
| **多段并行生成** | 一次裁好 6 段 → 开 6 个 H3 工作流分别生成 → 最后拼接 |
| **素材库管理** | 不同项目用不同 `project_name` 分开存，互不干扰 |

**在 H3 工作流中的位置：**

```
[之前]  Load Video → 手动裁 → H3 ref2va → 输出
[现在]  第一次: Load Video → [Manager] → 存库 + 输出
        之后:  [Picker] → H3 ref2va → 输出
                          ↑ 无需 Load Video，无需手动裁，帧数已对齐 17n+5
```

### 不适用

- 实时流处理（这是离线裁切+存储工具）
- 非 H3 模型（帧数规则不同）
- 需要 GPU 推理的场景（本节点纯 CPU：切片+文件读写）

---

### 安装

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/AraneaQwQ/H3-Long-Video-Manager.git
```

重启 ComfyUI，强刷浏览器（`Ctrl+F5`）。

> **要求**：ComfyUI ≥ 0.34.0，`torch`，`safetensors`（标准 ComfyUI 环境均自带）。

### 存储结构

```
ComfyUI/output/h3-lvm/<项目名>/
├── h3lvm_index.json          # 项目索引
├── seg01/
│   ├── seg01.safetensors     # 无损: 视频f16 + 音频f32 + 元数据
│   ├── seg01_first.png       # 缩略图（卡片封面）
│   └── seg01.mp4             # 可选预览（需开启 save_preview_mp4）
├── seg02/
│   └── ...
```

### 节点参数

#### H3 Long Video Manager

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `video_fps` | 24 | 源视频帧率 |
| `segment_duration` | 6.0s | 每段目标时长 |
| `motion_context_frames` | 22 | MC 上下文（5/22/39/56） |
| `segment_id` | 1 | 实时输出哪一段 |
| `scale_percent` | 100 | 缩放比例（50 = 一半分辨率） |
| `align_to_h3_grid` | true | 是否对齐 17n+5 |
| `project_name` | H3_LVM | 库文件夹名 |
| `save_enabled` | true | 是否存库（关 = 纯实时模式） |
| `save_preview_mp4` | false | 是否生成 MP4 预览 |

#### H3 Segment Picker

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `project_name` | H3_LVM | 从哪个库读取 |
| `segment_id` | 1 | 读取第几段 |

### API 接口

| 接口 | 返回 |
|------|------|
| `GET /h3_lvm/projects` | `{"projects": [...], "default": "H3_LVM"}` |
| `GET /h3_lvm/segments?project=<名称>` | 完整片段列表 + 缩略图 URL |

---

### License

MIT
