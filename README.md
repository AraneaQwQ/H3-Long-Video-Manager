# H3 Long Video Manager

> **署名与来源**：本仓库即 [AraneaQwQ/H3-Long-Video-Manager](https://github.com/AraneaQwQ/H3-Long-Video-Manager) 主仓库。ComfyUI V3 迁移、片段删除、Picker 缩放等改动由 [RAFOLIE](https://github.com/RAFOLIE) 开发，已在提交 `0944899`（full RAFOLIE merge）完整合并进本仓库；原项目 MIT 许可证与双方署名均保留，合并记录见 [RAFOLIE_DEVELOPMENT.md](RAFOLIE_DEVELOPMENT.md)。


**安装地址（主仓库）：** https://github.com/AraneaQwQ/H3-Long-Video-Manager

**当前开发版：ComfyUI V3 API + Nodes 2.0。** 迁移范围、运行要求与验证结果见 [V3_MIGRATION.md](V3_MIGRATION.md)。
片段卡片支持垃圾桶删除；删除范围、磁盘存储和缓存行为见 [删除与缓存说明](CACHE_AND_DELETION.md)。
Picker 新增 `segment_id` 输出，用于原片与二采片段对齐比较，见 [SEGMENT_ID_OUTPUT.md](SEGMENT_ID_OUTPUT.md)。
**[English](#english)** | **[简体中文](#简体中文)**

---

## English

> **Seamless 17n+5 video segmenter + local segment bin** for MiniMax H3 long-video workflows.

Cut any long video into H3-compatible segments (each satisfying the `17n + 5` frame rule), save them all to a local library with thumbnails, and retrieve any segment on-demand — no re-loading the source video.

### What it does

| Node | Role |
|------|------|
| **H3 Long Video Manager** | Input: video + audio → all segments saved to bin + selected segment live → `IMAGE`, `AUDIO`, `frame_count`, `total_segments` |
| **H3 Segment Picker** | Input: project name + segment ID → `IMAGE`, `AUDIO`, `frame_count`, `segment_id` (feeds H3 directly) |

### Key features

- **Fixed-length segments** — every full-length segment is exactly the same length: 每段时长 snapped down to a valid H3 count, so 6.0s @ 24fps gives 141 frames = 5.875s for every clip, never 6.6s here and 7.3s there
- **17n+5 grid alignment** — every full-length segment is a valid H3 frame count (no auto-snap surprises)
- **Nothing is lost at the end** — the last segment takes whatever frames are left, Motion Context included, with no rounding at all: no frame is duplicated, no black frame is invented, nothing is dropped. 1962 frames @ 6s/MC22 → 16 clips of 141 frames + one of 58 frames = 1962, exactly
- **The odd tail is H3's problem, not yours** — a tail that is not on the 17n+5 grid is passed to MiniMax H3 as-is; the model decides how to handle it, so no frames of your video silently disappear
- **Motion Context aware** — extraction range includes MC context frames for continuity
- **Local segment bin** — safetensors storage (int8 by default, fp16 on request), thumbnail covers, optional MP4 preview
- **Visual card picker** — click a thumbnail to select a segment, no re-loading video
- **Zero dependency** beyond `torch` + `safetensors` (both already in ComfyUI)

### How it works

```
Long video (e.g. 430 frames @ 24fps)
  │
  ▼
H3 Long Video Manager
  ├── Segments: [0,141) [119,260) [238,379) … [1309,1440)  ← full segments are 141 frames; MC repeats the previous tail; the last one takes the remainder
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
│   ├── seg01.safetensors     # video tensor (int8 or fp16) + audio f32 + metadata
│   ├── seg01_first.png       # thumbnail (card cover)
│   └── seg01.mp4             # optional preview (only if save_preview_mp4=True)
├── seg02/
│   └── ...
```

Disk use is frames × width × height × 3 × bytes-per-value: at 1280×720 that is
5.5 MB per frame in fp16 and 2.8 MB in int8. Motion Context frames are stored
again inside every segment, so a run writes more frames than the source has.

### Node parameters

#### H3 Long Video Manager

| Parameter | Default | Shown on the node | Notes |
|-----------|---------|-----------------|-------|
| `project_name` | H3_LVM | 📦 项目素材库 | Bin folder name. The canvas dropdown is hidden — the panel below the parameters owns the same menu (switch / `＋ 新建项目…` / `🗑 删除当前项目…`) and writes through this field |
| `fps` | 24 | 源视频帧率 | Source video frame rate |
| `segment_duration` | 6.0s | 每段时长（秒） | Fixed length of every full segment, Motion Context included; snapped down to 17n+5, so 6.0s @ 24fps → 141 frames = 5.875s. The last segment takes whatever frames are left and is not snapped |
| `motion_context_frames` | 22 | Motion Context 帧数 | MC context (0/5/22/39/56); the menu shows `22 帧（默认）` and friends |
| `segment_id` | 1 | 输出片段编号 | Which segment to output live |
| `scale_percent` | 100 | 画面缩放 % | Downscale (e.g. 50 = half resolution) |
| `align_to_h3_grid` | true | 对齐 H3 网格 | Enforce 17n+5 for the full-length segments; the last segment is never rounded |
| `save_enabled` | true | 保存到素材库 | Save to bin (disable for pure-live mode) |
| `save_preview_mp4` | false | 生成 MP4 预览 | Also encode MP4 preview |
| `final_align` | down | — (hidden) | Deprecated and ignored. The tail is decided automatically now; the field stays in the schema only so graphs saved before this keep their widget positions |
| `person_crop` | false | 人物裁切 | Detect person and crop edges so the subject fills more of the frame |
| `person_crop_expand_percent` | 0 | 人物框外扩 % | Extra padding around the person box, 0–100. 0 = tight (still keeps source aspect) |
| `save_dtype` | int8 | 素材存盘精度 | `int8` = half the bytes; `fp16` = the original format. The decoder already hands us 8-bit frames, so int8 stores those values exactly and the loaded picture is identical. Segments in one bin may mix formats — the loader reads whatever dtype the file declares |

**Node labels** — the parameters appear on the node in the order the server declares
them, which is the order of the table above. Labels, tooltips, and the
`motion_context_frames` option text are Chinese. All of it is
display-only: field names, stored values, and saved workflows stay English.
`project_name` is still re-declared as a combo in the node definition, which keeps the stored bin
name a valid option, but the widget itself is hidden (`options.hidden`) because the panel above it
draws the same menu — one control per setting. Hidden widgets are still serialised by position, so
graphs saved before this change load unchanged.

**Manager panel** — under the parameters the node has a panel in the same visual language as the
Segment Picker: the 项目素材库 menu on top (switch / create / delete a bin, with the live segment
count), then a tool row (`🔄 刷新`, `🎬 素材库` status, `▾ 展开素材库`), then the card deck. The deck reads
the selected bin and shows every segment in it, ordered by 片段编号 — thumbnail, 片段编号, frame count
and duration, a ▶ button for the MP4 preview, and clicking a card sets 输出片段编号. Segments that this
node's last run produced carry a small `本次` badge, and the status line names them
(`库内 17 段 · 本次生成 6 段（片段 1–6）`). Deleting a card in the Segment Picker removes it here too.
Nothing is saved: the ids come from the `h3_lvm/changed` event the node already sends after saving,
so a page reload simply shows the bin without the badge.

Expanding and collapsing adds or removes exactly the height of one card row, so a node the user
resized keeps its own width and extra space; the node no longer snaps back to its minimum size.

#### H3 Segment Picker

| Parameter | Default | Notes |
|-----------|---------|-------|
| `project_name` | H3_LVM | Which bin to read from. The panel shows a menu instead: every bin on disk is listed with its segment count, `＋ 新建项目…` creates an empty one, and `🗑 删除当前项目…` removes the whole bin after a confirm that repeats its name |
| `segment_id` | 1 | Which segment to load |

**Panel layout** — three rows, top to bottom: ① a labelled project menu with the live
segment count of the selected bin (`＋ 新建项目…` and `🗑 删除当前项目…` live inside that menu),
② a tool row (refresh, card size, current selection), ③ the card deck, then a one-line
legend. Card titles and status text are Chinese; the node parameter labels are shown in
Chinese too (`label` is display-only — saved workflows keep `project_name` / `segment_id`).

### API endpoints

| Endpoint | Returns |
|----------|---------|
| `GET /h3_lvm/projects` | `{"projects": [{"name": ..., "segments": N}, ...], "default": "H3_LVM"}` — every bin with its segment count |
| `POST /h3_lvm/project` | body `{"project": <typed name>}` → `{"name": <sanitized>, "created": true/false, "segments": N}` |
| `POST /h3_lvm/project/delete` | body `{"project": <name>, "confirm": <same name>}` → `{"name": ..., "deleted": true, "segments": N}` |
| `GET /h3_lvm/segments?project=<name>` | Full segment list with thumbnail URLs |
| `POST /h3_lvm/delete` | body `{"project": <name>, "segment_id": N}` → `{"deleted": N}` |

**WebSocket event** — `h3_lvm/changed` is broadcast after a run saves segments
(`{"project": <name>, "segments": [1, 2, ...]}`) and after a delete
(`{"project": <name>, "deleted_id": N}`). The `segments` list is what lets a Manager node show
exactly the cards from its own run instead of guessing from the bin contents.

### Project structure

```
H3-Long-Video-Manager/
├── archive/                       # Pre-change snapshots (date + commit short hash)
├── README.md                      # This file (EN + zh)
├── PROJECT_SPEC.md                # Original spec + current phase status
├── VERSION.md                     # Version notes + archive/ index
├── RAFOLIE_DEVELOPMENT.md         # Attribution & change record
├── CACHE_AND_DELETION.md          # Deletion scope, storage, cache behaviour
├── V3_MIGRATION.md                # ComfyUI V3 / Nodes 2.0 migration notes
├── SEGMENT_ID_OUTPUT.md           # segment_id: original vs re-gen alignment
├── __init__.py                    # Entry: ComfyExtension + routes + web
├── comfyui/
│   ├── __init__.py                    # Plugin package (nodes loaded by root extension)
│   ├── nodes.py                       # Manager (V3) + Picker nodes
│   ├── nodes_v1.py                    # backup (pre-audio)
│   ├── nodes_v2.py                    # backup (pre-save-bin)
│   ├── nodes_v3_backup.py             # backup (pre-V3-API)
│   ├── nodes_v4_backup.py             # backup (pre-V3-API, v4 attempt)
│   ├── asset_paths.py                 # Asset path checks + versioned preview URLs
│   ├── segment_store.py               # Storage layer (save/load/list/delete)
│   └── server_api.py                  # HTTP API routes
├── core/
│   ├── __init__.py                    # Layer A public API (dataclasses)
│   ├── models.py                      # Dataclasses (Segment, Manifest, etc.)
│   ├── models_v3_backup.py            # backup
│   ├── h3_grid.py                     # 17n+5 alignment + fixed-length segmentation
│   ├── h3_grid_v4_backup.py           # backup
│   ├── manifest.py                    # build_manifest()
│   ├── manifest_v4_backup.py          # backup
│   ├── segmentation.py                # Duration → frames computation
│   ├── person_crop.py                 # Person detection + edge crop
│   └── extraction.py                  # Frame range extraction (PyAV)
├── web/
│   ├── h3lvm_picker.js                # Card gallery frontend
│   ├── h3lvm_picker.css               # Styling
│   ├── h3lvm_manager.js               # Chinese labels, hides the canvas project combo
│   ├── h3lvm_manager_panel.js           # Manager panel (project menu + this run's cards)
│   ├── project_menu.js                  # Project switch/create/delete row (both panels)
│   ├── preview_overlay.js               # MP4 preview modal (Picker + Manager)
│   ├── delete_button.js               # Segment card delete button
│   ├── dom_panel.js                   # DOM widget sizing (Canvas + Nodes 2.0)
│   └── extension.js                   # (placeholder, intentionally empty)
└── tests/
    ├── __init__.py
    ├── test_core.py                   # Core regression tests
    ├── test_frame_integrity.py        # No-frame-loss tests
    ├── test_h3_grid.py                # 17n+5 grid tests
    ├── test_node_schema.py            # Node output order lock
    ├── test_person_crop.py            # Person crop tests
    ├── test_fixed_segments.py           # Fixed-length segmentation tests
    ├── test_project_menu.py           # Project menu (list/create/delete) tests
    └── test_segment_store.py          # Storage round-trip tests
```

---
---

## 简体中文

> **MiniMax H3 长视频工作流的无缝分段器 + 本地片段库。**

将任意长视频按 **17n+5** 帧规则裁切为 H3 兼容片段，全部保存到本地库（含缩略图），后续无需重新载入源视频即可随时取用任何一段。

### 功能

| 节点 | 作用 |
|------|------|
| **H3 Long Video Manager** | 接入视频 → 分段 → 全部存库 → 实时输出选中段 → 输出 `IMAGE`、`AUDIO`、`frame_count`、`total_segments` |
| **H3 Segment Picker** | 从库中读取 → 输出 `IMAGE`、`AUDIO`、`frame_count`、`segment_id`（前两项直接喂 H3） |

### 核心特性

- **定长分段** — 每个整段长度完全一致：每段时长向下吸附到合法 H3 帧数，6.0s @ 24fps 就是每段 141 帧 = 5.875s，不会再出现一段 6.6s、一段 7.3s
- **17n+5 网格对齐** — 每个整段都是合法 H3 帧数，不会自动 snap 导致时长偏移
- **结尾一帧都不丢** — 最后一段直接吃掉剩下的全部帧（含 Motion Context 重叠帧），完全不做对齐：不重复任何帧、不补黑帧、也不丢任何帧。1962 帧 @ 6s/MC22 → 16 段 141 帧 + 1 段 58 帧 = 1962，正好
- **末尾的零头交给 H3 判断** — 最后一段的帧数不在 17n+5 上，也原样交给 MiniMax H3，由模型自己处理，你的视频不会悄悄少几帧
- **Motion Context 感知** — 提取范围包含 MC 上下文帧，保证接续连贯
- **本地片段库** — safetensors 存储（默认 int8，可切 fp16）+ 首帧缩略图 + 可选 MP4 预览
- **视觉卡片选择** — 点击缩略图选段，无需重新加载视频
- **零额外依赖** — 仅需 `torch` + `safetensors`（ComfyUI 自带）

### 工作流程

```
长视频 (如 430帧 @ 24fps)
  │
  ▼
H3 Long Video Manager
  ├── 分段: [0,141) [119,260) [238,379) …  ← 每个完整段都是 141 帧；正文不重复，MC 与上一段尾部重叠
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
│   ├── seg01.safetensors     # 视频张量（int8 或 fp16）+ 音频f32 + 元数据
│   ├── seg01_first.png       # 缩略图（卡片封面）
│   └── seg01.mp4             # 可选预览（需开启 save_preview_mp4）
├── seg02/
│   └── ...
```

占用空间 = 帧数 × 宽 × 高 × 3 × 每个值的字节数：1280×720 下 fp16 每帧约 5.5 MB，int8 约 2.8 MB。
Motion Context 的重叠帧会在每一段里再存一份，所以一次运行写出的帧数会比源视频多。

### 节点参数

#### H3 Long Video Manager

| 参数 | 默认值 | 节点上显示为 | 说明 |
|------|--------|--------------|------|
| `project_name` | H3_LVM | 📦 项目素材库 | 库文件夹名。节点上的下拉框已隐藏——参数下面的面板里有同一个菜单（切换 / `＋ 新建项目…` / `🗑 删除当前项目…`），直接写这个字段 |
| `fps` | 24 | 源视频帧率 | 源视频帧率（H3 生成的视频一般是 24） |
| `segment_duration` | 6.0s | 每段时长（秒） | 每个整段的固定长度，已包含 Motion Context 重叠帧；向下吸附到 17n+5，因此 6.0s @ 24fps → 141 帧 = 5.875s。最后一段取剩余全部帧，不做吸附 |
| `motion_context_frames` | 22 | Motion Context 帧数 | MC 上下文（0/5/22/39/56），菜单里显示为 `22 帧（默认）` 等 |
| `segment_id` | 1 | 输出片段编号 | 实时输出哪一段 |
| `scale_percent` | 100 | 画面缩放 % | 缩放比例（50 = 一半分辨率） |
| `align_to_h3_grid` | true | 对齐 H3 网格 | 是否对整段对齐 17n+5；最后一段永远不做对齐 |
| `save_enabled` | true | 保存到素材库 | 是否存库（关 = 纯实时模式） |
| `save_preview_mp4` | false | 生成 MP4 预览 | 是否生成 MP4 预览 |
| `final_align` | down | —（已隐藏） | 已废弃，值被忽略。末段现在自动处理；这个字段留在 schema 里只是为了让改动前保存的工作流参数不错位 |
| `person_crop` | false | 人物裁切 | 开启后检测人物并裁掉边缘，让主体占画面更大 |
| `person_crop_expand_percent` | 0 | 人物框外扩 % | 人物框外扩百分比（0–100）。0 = 紧贴检测框，仍保持原画面比例 |
| `save_dtype` | int8 | 素材存盘精度 | `int8` = 体积只有原来的一半；`fp16` = 原来的格式。解码器交给我们本来就是 8-bit 帧，所以 int8 存的是同一批数值，读回来的画面完全一致。同一个库里可以混用两种精度，读取时按文件自己的类型还原 |

**节点上的显示** — 参数在节点上的顺序与服务端声明一致，也就是上表的顺序。参数名、悬停说明和
`motion_context_frames` 的选项文字全部中文。这些都只影响显示：字段名、保存的值
和工作流文件仍然是英文。`project_name` 仍然在节点类型注册前被声明为 combo（保证工作流里存的库名始终是合法选项），
但 widget 本身被隐藏（`options.hidden`），因为面板顶部已经有同一个菜单——一个设置只留一个控件。隐藏的 widget
仍按位置序列化，所以改动前保存的工作流打开后参数不会错位。

**Manager 面板** — 参数下面是与 H3 Segment Picker 同一套视觉的面板：顶部是项目素材库菜单（切换 / 新建 / 删除项目，右侧实时显示片段数），接着是工具行（`🔄 刷新`、`🎬 素材库` 状态、`▾ 展开素材库`），再下面是卡片网格。卡片区读的是当前选中的素材库，按片段编号顺序显示库内**全部**片段：缩略图、片段编号、帧数和时长，带 ▶ 按钮播放 MP4 预览，点卡片就是把该段设为「输出片段编号」。本节点上一次运行产出的片段带一个 `本次` 小标记，状态行会写清楚（`库内 17 段 · 本次生成 6 段（片段 1–6）`）。在 Segment Picker 里删除片段，这里同步消失。这里不保存任何状态：本次编号来自节点保存后本来就会发的 `h3_lvm/changed` 事件，刷新页面后只剩素材库本身、没有标记。

展开 / 收起只增减一行卡片的高度，用户自己拉过的宽高会保留，节点不会再缩回最小尺寸。

#### H3 Segment Picker

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `project_name` | H3_LVM | 从哪个库读取。面板上是一个下拉菜单：列出磁盘上所有库并带片段数量，`＋ 新建项目…` 建一个空库，`🗑 删除当前项目…` 在确认行里重复库名后删除整个库 |
| `segment_id` | 1 | 读取第几段 |

**面板布局** — 自上而下三行：① 带标签的项目菜单，右侧实时显示当前库的片段数量（`＋ 新建项目…` 与 `🗑 删除当前项目…` 都在这个菜单里）；② 工具行（刷新、卡片大小、当前选中）；③ 卡片网格，最下方一行操作图例。卡片标题与状态文字全部中文，节点参数名也显示为中文（`label` 只影响显示，保存的工作流仍然是 `project_name` / `segment_id`）。

### API 接口

| 接口 | 返回 |
|------|------|
| `GET /h3_lvm/projects` | `{"projects": [{"name": ..., "segments": N}, ...], "default": "H3_LVM"}` — 所有库 + 片段数量 |
| `POST /h3_lvm/project` | 请求 `{"project": <用户输入的名字>}` → `{"name": <清洗后的名字>, "created": true/false, "segments": N}` |
| `POST /h3_lvm/project/delete` | 请求 `{"project": <库名>, "confirm": <同一个库名>}` → `{"name": ..., "deleted": true, "segments": N}` |
| `GET /h3_lvm/segments?project=<名称>` | 完整片段列表 + 缩略图 URL |
| `POST /h3_lvm/delete` | 请求 `{"project": <库名>, "segment_id": N}` → `{"deleted": N}` |

**WebSocket 事件** — 一次运行保存完片段后（`{"project": <库名>, "segments": [1, 2, ...]}`）和删除片段后（`{"project": <库名>, "deleted_id": N}`）都会广播 `h3_lvm/changed`。`segments` 这个列表就是让 Manager 节点能准确显示自己这次运行的卡片，而不是从整库内容去猜。

---

### License

MIT
