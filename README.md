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
| **H3 Smart Split** | Input: video + audio → PySceneDetect finds the real shot cuts → every shot saved to the SAME bin + selected shot live → `IMAGE`, `AUDIO`, `frame_count`, `total_segments` |

| **H3 Segment Picker** | Input: project name + segment ID → `IMAGE`, `AUDIO`, `frame_count`, `segment_id` (feeds H3 directly) |
| **H3 Guide Timeline** | Input: `positive` + H3 AV latent + both VAEs + one guide list → image/audio guides placed on a two-lane timeline → `positive` (equal to a hand-wired chain of native Add Guide nodes) |

### Key features

- **Fixed-length segments** — every full-length segment is exactly the same length: 每段时长 snapped down to a valid H3 count, so 6.0s @ 24fps gives 141 frames = 5.875s for every clip, never 6.6s here and 7.3s there
- **17n+5 grid alignment** — every full-length segment is a valid H3 frame count (no auto-snap surprises)
- **Nothing is lost at the end** — the last segment takes whatever frames are left, Motion Context included, with no rounding at all: no frame is duplicated, no black frame is invented, nothing is dropped. 1962 frames @ 6s/MC22 → 16 clips of 141 frames + one of 58 frames = 1962, exactly
- **The odd tail is H3's problem, not yours** — a tail that is not on the 17n+5 grid is passed to MiniMax H3 as-is; the model decides how to handle it, so no frames of your video silently disappear
- **Or cut on real shots** — `H3 Smart Split` is a second producer for the same bin: PySceneDetect finds the actual shot boundaries in the connected video and every main range is stored exactly as detected. No 17n+5 snapping, no padding, no dropped or duplicated frame; the last shot is whatever length it is
- **Motion Context is optional there** — Smart Split defaults to 0 and only widens the extraction range, it never moves a detected cut

- **Motion Context aware** — extraction range includes MC context frames for continuity
- **Local segment bin** — safetensors storage (int8 by default, fp16 on request), thumbnail covers, optional MP4 preview
- **Visual card picker** — click a thumbnail to select a segment, no re-loading video
- **Portrait frames shown whole** — a 9:16 thumbnail is displayed in full inside the same card: the side space is filled with a blurred copy of the frame instead of black bars. Landscape frames keep filling the box as before, and the card size is identical either way
- **The deck is always open** — the Manager node keeps its card grid visible, and reopening a workflow shows the cards by itself: no expand button, no 刷新 to click
- **No extra dependency for the fixed-length path** — `torch` + `safetensors` only (both already in ComfyUI). Smart Split additionally uses `scenedetect>=0.6.4,<0.8`; if that package is missing the plugin still loads and only Smart Split prints the exact pip command to run
- **One node instead of an Add Guide chain** - `H3 Guide Timeline` keeps one guide list and calls the native node once per guide in frame order: same conditioning structure, same frame positions, no four-node wiring
- **Two-lane timeline editor** - real thumbnails, real waveforms, drag a marker or clip frame by frame, audition only the trimmed range, and every conflict is a clickable line in the footer


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
  ▼  (or skip the Manager and let the footage decide where the cuts are)
H3 Smart Split
  ├── Detect on the connected tensor: real shot cuts → [0,214) [214,505) [505,960)
  ├── Saves all → the SAME bin, the same cards, the same Picker
  └── Outputs selected segment live (IMAGE + AUDIO)
  │
  ▼  (later, without re-loading video — either producer, same bin)
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
>
> **Optional**: `scenedetect>=0.6.4,<0.8`, used by `H3 Smart Split` only:
>
> ```bash
> "<path to the Python that runs ComfyUI>" -m pip install "scenedetect>=0.6.4,<0.8"
> ```
>
> Without it the Manager, the Picker and the segment bin behave exactly as before; Smart
> Split stops with an error that prints the same command for the running interpreter.>
> **Uploaded videos need PyAV**: the Picker's **投放视频** (uploaded video) library decodes
> with `av`, the same FFmpeg-inside-Python the Manager already uses, so no `ffmpeg` on
> `PATH` is needed. It is not pinned in `requirements.txt` because a normal ComfyUI
> install already ships it; if it is missing, the cut-bin mode keeps working and the
> upload mode stops with an error that prints `pip install av`.


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

ComfyUI/output/h3-lvm-video-uploads/<project_name>/   # the Picker's 投放视频 library (its own root, never inside h3-lvm)
├── h3lvm_upload_index.json   # cards: original filename, duration, size, fps, audio flag
└── files/
    ├── vid001.mp4            # the user's file, byte for byte — never re-encoded or trimmed
    └── vid001_cover.jpg      # card cover (320 px max edge)

ComfyUI/output/h3-lvm-image-refs/<project_name>/h3lvm_references.json   # image reference preset
ComfyUI/output/h3-lvm-audio-refs/<project_name>/h3lvm_references.json   # audio reference preset
```

Disk use is frames × width × height × 3 × bytes-per-value: at 1280×720 that is
5.5 MB per frame in fp16 and 2.8 MB in int8. Motion Context frames are stored
again inside every segment, so a run writes more frames than the source has.
The upload library is different on purpose: one original file per card and nothing else.
Importing never writes a `.safetensors` and never keeps a decoded video in memory — the
bytes are decoded when the node runs, one card at a time.

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
count), then a tool row (`🔄 刷新`, `🔗 合并模式`, `卡片大小` 100%–400%, `🎬 素材库` status), then the card deck. The deck is always open — there is
no collapse button. It reads the selected bin and shows every segment in it, ordered by 片段编号 — thumbnail, 片段编号, frame count
and duration, a ▶ button for the MP4 preview, and clicking a card sets 输出片段编号. Segments that this
node's last run produced carry a small `本次` badge, and the status line names them
(`库内 17 段 · 本次生成 6 段（片段 1–6）`). Deleting a card in the Segment Picker removes it here too.
Nothing is saved: the ids come from the `h3_lvm/changed` event the node already sends after saving,
so a page reload simply shows the bin without the badge.
Thumbnails follow the frame orientation: landscape fills the box (`object-fit: cover`), portrait (9:16) is
shown whole (`object-fit: contain`) with a blurred copy of the same frame behind it, so a vertical video is
never cropped to a thin strip. The thumbnail box — and therefore the card — is the same size in both cases.

**Card size** — both panels use the same control (`web/card_zoom.js`): `−` / `+` step through
100% / 150% / 200% / 300% / 400%, the ends disable themselves instead of wrapping around, and the deck
scrolls inside the panel. Only the CSS variables `--card-min` and `--thumb-h` change, so the node keeps
whatever size the user gave it.

**Merge mode** — automatic splitting sometimes cuts one shot into several tiny pieces, so both decks
carry a `🔗 合并模式` button in the tool row, on the same row and at the same height as
`🔄 刷新`. Turning it on makes cards selectable: click two or more **adjacent** cards (clicking a
non-adjacent one restarts the selection), they get an `已选` badge, and `✅ 确认合并` appears in
the same row. The merge joins those segments into one card that keeps the **smallest** id of the
selection, and every later segment shifts down by the number of removed cards, so the bin stays
numbered 1..N with no holes — which is what 输出片段编号 reads. Joining drops the Motion Context
overlap at every seam (the head frames of each segment after the first, plus the matching audio
head), so the joined clip neither replays frames nor drifts off the picture; audio survives only
when every part has it. Frames are concatenated in the stored packed format (int8/fp16), so a long
merge does not need an extra float32 copy. Mixed frame rate or resolution in one selection is
refused with a Chinese error. Merge mode is a UI state, not a saved field: reloading the page
leaves it off.

The deck belongs to the bin, not to the page visit: reopening a workflow paints the cards by itself,
because the panel repaints once the saved 项目素材库 name is restored — no 刷新 click needed. The panel
height is also the widget's minimum height, so ComfyUI grows any node too short to show a card row and
keeps the width the user chose.

#### H3 Smart Split

| Parameter | Default | Shown on the node | Notes |
|-----------|---------|-----------------|-------|
| `project_name` | H3_LVM | 📦 项目素材库 | The same bin as the Manager. The canvas dropdown is hidden; the panel menu (switch / create / delete) writes through this field |
| `fps` | 24 | 源视频帧率 | Source frame rate. Detection runs on the connected tensor, so this is also the frame → time scale |
| `detection_sensitivity` | medium | 镜头切点灵敏度 | `low` = 4.5, `medium` = 3.0, `high` = 2.0 for `AdaptiveDetector.adaptive_threshold` — the same three values the reference Director uses. It only decides where the cut lands |
| `motion_context_frames` | 0 | Motion Context 帧数 | 0/5/22/39/56. Widens the extraction range only, never moves a cut. Default 0 because a real shot boundary is not a seam that needs hiding |
| `segment_id` | 1 | 输出片段编号 | Which shot to output live (1 = first shot) |
| `scale_percent` | 100 | 画面缩放 % | Downscale |
| `save_enabled` | true | 保存到素材库 | Save to bin (disable for pure-live mode) |
| `save_preview_mp4` | false | 生成 MP4 预览 | Also encode MP4 preview |
| `save_dtype` | int8 | 素材存盘精度 | The same switch as the Manager |

There is deliberately **no** `segment_duration`, `align_to_h3_grid`, `final_align` or
`person_crop*` on this node: a shot boundary is not a duration, and the node must not be
able to change frame counts behind your back. The output shape is identical to the Manager,
so the existing H3 Segment Picker reads either producer unchanged.

**Panel** — the same 项目素材库 menu as the other two nodes (switch / create / delete, with
the live segment count), then the same card deck as the Manager: every segment in the bin in
segment order, the ones from this node's last run marked `本次`, card zoom 100%–400%, and
click-a-card to set 输出片段编号. The deck code is shared (`web/deck_panel.js`), so the two
panels cannot drift apart, and a bin written by one producer shows the same cards in the
other. Cut frames and the per-shot ranges are printed to the console as a `SEGMENT TABLE`.
Merge mode (`🔗 合并模式`, described with the Manager panel) is the intended fix when the
detector cuts one shot into several tiny pieces.


#### H3 Segment Picker

One node, two libraries, the same four outputs. Two buttons above the project menu pick
which library the node reads; the switch is explicit and nothing is guessed from what
happens to be on disk.

| Parameter | Default | Notes |
|-----------|---------|-------|
| `project_name` | H3_LVM | Which project to read — inside the library the current mode button points at. The panel shows a menu instead: every project of **that** library with its count, `＋ 新建项目…` creates an empty one, and `🗑 删除当前项目…` removes the whole project after a confirm that repeats its name |
| `segment_id` | 1 | Which segment / card to load |
| `source_mode` | `segments` | `segments` = 裁切片段 (the cut bin written by Manager / Smart Split), `uploads` = 投放视频 (whole videos brought into this node). Appended after the two old fields on purpose: a workflow saved before this field existed keeps its two values and keeps reading the cut bin |
| `output_size` | `原始（不缩放）` | 投放视频 only — caps the long side of the frames this node decodes: `原始（不缩放）` / `最长边 3840` / `1920` / `1280` / `960` / `640` / `480` / `自定义（自己填最长边）`. Proportional, even-aligned, never upscaled, and the stored file is never transcoded, so changing it costs a decode and nothing else. A 4K frame is 8 MB of float32 and the H3 encoder downscales anyway, so 1920 or 1280 is the sane choice for 4K/2K material. Appended after `source_mode` for the same reason as that field: a workflow saved before it existed keeps its three values and decodes at the original size. 裁切片段 never uses it |
| `custom_max_side` | 1920 | Read only when `output_size` is `自定义（自己填最长边）` — the long side in pixels, 16–8192. A typed number is clamped into that range rather than rejected, because a typed number is an intention; `scale_plan()` never grows a picture, so a cap above the source simply means no scaling. Ignored while a preset is selected. Appended after `output_size` for the same restore-by-position reason |

**Mode 1 · 裁切片段 (default, unchanged)** — reads the `.safetensors` bundle the Manager or
Smart Split saved. Nothing is decoded again, and the four outputs are exactly what they
were before this feature.

**Mode 2 · 投放视频** — whole videos the user dropped into the node, stored as their own
files under a separate root. Importing does not run the workflow and does not create a
tensor: the file is kept byte for byte, probed for duration / size / fps / audio, and
given a card cover. Only the selected card is decoded, and only when the workflow runs —
frames are sampled to 24 fps (the H3 convention), audio is resampled to 44.1 kHz, and a
clip without a sound track gets silent AUDIO of the matching length so downstream H3
nodes never receive `None`. No trimming, no black-frame padding, no 17n+5 snapping:
whatever the file is, that is what H3 judges. Limits: `.mp4 .m4v .mov .mkv .webm .avi
`.ts .mts`, 2 GiB per file, 999 cards per project.

**Output size is a decode-time cap, never a transcode** — `输出分辨率` caps the long side while
frames are being decoded, which is what keeps a 4K upload from costing 8 MB of RAM per frame
and from being refused by the memory guard (the estimate now uses the planned output size, and
the Chinese error names the control). The plan is proportional, snapped to even numbers, and
never upscales; the file on disk stays byte for byte, so switching back to `原始（不缩放）` loses
nothing. The card list is planned with the same `scale_plan()` on the server, so a card
advertises what a run will really produce — `源 3840×2160 → 输出 1920×1080（原文件不变）` — and in
裁切片段 mode the widget label says `输出分辨率（裁切不用）` instead of hiding a control. The option
list lives in `comfyui/video_decode.py::RESIZE_OPTIONS` so the widget, the cards and the tests
cannot disagree about what is offered. The last entry, `自定义（自己填最长边）`, carries no number
in its label and reads `custom_max_side` instead; the panel labels that field `（生效中）` when the
combo points at it and `（选自定义后可用）` otherwise, so it is always clear whether a typed
number is live — and it is never hidden, because a control that appears and disappears reads
as broken and makes the node body jump.

**The numbers are the card order** — cards in the upload library can be dragged into a new
order: where a card is dropped decides the order, the first card is `segment_id 1`, and the
rest follow. Import and delete follow the same rule: a new video is appended at the end, and
deleting a card moves the later ones up, so a library is always numbered 1..N with no holes.
That is the number the panel shows and the number 输出片段编号 reads. After a delete the
panel follows the selection to its new number and says so
(`当前选中：视频 2（后面的编号已顺延）`). Renumbering rewrites the index only; the video
files and covers stay where they are because every read goes through the record, so neither
a drag nor a delete moves bytes. Files keep the opaque name they were given at import —
`next_id` in the index is that storage counter and never hands a name out twice — so a
number freed by a delete can never overwrite another card's file. A `segment_id` saved in a
workflow therefore means "which position in the order", not "which upload came first",
which is what stitching several clips into one long video needs. The cut-segment deck stays
numbered as Manager / Smart Split saved it and is not draggable.

**Panel layout** — four rows, top to bottom: ① the two mode buttons (`🎬 裁切片段` /
`📥 投放视频`), ② a labelled project menu with the live count of the current library
(`＋ 新建项目…` and `🗑 删除当前项目…` live inside that menu), ③ a tool row (refresh, card
size 100%–400%, current selection, plus `＋ 载入视频` in upload mode), ④ the card deck,
then a one-line legend. Card titles and status text are Chinese; the node parameter
labels are shown in Chinese too (`label` is display-only — saved workflows keep
`project_name` / `segment_id` / `source_mode` / `output_size` / `custom_max_side`).

**Two selections, both restored** — each mode keeps its own project + card in
`node.properties["h3lvm_picker_modes"]`, so saving the workflow, reopening it, or
restarting ComfyUI brings back what was selected in each mode; the graph is the source
of truth on load, so a workflow saved before this feature still opens in 裁切片段.
Dropping files on the deck uploads them (ComfyUI's automatic `LoadImage` node is
suppressed for video files). An upload card shows the cover, the original filename,
duration, resolution, source fps with a 输出按 24fps 采样 note when it differs, and
whether it has audio; a card whose file was deleted outside ComfyUI stays visible with a
文件已丢失 badge instead of vanishing. ▶ previews in the browser when the container is
playable there (`.mkv` / `.avi` say why they are not), 🗑 deletes that card and its file.

Thumbnails keep the shared card rules: landscape fills the frame (`object-fit: cover`),
portrait (9:16) shows the whole frame (`object-fit: contain`) over a blurred copy of the
same frame, and the card size is identical either way. Card zoom 100%–400% is the same
control as on the Manager and Smart Split panels.


#### H3 Image Reference Loader / H3 Audio Reference Loader

These two nodes feed the reference ports of the official `MiniMaxH3ReferenceToVideo`
(`ref_image_0..8`, `ref_audio_0..2`) without a wall of `LoadImage` / `LoadAudio` nodes plus
resize nodes. Card order **is** slot order, and an unused slot outputs a real `None`, which
the H3 node skips (`if img is None: continue`).

| Parameter | Default | Shown on the node | Notes |
|-----------|---------|-----------------|-------|
| `media_files` | `[]` | 🎞 参考素材列表 | JSON list written by the card panel: `[{"filename", "subfolder", "type"}, ...]`; an audio entry may also carry `"start"` / `"duration"` in seconds, which is that card's trim window. A plain list of file names also works for hand-written API prompts. The widget is hidden once the panel is running (`options.hidden`); the value is still serialised by position. A parked card carries `"skip": true` and is never read by the node |
| `target_megapixels` | 0.25 | 🎯 目标像素量 (MP) | Per-image target in megapixels (0.02–8.0). Every image keeps its own aspect ratio and is snapped to the 32 px H3 grid; changing the value re-plans every card at once |
| `project_name` | `H3_LVM` | 📦 项目素材库 | Which project bin `📥 载入项目预设` / `📤 存为项目预设` read and write. Appended last on purpose — `configure()` restores widget values by position — and it is never part of the cache key and never changes a pixel. Hidden once the panel's project menu is running, exactly like `media_files` |
| `resampling_method` | `Lanczos` | 🔍 重采样算法 | `Lanczos` / `Bicubic` / `Bilinear` / `Nearest`, mapped straight onto PIL's filters — the option list, the backend and the tests read the same tuple, so the UI can never promise a filter the node does not use. `Lanczos` is the best downscaler; `Nearest` keeps hard edges for pixel art. Changing it re-decodes the images (it is part of the cache key) but never changes the output size |
| `upscale_small_images` | false | ↕ 放大小图至目标 MP | Off: only images above the target area are scaled down, a smaller image is only nudged onto the 32 grid and its card says `（未放大，仅对齐网格）`. On: every image is scaled to the target area. Off by default — upscaling invents detail the source does not have and costs encoder time |

**Outputs** — `ref_image_0 … ref_image_8` (`IMAGE`, batch size 1) and `ref_audio_0 …
ref_audio_2` (`AUDIO`). Always nine / three ports, in that order.

**Image sizing** — `core/ref_size.py` is the single implementation: proportional scaling
onto the 32 px grid, never a crop and never a pad. `plan_reference()` chooses the mode:
`target_mp` scales to the target area (anything above it, or anything at all when
`upscale_small_images` is on), `grid_align` only moves each axis by at most one grid step
and returns an already-legal source unchanged, which is how the node knows to skip
resampling it. Both modes build candidates from the ideal size, the area match and the ratio
match, then a deterministic tie-break picks one. Worst case in the tested range
(target ≥ 0.25 MP, source ratio ≤ 3:1) is 8.95% area error and 3.57% ratio error; a
480×640 source at 0.25 MP deliberately trades a little ratio to hit the requested area.
"Upscaling off" is not "the pixel count never changes": 300×200 becomes 320×192 because the
32 px grid requires it, and the card says `（未放大，仅对齐网格）` so it does not read as a
bug. The card shows `source → output · actual MP`, and that number comes from
`GET /h3_lvm/ref_plan` — the same planner the node runs, not a JavaScript copy of it. EXIF
orientation is applied, alpha is dropped (like `LoadImage`), an animated source contributes
its first frame, and a source over 40 MP is refused with a readable error.

**Audio** — the one thing the loader changes is where a clip starts and how long it is: every
audio card has `开始` / `时长` inputs in seconds, stored on the entry as `"start"` /
`"duration"`, so a cut survives a save, a reload and a project preset. The rules are
ComfyUI's own `TrimAudioDuration`: a negative start counts back from the end of the file, a
duration of 0 runs to the end, and both ends are clamped into the file — only a window with no
samples in it is an error, and it says so in Chinese. Everything else is passed through as-is:
no resample, no remix. H3 resamples inside `_encode_ref_audio` for its audio VAE, so the
loader keeps the original sample rate and channel count. Decoding uses ComfyUI's own
`comfy_extras.nodes_audio.load`, the same decoder `LoadAudio` uses.

**Panel** — the same visual language as the deck panels: a tool row (`🔄 刷新`,
`卡片大小` 100%–400%, slot status `已用 3/9（ref_image_0..ref_image_2） · 空槽输出 None`), an
`＋ 添加参考图` / `＋ 添加参考音频` button, drag & drop onto the grid, and one card per slot
with the thumbnail (portrait shown whole, same card size) or — for an audio card — a waveform
drawn in the same thumbnail box (blue bars are what H3 receives, grey bars are not; `▶`
previews only that window and clicking the waveform seeks inside it) plus a `开始` / `时长`
row in seconds and `↺` to clear the cut, the port it feeds (`参考图 3 → ref_image_2` — the number on the card is 1-based for humans, the port name is not), the real output size, and `↻ 替换` / `⊘ 跳过` / `✕ 移除` buttons (a parked card carries `↩ 放回` / `✕ 移除` instead). Dragging a card anywhere in the panel reorders the slots — the card order *is* the slot order. The
landing spot is the nearest card, so gaps between cards and the space below the last row are
usable targets, and the grid scrolls while the pointer is held near its top or bottom edge. The panel
height is fixed, so nothing on it can resize the node. Files go through ComfyUI's
`/upload/image` into the `input` folder; the list only ever stores relative paths, and
replacing a file on disk re-decodes it, because the cache key includes size + mtime.

**Parked cards (`⊘ 跳过`)** — a card that must stay in the workflow but should not be sent
to H3 this run is parked instead of deleted: it moves to a second block at the back of the
deck, dimmed, labelled `⊘ 已跳过 · 不占槽位`, and is not draggable. The numbered ports come
from the slot block only, so parking card 2 closes the gap (cards 3… become 2…), while the
parked file stays in `media_files` with `"skip": true` — `↩ 放回` puts it back at the end of
the slot order without re-uploading, and `↺ 全部放回` (only shown while something is parked)
brings back everything that fits. Parked cards never count against the 9/3 slot limit and are
not part of the cache key, because the node never reads them.

**Project reference presets** — a story reuses the same characters and scenes over and over, so the panel can keep the
current card list as the preset of a project bin and put it back into any node of the same kind: `📤 存为项目预设` writes
`<output>/h3-lvm-image-refs/<project>/h3lvm_references.json` (the audio loader writes its own
`<output>/h3-lvm-audio-refs/<project>/h3lvm_references.json`), `📥 载入项目预设` puts that bin's cards back. A preset stores
**paths only** — the same `{filename, subfolder, type}` a card already holds — so it costs a few hundred bytes however
big the media is, and nothing is copied, re-uploaded, or duplicated. What it stores is the **arrangement**, not a bag
of files: the order of the slot cards (that order is the order of the `ref_image_` ports) and which cards were parked
are saved and restored. Images and audios live in **separate libraries** — one root, one project list, and one list
file per kind — because a reference image and a reference audio are different material for different ports: the audio
loader never offers the image loader's bins, and a bin named for a story cannot look like it holds both. A preset saved
before that split is copied out of the old shared file once, into its own kind's library, and the old file is left
where it is. The slot limit still applies on the way back, and cards the panel holds that the preset does not mention
are **removed** — a preset *is* the reference set of a project, so keeping the leftovers beside it means the next run
quietly carries references the user had already decided against; adding a card back is a normal add, and loading the
same preset twice still changes nothing. The first row of the panel is the shared `📦 项目素材库` menu
(switch / `＋ 新建项目…` / `🗑 删除当前项目…`), and on these two nodes it lists that kind's own library and counts
**reference cards** — `项目名 (4 张)`, `共 4 张参考`, `无预设` — because a reference-only bin holds no saved segments and used
to read `（空）` forever; the Picker and the Manager still count segments. Creating or deleting a project there touches
that kind only: deleting a story's voice presets keeps its character images. The status line says what the bin holds
(`项目预设 4（含 1 张已跳过）`), and 载入 is disabled while it is empty. A missing or half-written preset reads as empty
instead of breaking the panel, and switching project re-reads it.

**Defaults vs. the official node** — the official `ref_image_size` is `match`/`max`
(short side ≤ 2048, ≈ 3.2 MP for a 16:9 frame), while a `LoadImage` + resize chain with a
512 long edge lands near 0.15 MP. These nodes default to 0.25 MP; set `target_megapixels`
to about 3.2 to match the official default.
#### H3 Guide Timeline

One node instead of a chain of native `MiniMaxH3AddGuide` nodes. The native node anchors exactly
one image or one audio per node, so three pose images plus one voice line is four nodes wired by
hand and the frame numbers only exist inside each widget. This node keeps the native semantics and
replaces the chain with one list: wire `positive`, the MiniMax H3 AV latent and both VAEs once, then
place guides on a two-lane timeline.

| Parameter | Default | Shown as | Description |
|-----------|---------|----------|-------------|
| `positive` | - | positive | The conditioning to guide. Returned unchanged when nothing is both enabled and placed |
| `latent` | - | latent | The MiniMax H3 AV latent. The real total frame count comes from it (the `1+4+4+4+4...` token grid), and the editor ruler uses that number |
| `length_seconds` | 0.0 | ⏱ 视频时长（秒） | Ruler only, and in seconds like `segment_duration` elsewhere in this plugin: the panel converts it with `round(seconds × 24)` and aligns up to 17n+5, then says the arithmetic out loud (10 秒 → 240 → 243 帧). 0 means not set. It never changes execution or the output |
| `vae` | optional | vae | Video VAE. Required when at least one enabled+placed image guide exists; may stay empty otherwise |
| `audio_vae` | optional | audio_vae | Audio VAE. Required when at least one enabled+placed audio guide exists |
| `guides` | `{"schema_version":1,"fps":24,"guides":[]}` | 🎬 Guide 列表 (JSON) | The whole document the panel reads and writes: the guide list plus `view_state` and `resolved_frame_count`. Written by the editor, editable by hand |

**Output** - one `positive` (Conditioning). There is no `ref_images` / `ref_audios` output: a guide is
a time anchor, not a reference slot - that is what the two loader nodes are for.

**Run time** - parse the list -> drop disabled and unplaced items -> if nothing is left, pass
`positive` through unchanged -> read the real frame count from the latent -> validate everything
*before* encoding anything -> sort by `(frame_index, image before audio, original list order)` -> call
the native `MiniMaxH3AddGuide.execute` once per guide, each result feeding the next -> return the last
`positive`. That is exactly a hand-wired chain: the native node appends keyframe entries in call order
and `PackedLayout` packs them in list order, so sorting by frame before encoding is what makes
"same guides, same frames" equal. Two VAEs are always connected on purpose - there is no lazy loading,
but the audio encoder is not called when no audio guide runs, and the video encoder not when no image
guide runs.

**Rules** - one table of rules lives in `core/guide_timeline.py` and is mirrored by
`web/guide_state.js`, so a card can never disagree with the node. `frame_index` is the authority and
seconds are only an input and a label; audio trim stays in sample points
(`source_start_sample` / `source_end_sample`) and its length is samples / sample rate / fps. Audio
ranges are half-open `[start, end)`, so two guides that touch do not overlap. Quotas: at most 16
enabled image guides, 16 audio, 32 total - a first-version product limit, not an official model limit;
disabled and unplaced guides are kept but do not count. Every failure is a readable Chinese error:
missing VAE, frame out of range, overlapping audio, two images on the same frame, an audio window that
leaves no samples, a missing media file, over quota. Shortening the video only marks guides out of
range - nothing is silently moved or rescaled.

**Panel** - the node body is a fixed-height summary strip (`启用 图片 N · 音频 M · 不执行 K · 24 FPS ·
帧数/时长`) with `🎬 打开 Guide 编辑器` and `🔄 刷新`; nothing on it resizes the node. The editor is a
floating panel (drag its bar to move it, drag its corner to resize it) in the same visual language as
the other panels here: `时间尺` + `图片轨` + `音频轨` share one coordinate transform, then the shared
`.h3lvm-deck` card grid with the shared 100%-400% card zoom and portrait-aware thumbnails. Real
thumbnails, real waveforms (blue is the part that will be used), and `▶` auditions the trimmed range
only. Each card carries its own `秒` / `帧` inputs and `启用/停用` - `放置` - `替换` - `复制` - `删除`;
dragging a card reorders the list, dragging a file into the grid uploads it through ComfyUI's own
`/upload/image`. Dragging a marker or clip moves only that element and updates its numbers live; the
write happens once on release, and the drag is limited to the valid range while a typed out-of-range
number is kept and reported. `←` / `→` nudge the selected guide by one frame (`Shift` = one second).
The footer lists every current problem and each line is a button that selects and scrolls to it.

**Timeline inside the node** - `addPanel` hands this panel every pixel the user drags the node taller,
so the summary bar is not the end of the story: below it the node renders the **same renderer on a
second surface** - `时间尺` + `图片轨` + `音频轨` fit to the node width, with real thumbnails, labels
and waveforms, and the markers and audio clips are draggable there too. Card width scales with the
lane height (40-72 px) and the scale padding follows it, so the first and last card are never cut off.
There are no zoom controls here (the whole video fits the width); zoom and the card pool stay in the
editor. When both are open they stay in sync. It never changes the node size: if the panel is shorter
than 160 px it hides itself, which is why it is not visible at the default node height - drag the node
taller and it appears.

**Persistence** - everything lives in the `guides` widget, so saving a workflow, refreshing, reopening,
copying the node and running two of them side by side are all isolated. Media is stored as
`{filename, subfolder, type}` inside ComfyUI's own folders - never a Blob URL, never base64. Closing
the editor or deleting the node never deletes media, because another workflow may reference it; a
missing file stays as a card with an error until `替换` re-links it. `resolved_frame_count` is written
back after a run so the ruler keeps the real length. Before the first run, type the target duration in
the `length_seconds` box - seconds, because that is how a person plans a shot - and the panel converts
it with `round(seconds × 24)` aligned up to 17n+5, showing its work (10 秒 → 240 → 243 帧). With nothing
typed it estimates from the upstream generator's `length` widget (which really is frames) and says so
instead of pretending.

**Not here** - no `guide_list` socket (nothing in this plugin produces one yet; the merge point stays
internal in `core.guide_timeline.merge_guides`), no snapping to 17n+5 or Motion Context (the native
node does not snap), no dialogue/TTS, no final mix, no keyframe tweening, no multi-shot orchestration,
and no upload of your media to any external service. If the running ComfyUI has no native
`MiniMaxH3AddGuide`, only this node reports it; the rest of the plugin loads normally.
### API endpoints

| Endpoint | Returns |
|----------|---------|
| `GET /h3_lvm/projects?scope=segments\|image\|audio\|uploads` | `{"projects": [...], "default": "H3_LVM"}` — `scope=segments` (default) is the video bins with their segment count (Picker/Manager); `scope=image` / `scope=audio` is that kind's own reference library with its card count (the two loaders) |
| `POST /h3_lvm/project` | body `{"project": <typed name>, "scope": "segments"\|"image"\|"audio"\|"uploads"}` → `{"name": <sanitized>, "created": true/false, "segments"\|"references": N}` — the scope picks which library the bin is created in |
| `POST /h3_lvm/project/delete` | body `{"project": <name>, "confirm": <same name>, "scope": ...}` → `{"name": ..., "deleted": true, ...}` — only that library is touched, never the video bin or the other kind |
| `GET /h3_lvm/ref_presets?project=<name>&kind=image\|audio` | `{"project_name": <name>, "references": [...]}` — that kind's preset for one project, paths only; a Chinese 400 for a kind that is neither |
| `POST /h3_lvm/ref_presets` | body `{"project": <name>, "kind": "image"\|"audio", "entries": <panel JSON>}` → `{"name": ..., "kind": ..., "saved": N}` — writes that kind's own library file only |
| `GET /h3_lvm/segments?project=<name>` | Full segment list with thumbnail URLs |
| `GET /h3_lvm/ref_plan?w=&h=&mp=&upscale=0|1` | `{"width", "height", "actual_megapixels", "area_error", "ratio_error", "mode"}` — the 32-grid size the reference loader will really produce for that source, target and upscale setting; `mode` is `target_mp` or `grid_align` and is what puts the "not upscaled" note on the card |
| `POST /h3_lvm/delete` | body `{"project": <name>, "segment_id": N}` → `{"deleted": N}` |
| `POST /h3_lvm/merge` | body `{"project": <name>, "segment_ids": [3, 4, 5]}` → `{"project": ..., "merged_id": 3, "merged_from": [3, 4, 5], "dropped_overlap_frames": N, "renumbered": [{"from": 6, "to": 4}], "segment": {...}}` — joins consecutive segments; a Chinese 400 for a non-consecutive selection or mismatched fps/size |
| `GET /h3_lvm/uploads?project=<name>&output_size=<option>&custom_max_side=<pixels>` | The upload library's cards: `{"project_name", "videos": [...]}` — each card carries `segment_id`, `storage_name`, `original_name`, `thumbnail`, `cover_url`, `video_url`, `width`, `height`, `source_fps`, `variable_fps`, `duration_sec`, `has_audio`, `out_fps`, `size_bytes`, `browser_preview`, plus `out_width` / `out_height` / `out_scaled` for the size the decode will really produce with that setting; a card whose file was deleted outside ComfyUI is listed with `missing_file: true` instead of disappearing |
| `POST /h3_lvm/uploads/import` | multipart form with the `project` field **before** the `file` part; bytes are streamed into a `.upload_*` temp file and the card is only registered after the probe succeeds → the card record. Over 2 GiB is a 413, and a rejected or interrupted file leaves no index ghost and no leftover bytes |
| `POST /h3_lvm/uploads/delete` | body `{"project": <name>, "segment_id": N}` → `{"deleted": N}` — that card, its file and its cover only; the cards after it move up one number, so the library stays 1..N; already gone is a Chinese 404 |
| `POST /h3_lvm/uploads/reorder` | body `{"project": <name>, "order": [3, 1, 2]}` → `{"project": ..., "order": [1, 2, 3], "videos": N}` — renumbers the cards 1..N in the order given; the files and covers do not move. An order that does not match the current cards (missing, unknown, repeated, or not a list) is a Chinese 400 and the index stays as it was |

**WebSocket event** — `h3_lvm/changed` is broadcast after a run saves segments
(`{"project": <name>, "segments": [1, 2, ...]}`) and after a delete
(`{"project": <name>, "deleted_id": N}`) and after a merge (`{"project": <name>, "merged_id": N}`). The `segments` list is what lets a Manager node show
exactly the cards from its own run instead of guessing from the bin contents.

`h3_lvm/uploads_changed` belongs to the upload library alone
(`{"scope": "uploads", "project": <name>, "segment_id": N, "action": "import"|"delete"|"reorder"}`).
Importing, deleting or reordering an uploaded video never refreshes cut-bin cards, and a cut-bin run
never touches the upload deck — the two panels listen to different events.

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
├── SMART_SPLIT_AUDIT.md             # Source audit behind H3 Smart Split
├── GUIDE_TIMELINE.md                # Native Add Guide audit + this node's contract
├── requirements.txt                 # Optional: scenedetect, Smart Split only

├── __init__.py                    # Entry: ComfyExtension + routes + web
├── comfyui/
│   ├── __init__.py                    # Plugin package (nodes loaded by root extension)
│   ├── nodes.py                       # Manager (V3) + Picker nodes
│   ├── ref_nodes.py                   # 图片/音频参考加载器（固定编号槽位）
│   ├── ref_presets.py                 # 参考库：图片/音频各一套（只存路径，不复制媒体）
│   ├── guide_nodes.py                 # H3 Guide 时间轴（逐条调用原生 Add Guide）
│   ├── nodes_v1.py                    # backup (pre-audio)
│   ├── nodes_v2.py                    # backup (pre-save-bin)
│   ├── nodes_v3_backup.py             # backup (pre-V3-API)
│   ├── nodes_v4_backup.py             # backup (pre-V3-API, v4 attempt)
│   ├── asset_paths.py                 # Asset path checks + versioned preview URLs
│   ├── segment_store.py               # Storage layer (save/load/list/delete)│   ├── uploaded_video_store.py        # 投放视频库：原文件 + 独立索引（与裁切库不共用根目录）
│   ├── video_decode.py                # PyAV probe + card cover + 24 fps decode → IMAGE/AUDIO
│   └── server_api.py                  # HTTP API routes
├── core/
│   ├── __init__.py                    # Layer A public API (dataclasses)
│   ├── models.py                      # Dataclasses (Segment, Manifest, etc.)
│   ├── models_v3_backup.py            # backup
│   ├── h3_grid.py                     # 17n+5 alignment + fixed-length segmentation
│   ├── smart_split.py                 # Scene-cut detection → shot ranges (no grid, no padding)

│   ├── h3_grid_v4_backup.py           # backup
│   ├── manifest.py                    # build_manifest()
│   ├── manifest_v4_backup.py          # backup
│   ├── segmentation.py                # Duration → frames computation
│   ├── person_crop.py                 # Person detection + edge crop
│   ├── ref_size.py                    # Target MP / grid-align size planner + resampling options
│   ├── ref_media.py                   # Media list parsing, path safety, cache keys
│   ├── guide_timeline.py              # Guide 列表规范化、校验、排序、执行摘要
│   └── extraction.py                  # Frame range extraction (PyAV)
├── web/
│   ├── h3lvm_picker.js                # Card gallery frontend
│   ├── h3lvm_picker.css               # Styling
│   ├── h3lvm_manager.js               # Chinese labels, hides the canvas project combo
│   ├── h3lvm_manager_panel.js         # Manager panel (project menu + card deck)
│   ├── h3lvm_smart.js                 # Smart Split Chinese labels + panel
│   ├── deck_panel.js                  # Card deck shared by Manager and Smart Split
│   ├── project_menu.js                # Project switch/create/delete row (all panels)│   ├── picker_mode_state.js           # Picker two-mode state + card copy rules (pure, node --test)
│   ├── preview_overlay.js             # MP4 preview modal (Picker + panels)
│   ├── card_zoom.js                   # Card size 100%-400% (shared control)
│   ├── thumb_fit.js                   # Card thumbnails: portrait frames shown whole
│   ├── delete_button.js               # Segment card delete button
│   ├── dom_panel.js                   # DOM widget sizing (Canvas + Nodes 2.0)
│   ├── ref_loader.js                  # Reference loader card panel (image/audio)
│   ├── ref_state.js                   # Media list rules (pure, node --test)
│   ├── ref_loader.css                 # Reference panel extras only
│   ├── guide_timeline.css             # 时间轴与编辑器外壳（卡片区沿用 h3lvm_picker.css）
│   ├── guide_state.js                 # Guide 列表与时间轴几何规则（pure, node --test）
│   ├── guide_timeline.js              # Guide 时间轴编辑器（两轨 + 卡片区）
│   └── extension.js                   # (placeholder, intentionally empty)
└── tests/
    ├── __init__.py
    ├── test_core.py                   # Core regression tests
    ├── test_frame_integrity.py        # No-frame-loss tests
    ├── test_h3_grid.py                # 17n+5 grid tests
    ├── test_node_schema.py            # Node output order lock
    ├── test_person_crop.py            # Person crop tests
    ├── test_fixed_segments.py           # Fixed-length segmentation tests
    ├── test_project_menu.py           # Project menu (list/create/delete) tests    ├── test_upload_store.py           # 投放视频库：两库隔离 / 稳定 ID / 索引损坏 / 路径安全
    ├── test_upload_api.py             # Upload API: import, delete, scope, size cap
    ├── test_video_decode.py           # Probe, 24 fps sampling, silent audio, covers
    ├── test_picker_dual_mode.py       # Old graphs stay on the cut bin; uploads round-trip
    ├── _media_clip.py                 # Test helper: a tiny generated clip
    ├── _plugin_import.py              # Test helper: import the plugin with or without ComfyUI
    ├── test_smart_split_core.py         # Scene-cut → lossless shot segments tests
    ├── test_smart_split_node.py         # Smart Split node end-to-end tests
    ├── test_ref_size.py               # 32 px grid size planner tests
    ├── test_ref_media.py              # Media list / path safety tests
    ├── test_ref_nodes.py              # Slot order, None slots, dtype tests
    ├── test_ref_presets.py            # 参考库：两类互不可见 / 旧共用文件迁移 / 预设读写与损坏
    ├── test_guide_nodes.py          # Guide 节点与原生链等价 tests
    ├── test_guide_timeline_core.py  # Guide 规范化 / 校验 / 排序 / 配额 tests

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
| **H3 Smart Split** | 接入视频 → PySceneDetect 找出真实镜头切点 → 每个镜头全部存进**同一个库** → 实时输出选中段 → 输出 `IMAGE`、`AUDIO`、`frame_count`、`total_segments` |

| **H3 Segment Picker** | 从库中读取 → 输出 `IMAGE`、`AUDIO`、`frame_count`、`segment_id`（前两项直接喂 H3） |
| **H3 Guide 时间轴** | 输入：`positive` + H3 AV latent + 两个 VAE + 一个 Guide 列表 → 在双轨时间轴上放图片/音频 Guide → 输出 `positive`（与手动串联原生 Add Guide 等价） |

### 核心特性

- **定长分段** — 每个整段长度完全一致：每段时长向下吸附到合法 H3 帧数，6.0s @ 24fps 就是每段 141 帧 = 5.875s，不会再出现一段 6.6s、一段 7.3s
- **17n+5 网格对齐** — 每个整段都是合法 H3 帧数，不会自动 snap 导致时长偏移
- **结尾一帧都不丢** — 最后一段直接吃掉剩下的全部帧（含 Motion Context 重叠帧），完全不做对齐：不重复任何帧、不补黑帧、也不丢任何帧。1962 帧 @ 6s/MC22 → 16 段 141 帧 + 1 段 58 帧 = 1962，正好
- **末尾的零头交给 H3 判断** — 最后一段的帧数不在 17n+5 上，也原样交给 MiniMax H3，由模型自己处理，你的视频不会悄悄少几帧
- **也可以按真实镜头切** — `H3 Smart Split` 是同一个素材库的第二个产出节点：PySceneDetect 在接入的视频里找出真实镜头边界，每个正文区间按检测结果原样保存。不做 17n+5 吸附、不补帧、不丢帧、不重复主帧，最后一个镜头有多长就是多长
- **这里的 Motion Context 是可选的** — Smart Split 默认 0，而且它只放大提取范围，绝不会移动切点

- **Motion Context 感知** — 提取范围包含 MC 上下文帧，保证接续连贯
- **本地片段库** — safetensors 存储（默认 int8，可切 fp16）+ 首帧缩略图 + 可选 MP4 预览
- **视觉卡片选择** — 点击缩略图选段，无需重新加载视频
- **竖屏画面完整显示** — 9:16 的缩略图在同一张卡片里整帧可见，左右两侧用同一帧的模糊副本填充而不是黑边；横屏画面照旧铺满，两种情况的卡片尺寸完全一致
- **素材库常开** — Manager 节点的卡片区一直展开，重新打开工作流卡片直接出现，没有展开按钮，也不用点刷新
- **固定时长这条路径零额外依赖** — 只需要 `torch` + `safetensors`（ComfyUI 自带）。Smart Split 另外用到 `scenedetect>=0.6.4,<0.8`；这个包不在的时候插件照常加载，只有 Smart Split 会打印出该执行的安装命令
- **一个节点替代一串原生 Add Guide** - `H3 Guide 时间轴` 只维护一个 Guide 列表，按帧顺序逐条调用原生节点：条件结构相同、帧位置相同，不用手接四个节点
- **双轨时间轴编辑器** - 真实缩略图与真实波形、标记和音频条可以一帧一帧拖、试听只播裁切后的那一段，所有冲突在底栏列成可点击的一行


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
  ▼  (或者不用 Manager，让画面自己决定切在哪里)
H3 Smart Split
  ├── 在接入的张量上检测：真实镜头切点 → [0,214) [214,505) [505,960)
  ├── 保存全部 → 同一个库、同样的卡片、同一个 Picker
  └── 实时输出选中段 (IMAGE + AUDIO)
  │
  ▼  (之后，无需重新载入视频——两种产出同一个库，Picker 不用改)
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
>
> **可选**：`scenedetect>=0.6.4,<0.8`，只有 `H3 Smart Split` 用到：
>
> ```bash
> "<运行 ComfyUI 的那个 python>" -m pip install "scenedetect>=0.6.4,<0.8"
> ```
>
> 没有这个包，Manager、Picker 和素材库的行为完全不变；Smart Split 会停下并把同一个命令
> 打印成错误信息，命令里的 python 就是当前运行的那个。>
> **投放视频需要 PyAV**：Picker 的**投放视频**库用 `av` 解码，和 Manager 用的是同一套
> 「装在 Python 环境里的 FFmpeg」，不需要在 `PATH` 上另装 `ffmpeg`。它没有写进
> `requirements.txt`，因为正常的 ComfyUI 环境本来就带这个包；真的缺了，裁切片段模式照常
> 工作，投放视频模式会停下并打印 `pip install av`。


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

ComfyUI/output/h3-lvm-video-uploads/<项目名>/   # Picker 的投放视频库（独立根目录，绝不在 h3-lvm 里面）
├── h3lvm_upload_index.json   # 卡片：原始文件名、时长、尺寸、帧率、有无音轨
└── files/
    ├── vid001.mp4            # 用户自己的文件，逐字节保存——不转码、不裁切
    └── vid001_cover.jpg      # 卡片封面（最长边 320 px）

ComfyUI/output/h3-lvm-image-refs/<项目名>/h3lvm_references.json   # 图片参考预设
ComfyUI/output/h3-lvm-audio-refs/<项目名>/h3lvm_references.json   # 音频参考预设
```

占用空间 = 帧数 × 宽 × 高 × 3 × 每个值的字节数：1280×720 下 fp16 每帧约 5.5 MB，int8 约 2.8 MB。
Motion Context 的重叠帧会在每一段里再存一份，所以一次运行写出的帧数会比源视频多。
投放视频库是另一种存法：一张卡片就是磁盘上的一个原文件，没有别的。导入不写
`.safetensors`，也不把解码结果常驻在内存里——只有节点真正运行时才解码，一次只解一张卡片。

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

**Manager 面板** — 参数下面是与 H3 Segment Picker 同一套视觉的面板：顶部是项目素材库菜单（切换 / 新建 / 删除项目，右侧实时显示片段数），接着是工具行（`🔄 刷新`、`🔗 合并模式`、`卡片大小` 100%–400%、`🎬 素材库` 状态），再下面是常开的卡片网格（没有折叠按钮）。卡片区读的是当前选中的素材库，按片段编号顺序显示库内**全部**片段：缩略图、片段编号、帧数和时长，带 ▶ 按钮播放 MP4 预览，点卡片就是把该段设为「输出片段编号」。本节点上一次运行产出的片段带一个 `本次` 小标记，状态行会写清楚（`库内 17 段 · 本次生成 6 段（片段 1–6）`）。在 Segment Picker 里删除片段，这里同步消失。这里不保存任何状态：本次编号来自节点保存后本来就会发的 `h3_lvm/changed` 事件，刷新页面后只剩素材库本身、没有标记。缩略图按画面方向自适应：横屏铺满，竖屏（9:16）整帧显示并在后面垫一层同帧模糊副本，卡片尺寸不变。

卡片区属于素材库而不是这一次页面访问：重新打开工作流时，面板会在「项目素材库」的名字恢复之后自己重画，卡片直接出现，不需要点刷新。面板高度同时是 widget 的最小高度，节点太矮时 ComfyUI 会自动长到能显示一行卡片，宽度按用户自己的设置不变。

**卡片大小** — 两个面板用的是同一个控件（`web/card_zoom.js`）：`−` / `+` 在 100% / 150% / 200% / 300% / 400% 之间步进，到两端按钮自己变灰而不是绕回，卡片区在面板内滚动。它只改 CSS 变量 `--card-min` 和 `--thumb-h`，节点尺寸完全由用户掌握。

**合并模式** — 自动切分有时会把一个镜头切成好几个小片段，所以两个卡片区都在工具行里放了 `🔗 合并模式`，与 `🔄 刷新` 同一行同一高度。打开后卡片可以点选：点两段以上**相邻**的卡片（点了不相邻的就重新从这一段开始选），卡片上出现 `已选` 角标，同一行出现 `✅ 确认合并`。合并把这几段接成一个卡片，**编号沿用所选里最小的那个**，后面的片段按删掉的段数依次前移，整个库始终是 1..N 连续编号——也就是「输出片段编号」读的那个号。相接时会去掉每个接缝的 Motion Context 重叠帧（第一段之后每段头部的若干帧，音频按同样的时长同步裁掉），所以接出来的片段既不会重复帧也不会音画错位；只要有一段没有音频，合并结果就不带音频。帧数据按库里存的 packed 格式（int8/fp16）直接拼接，长片段不会因为合并而多吃一份 float32 内存。所选片段帧率或分辨率不一致会被拒绝并给出中文提示。合并模式只是界面上的状态，不写进工作流，刷新页面就关掉。

#### H3 Smart Split

| 参数 | 默认值 | 节点上显示为 | 说明 |
|------|--------|--------------|------|
| `project_name` | H3_LVM | 📦 项目素材库 | 与 Manager 同一个素材库。节点上的下拉框已隐藏，面板顶部的同一个菜单（切换 / 新建 / 删除）直接写这个字段 |
| `fps` | 24 | 源视频帧率 | 源视频帧率。检测跑在接入的张量上，所以它同时也是帧号 ↔ 时间的换算基准 |
| `detection_sensitivity` | medium | 镜头切点灵敏度 | 对应 `AdaptiveDetector.adaptive_threshold`：低 4.5 / 中 3.0 / 高 2.0，与参考实现 Director 完全一致。它只决定切在哪里，不改变切分规则 |
| `motion_context_frames` | 0 | Motion Context 帧数 | 0/5/22/39/56。只放大提取范围，不会移动切点。默认 0，因为真实镜头边界不是需要掩盖的接缝 |
| `segment_id` | 1 | 输出片段编号 | 实时输出第几个镜头（1 = 第一个镜头） |
| `scale_percent` | 100 | 画面缩放 % | 缩放比例 |
| `save_enabled` | true | 保存到素材库 | 是否存库（关 = 纯实时模式） |
| `save_preview_mp4` | false | 生成 MP4 预览 | 是否生成 MP4 预览 |
| `save_dtype` | int8 | 素材存盘精度 | 与 Manager 是同一个开关 |

这个节点上刻意**没有** `segment_duration`、`align_to_h3_grid`、`final_align`、`person_crop*`：
镜头边界不是一个时长，节点也不该在背后悄悄改动帧数。输出接口与 Manager 完全一致，
所以现有的 H3 Segment Picker 不需要任何改动就能读两种产出。

**面板** — 顶部是与其他两个节点完全相同的项目素材库菜单（切换 / 新建 / 删除，右侧实时显示片段数），
下面是与 Manager 完全相同的卡片区：按片段顺序显示库内全部片段，本节点这次运行产生的卡片带
`本次` 角标，卡片缩放 100%–400%，点卡片即切换输出片段编号。卡片区代码是共用的
（`web/deck_panel.js`），两个节点写的是同一个素材库，所以任一节点产出的卡片在另一个节点里
同样可见。切点与每个镜头的帧区间会打印在控制台的 `SEGMENT TABLE` 里。检测把同一个镜头切成好几个小片段时，用 `🔗 合并模式`（说明见 Manager 面板）手动接回去。


#### H3 Segment Picker

一个节点、两个素材库、四个输出不变。项目菜单上方有两个按钮决定节点读哪个库；切换是显式的，
不会根据磁盘上有什么去猜。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `project_name` | H3_LVM | 读哪个项目——范围是当前模式按钮指向的那个库。面板上是一个下拉菜单：列出**该库**里的所有项目并带数量，`＋ 新建项目…` 建一个空的，`🗑 删除当前项目…` 在确认行里重复名字后删除整个项目 |
| `segment_id` | 1 | 读取第几段 / 第几张卡片 |
| `source_mode` | `segments` | `segments` = 裁切片段（Manager / Smart Split 保存的切片库），`uploads` = 投放视频（在节点面板里拖入或载入的完整视频）。这个字段是追加在两个旧字段之后的：更早保存的工作流保留原来的两个值，继续读裁切库 |
| `output_size` | `原始（不缩放）` | 只作用于投放视频：把执行时解码出来的画面等比缩小到该最长边——`原始（不缩放）` / `最长边 3840` / `1920` / `1280` / `960` / `640` / `480` / `自定义（自己填最长边）`。只缩放解码，磁盘上的原文件一个字节都不改，所以改这个设置只多一次解码，切回原始也没有任何损失。4K 一帧 float32 是 8 MB，而 H3 编码器本来还会再缩小，4K/2K 素材选 1920 或 1280 更稳。这个字段同样是追加在 `source_mode` 之后的：更早保存的工作流保留原来的三个值，按原始尺寸解码。裁切片段模式不用它 |
| `custom_max_side` | 1920 | 只有当 `output_size` 选到 `自定义（自己填最长边）` 时才读取：最长边的像素数，范围 16–8192。填越界的数字会被夹到边界而不是当成无效直接不缩——因为人填的数字是意图，而 `scale_plan()` 从不放大画面，比源还大的上限本来就等于不缩放。选的是预设档位时这个值完全不读。同样是追加在 `output_size` 之后的，位置恢复才安全 |

**模式一 · 裁切片段（默认，行为不变）** — 读取 Manager 或 Smart Split 保存的 `.safetensors`。
不再解码任何东西，四个输出与这个功能之前完全一致。

**模式二 · 投放视频** — 用户拖进节点的完整视频，按原文件存在另一个根目录里。导入不需要运行
工作流，也不生成张量：文件逐字节保存，探测出时长 / 尺寸 / 帧率 / 有无音轨，并生成卡片封面。
只有被选中的那张卡片会被解码，而且只在运行时——帧按 24fps 采样（H3 的约定），音频重采样到
44.1 kHz，没有音轨的视频会得到时长一致的静音 AUDIO，下游 H3 节点不会收到 `None`。这里不裁切、
不补黑帧、不做 17n+5 对齐：文件是什么样，H3 拿到的就是什么样。上限：`.mp4 .m4v .mov .mkv
`.webm .avi .ts .mts`、单文件 2 GiB、每个项目 999 张卡片。

**输出分辨率只作用于解码，不是转码** — `输出分辨率` 在解码时给最长边设上限：4K 一帧 float32 是 8 MB，
这个上限就是让 4K 素材不至于吃掉整块内存，也不会被内存预估直接挡在门外（预估改用计划尺寸，
报错文案会直接说「请在节点上把「输出分辨率」调小」）。缩放等比、对齐偶数、绝不放大；磁盘上的原文件
逐字节不变，所以切回 `原始（不缩放）` 没有任何损失。卡片上的「输出」尺寸由服务端用同一个 `scale_plan()`
算出，因此卡片说的就是运行时真正会得到什么（`源 3840×2160 → 输出 1920×1080（原文件不变）`）；裁切片段
模式下这个控件的标签会写成 `输出分辨率（裁切不用）`，而不是把它藏起来。选项表只有一份，放在
`comfyui/video_decode.py::RESIZE_OPTIONS`，节点控件、卡片文案和测试不可能各说一套。最后一档
`自定义（自己填最长边）` 的标签里故意不带数字，它读的是 `custom_max_side`；面板会在选中它时把那个
字段标成 `（生效中）`、否则标成 `（选自定义后可用）`，让「这个数字现在有没有生效」一眼可见——控件
不会被藏起来，因为忽隐忽现的控件看起来像坏了，节点高度还会跟着跳。

**编号就是卡片顺序** — 投放视频库的卡片可以直接拖动换位：松手的位置决定新顺序，第一张卡片
就是 `segment_id 1`，其余依次重排。导入和删除走的是同一条规则：新视频排在最后，删掉一张
卡片后后面的卡片依次补位，所以一个库永远是 1..N 连续编号、不会有空号——这就是面板上显示的
号，也是「输出片段编号」读的号。删除后如果选中的卡片还在，面板会把选中跟到它的新编号，并在
状态行写清楚（`当前选中：视频 2（后面的编号已顺延）`）。重编号只重写索引，磁盘上的视频和
封面不动（读取一律走索引记录），所以无论拖动还是删除都不搬一个字节。文件沿用导入时拿到的
不透明名字（索引里的 `next_id` 只是这个存储序号，同一个名字永不复用），因此删除腾出来的
编号不会盖掉另一张卡片的文件。工作流里保存的 `segment_id` 因此是「排在第几」，不是「当初
上传的第几个」——这正是把几个视频按顺序接成长片时要的语义。裁切片段库的卡片仍按编号排列、
不可拖动：那边的编号是 Manager / Smart Split 保存时写下的，不在这里改。

**面板布局** — 自上而下四行：① 两个模式按钮（`🎬 裁切片段` / `📥 投放视频`）；② 带标签的项目
菜单，右侧实时显示当前库的数量（`＋ 新建项目…` 与 `🗑 删除当前项目…` 都在这个菜单里）；
③ 工具行（刷新、卡片大小 100%–400%、当前选中，投放模式下还有 `＋ 载入视频`）；④ 卡片网格，
最下方一行操作图例。卡片标题与状态文字全部中文，节点参数名也显示为中文（`label` 只影响显示，
保存的工作流仍然是 `project_name` / `segment_id` / `source_mode` / `output_size` / `custom_max_side`）。

**两个模式各自的选中都会恢复** — 每个模式各自的项目 + 卡片存在
`node.properties["h3lvm_picker_modes"]`：保存工作流、重新打开、甚至重启 ComfyUI 之后，两个模式
各自选中的东西都会回来；读取时以工作流里的值为准，所以这个功能之前保存的工作流仍然打开在
裁切片段。把文件拖到卡片区就是上传（视频文件不会让 ComfyUI 顺手生成 `LoadImage` 节点）。
投放卡片显示封面、原始文件名、时长、分辨率、源帧率（与 24fps 不同时会标注「输出按 24fps 采样」）
以及有无音轨；在 ComfyUI 外面删掉的文件不会让卡片消失，而是保留卡片并标注「文件已丢失」。
▶ 在浏览器能播的封装里直接预览（`.mkv` / `.avi` 会说明为什么不能），🗑 删除这张卡片和它的文件。

缩略图沿用其它可视化节点的规则：横屏铺满（`object-fit: cover`），竖屏（9:16）整帧显示
（`object-fit: contain`）并在后面垫一层同帧模糊副本，不会被压成一条窄带；缩略图区域和卡片尺寸
在两种情况下完全一致。卡片缩放 100%–400% 与 Manager、Smart Split 用的是同一个控件。


#### H3 图片参考加载器 / H3 音频参考加载器

这两个节点直接喂官方 `MiniMaxH3ReferenceToVideo` 的参考端口（`ref_image_0..8`、
`ref_audio_0..2`），不用再摆一排 `LoadImage` / `LoadAudio` 加缩放节点。卡片顺序就是槽位顺序，
空槽输出真正的 `None`，H3 节点会跳过（`if img is None: continue`）。

| 参数 | 默认值 | 节点上显示为 | 说明 |
|------|--------|--------------|------|
| `media_files` | `[]` | 🎞 参考素材列表 | 由卡片面板写入的 JSON 列表：`[{"filename", "subfolder", "type"}, ...]`；音频条目还可以带 `"start"` / `"duration"`（单位秒），那就是这张卡片的裁切窗口。手写 API 时也可以直接填文件名列表。面板正常运行后这个控件会被隐藏（`options.hidden`），但值仍按位置序列化。「已跳过」的卡片带 `"skip": true`，节点不会读它 |
| `target_megapixels` | 0.25 | 🎯 目标像素量 (MP) | 每张图的目标像素量（百万像素，0.02–8.0）。每张图保持自己的比例并对齐 32 像素网格；改这个数会立刻重算所有卡片的尺寸 |
| `project_name` | `H3_LVM` | 📦 项目素材库 | 决定「📥 载入项目预设 / 📤 存为项目预设」读写哪个项目文件夹。刻意排在输入最后——`configure()` 按位置恢复控件值，新字段不能把已有字段挤位；它不进缓存键，也不改变任何像素。面板的项目选单运行后这个控件同样被隐藏，与 `media_files` 一致 |
| `resampling_method` | `Lanczos` | 🔍 重采样算法 | `Lanczos` / `Bicubic` / `Bilinear` / `Nearest`，直接映射到 PIL 的滤镜；选项表、后端和测试读的是同一份常量，界面不可能出现「写着 A 实际跑 B」。缩小优先 `Lanczos`，像素风素材要硬边用 `Nearest`。改它会重新解码图片（它在缓存键里），但不会改变输出尺寸 |
| `upscale_small_images` | false | ↕ 放大小图至目标 MP | 关闭：只把大于目标面积的图缩小，小于它的图只做 32 网格所需的最小调整，卡片会标 `（未放大，仅对齐网格）`。开启：所有图都缩放到目标面积。默认关闭——放大只是凭空造细节，还会增加后续编码开销 |

**输出端口** — `ref_image_0 … ref_image_8`（`IMAGE`，batch = 1）与 `ref_audio_0 …
ref_audio_2`（`AUDIO`）。永远是九个 / 三个端口，顺序固定。

**图片尺寸** — 唯一实现在 `core/ref_size.py`：按比例缩放到 32 像素网格，不裁切、不补边。`plan_reference()`
决定用哪种模式：`target_mp` 按目标面积缩放（大于目标面积的图，或开启 `upscale_small_images` 时的全部图）；
`grid_align` 每个轴最多只挪一个网格步，本来合法的源原样返回——节点就是靠这一点跳过重采样的。两种模式的候选
都来自三条思路（理想尺寸、面积匹配、比例匹配），再用确定的 tie-break 选一个。在测试范围内（目标 ≥ 0.25 MP、
源比例 ≤ 3:1）最坏是面积误差 8.95%、比例误差 3.57%；480×640 的源在 0.25 MP 下会主动让一点比例去换目标面积。
「关闭放大」不等于「像素数一定不变」：300×200 会变成 320×192，因为 32 像素网格要求这样，卡片会标
`（未放大，仅对齐网格）`，免得看起来像 bug。卡片上显示的是 `源尺寸 → 输出尺寸 · 实际 MP`，这个数字来自
`GET /h3_lvm/ref_plan`，也就是节点真正跑的那套算法，不是 JavaScript 复刻。EXIF 方向会应用，alpha 会丢弃
（与 `LoadImage` 一致），动图取第一帧，超过 40 MP 的源会用可读的错误拒绝。

**音频** — 加载器唯一会改的是「从哪一秒开始、要多久」：每张音频卡片都有 `开始` / `时长` 两个输入
（单位秒），写在条目上的 `"start"` / `"duration"`，所以这段裁切会跟着保存、刷新和项目预设一起存活。
规则与 ComfyUI 自带的 `TrimAudioDuration` 一致：开始时间填负数是从片尾往前算，时长填 0 表示一直到片尾，
两端都会被夹到文件范围内；只有「裁完没有样本」才是错误，而且会用中文说清楚。其余一切原样传递——不重采样、
不混音。H3 在 `_encode_ref_audio` 内部为自己的音频 VAE 重采样，所以加载器保留原始采样率与声道数。
解码用的是 ComfyUI 自带的 `comfy_extras.nodes_audio.load`，和 `LoadAudio` 同一个解码器。

**面板** — 与素材库面板同一套视觉语言：工具行（`🔄 刷新`、`卡片大小` 100%–400%、槽位状态
`已用 3/9（ref_image_0..ref_image_2） · 空槽输出 None`）、`＋ 添加参考图` / `＋ 添加参考音频`
按钮、把文件直接拖进网格，以及每个槽位一张卡片：缩略图（竖屏整帧显示，卡片尺寸不变），音频卡片则是画在同一个缩略图框里的波形（蓝色就是会被输出的部分，灰色不会；`▶` 只试听这一段，点波形可以在这一段里定位）加一行 `开始` / `时长`（秒）和 `↺` 清除裁切——音频卡片与图片卡片同尺寸，由同一个 `卡片大小` 控件缩放，
它对应的端口（`参考图 3 → ref_image_2`——卡片上的编号给人看，从 1 开始；端口名仍是 `ref_image_2`）、真实输出尺寸，以及 `↻ 替换` / `⊘ 跳过` / `✕ 移除` 按钮（被跳过的卡片上是 `↩ 放回` / `✕ 移除`）；卡片本身可以直接拖动，拖到哪里就换到哪个槽位（卡片顺序就是槽位顺序）。整个面板都是落点，落点取最近的卡片，卡片之间的缝隙和末行下方的空白都能用，指针停在上下边缘时卡片区会自己滚动。面板高度是固定的，
所以面板上的任何按钮都不会改变节点尺寸。文件通过 ComfyUI 的 `/upload/image` 存到 `input` 目录；
列表里只保存相对路径；同名文件被替换后会重新解码，因为缓存键包含文件大小与修改时间。

**已跳过（`⊘ 跳过`）** — 这一轮不想送进 H3、但还想留在工作流里的卡片不会被删除，而是被停到后排：
它移到卡片区后面的第二个区块，变暗、标 `⊘ 已跳过 · 不占槽位`、不可拖动。编号端口只由前面的槽位区块决定，
所以跳过第 2 张后后面的卡片自动补位（第 3 张变成第 2 张…），而那张卡片的文件仍在 `media_files` 里，带
`"skip": true`——`↩ 放回` 把它放回槽位顺序的末尾，不需要重新上传；`↺ 全部放回`（只有存在跳过项时才出现）
把放得下的都放回去，放不下的留在后排。已跳过的卡片不占 9/3 的槽位上限，也不进缓存键，因为节点根本不读它。

**项目参考预设** — 一部片子会反复用到同一批角色与场景参考，所以面板可以把当前卡片组合存成某个项目的预设，再放进任何同类节点：
`📤 存为项目预设` 写入 `<output>/h3-lvm-image-refs/<项目>/h3lvm_references.json`（音频加载器写自己的 `<output>/h3-lvm-audio-refs/<项目>/h3lvm_references.json`），`📥 载入项目预设` 把库里那套卡片放回来。
预设里**只有路径**——就是卡片本来就持有的那三个字段——所以图片再大也只花几百字节，不复制、不重复上传、不产生第二份文件。
存的是**排列**，不是一堆文件路径：槽位卡片的先后顺序（这个顺序就是 `ref_image_` 端口的顺序）和哪些卡片当时被跳过，都会存下来并原样恢复。
图片库与音频库**完全分开**：每一类各有自己的根目录、项目列表和一个只装一份列表的文件——参考图片和参考音频是给不同端口的不同材料，一个按片子命名的素材库说明不了哪些配音属于它，所以音频加载器不会看到图片加载器的项目，反之也一样；拆分前那份共用文件会在第一次读取时按类别各复制一次到对应库里，旧文件原样留着。回来时同样受槽位上限约束（超出部分吃预设的尾部）；载入是**整组替换**——面板之后就是预设那一套（顺序与跳过状态原样），预设外的卡片（含被跳过的）会被移除：预设就是一个项目的参考组合，把剩下的留在旁边等于下一轮悄悄带上用户已经不要的参考；想加卡片就正常「＋ 添加」，同一个预设连载入两次也不会变。
面板第一行就是共用的 `📦 项目素材库` 选单（切换 / `＋ 新建项目…` / `🗑 删除当前项目…`），在这两个节点上它列的是**本类自己的库**、数的是**参考卡片张数**（`项目名 (4 张)`、`共 4 张参考`、`无预设`）——参考库里没有视频片段，以前只会显示（空）；Picker 与 Manager 仍然数片段。在这里新建或删除项目也只作用于本类：删掉一部片子的配音预设不会带走它的角色图。状态行会显示库里有什么（`项目预设 4（含 1 张已跳过）`），空库时载入按钮是禁用的。预设文件缺失或写坏时读出来是空的，不会让面板报错；切换项目会重新读取。

**与官方节点的默认值差异** — 官方 `ref_image_size` 是 `match`/`max`（短边 ≤ 2048，16:9 画面约
3.2 MP），而 `LoadImage` + 缩放到长边 512 的旧链路大约只有 0.15 MP。这两个节点默认 0.25 MP；
想要官方默认量级就把 `target_megapixels` 设到 3.2 左右。
#### H3 Guide 时间轴

一个节点替代一串原生 `MiniMaxH3AddGuide`。原生节点一个只能锚定一张图或一段音频，所以「三张姿态图 +
一条配音」就是四个节点手动串联，而且帧号只存在于每个控件里。这个节点保留原生的语义，把那一串换成一个
列表：`positive`、MiniMax H3 的 AV latent 和两个 VAE 各接一次，然后在双轨时间轴上放 Guide。

| 参数 | 默认值 | 节点上显示为 | 说明 |
|------|--------|--------------|------|
| `positive` | - | positive | 要被引导的条件。没有任何「启用且已放置」的 Guide 时原样透传 |
| `latent` | - | latent | MiniMax H3 的 AV latent。视频真实总帧数由它算出（`1+4+4+4+4...` 的 token 网格），编辑器的时间尺用的就是这个数 |
| `length_seconds` | 0.0 | ⏱ 视频时长（秒） | 只给编辑器的时间尺用，单位是秒（和本插件 `segment_duration` 同一套习惯）：面板按 `秒 × 24` 换算成帧并向上对齐 17n+5，还把算式写出来（10 秒 → 240 → 243 帧）。0 = 不设置。它不参与执行，也不改变输出 |
| `vae` | 可选 | vae | 视频 VAE。只要有「启用且已放置」的图片 Guide 就必须接；没有图片 Guide 时可以留空 |
| `audio_vae` | 可选 | audio_vae | 音频 VAE。只要有「启用且已放置」的音频 Guide 就必须接 |
| `guides` | `{"schema_version":1,"fps":24,"guides":[]}` | 🎬 Guide 列表 (JSON) | 面板读写的完整文档：Guide 列表 + `view_state` + `resolved_frame_count`。由编辑器写入，也可以直接手改 |

**输出端口** — 只有 `positive`（Conditioning）。没有 `ref_images` / `ref_audios`：Guide 是时间锚点，不是参考槽位，
那是两个参考加载器的职责。

**执行流程** — 解析列表 → 过滤停用与待放置 → 一条都没有就把 `positive` 原样返回 → 从 latent 读出真实总帧数 →
**先把全部校验跑完再开始编码** → 按 `(frame_index, 图片优先, 原列表次序)` 排序 → 逐条调用原生
`MiniMaxH3AddGuide.execute`，上一条的结果作为下一条的输入 → 返回最后那个 `positive`。这就是手动串联的等价：
原生节点按调用顺序追加关键帧条目，`PackedLayout` 按列表顺序打包，所以「编码前先按帧排序」才是「同样的
Guide、同样的帧位置」等价的原因。两个 VAE 是刻意常连的（不做惰性加载），但没有音频 Guide 时不会调用音频编码，
没有图片 Guide 时不会调用视频编码。

**规则** — 规则只有一份，写在 `core/guide_timeline.py`，`web/guide_state.js` 是它的镜像，所以卡片不可能和节点
说法不一致。`frame_index` 是权威时间位置，秒数只是输入和显示；音频裁切始终用采样点边界
（`source_start_sample` / `source_end_sample`），时长 = 样本数 / 采样率 / 帧率。音频区间是半开区间 `[start, end)`，
首尾相接不算重叠。配额：启用的图片最多 16、音频最多 16、合计最多 32——这是首版的产品限制，不是官方模型限制；
停用与待放置的条目保留在列表里但不占配额。所有失败都是可读的中文错误：缺 VAE、帧位置越界、音频重叠、
同一帧放了两张图片、裁完没有样本、素材文件丢失、超过配额。视频变短只会把 Guide 标成越界，不会悄悄按比例挪位置。

**面板** — 节点本体是一条固定高度的摘要条（`启用 图片 N · 音频 M · 不执行 K · 24 FPS · 帧数/时长`）加
`🎬 打开 Guide 编辑器` 和 `🔄 刷新`，上面的任何按钮都不会改变节点尺寸。编辑器是浮在画布上的面板（拖标题栏移动、
拖右下角改大小），视觉语言与本插件其他面板一致：`时间尺` + `图片轨` + `音频轨` 共用同一个坐标变换，下面是共用的
`.h3lvm-deck` 卡片区和共用的 `卡片大小` 100%–400%、竖屏整帧显示的缩略图。缩略图是真的、波形是真的（蓝色就是会被
使用的部分），`▶` 只试听裁切后的那一段。每张卡片自带 `秒` / `帧` 两个输入和 `启用/停用` · `放置` · `替换` · `复制` ·
`删除`；拖动卡片就是给列表换序。把文件拖进**卡片池**（整段都接受，包括带 `卡片大小` 的标题栏）会通过 ComfyUI 自带的
`/upload/image` 上传；图片还是音频由文件自己的扩展名决定，投进当前没显示的那一格时面板会自动切过去并写明「已切到音频卡片」，
同名素材第二次投放会被去重并在提示里说明。在时间轴上拖动标记或
音频条只会移动那一个元素并实时更新它的数字，松手才写一次；拖动被限制在有效范围内，而手填的越界数值会被保留并
明确报错。`←` / `→` 让选中项移动一帧（`Shift` = 一秒）。底栏列出当前所有问题，每一行都是按钮，点了就选中并滚到那张卡片。

**节点内的时间轴** — `addPanel` 会把用户拉高节点多出来的空间全交给这个面板，所以摘要条不是全部：它下面渲染的是**同一个
渲染器的第二 surface**——`时间尺` + `图片轨` + `音频轨` 按节点宽度铺满，缩略图、名称与波形都是真的，marker 和音频条
在这里**同样可以拖动**，拖完卡片上的数字与编辑器一起更新。卡片宽度随轨道高度自适应（40–72px），刻度 padding 与它成契约，
首尾卡片不会被裁。这里没有缩放控件（整段视频按宽度铺满），缩放和卡片池仍在编辑器里；两处同时显示时互相同步。它也绝不改变节点尺寸：
面板可用高度不足 160px 时它自己消失——所以默认节点高度下看不到它，把节点拉高就会出现。

**保存与恢复** — 所有状态都在 `guides` 这个控件里，所以保存工作流、刷新页面、重新打开、复制节点、两个节点同时打开，
彼此都不会串数据。素材只存 `{filename, subfolder, type}`，文件永远在 ComfyUI 自己的目录里——绝不存 Blob URL，也不存
base64。关闭编辑器或删除节点都不会删除素材，因为别的工作流可能还在引用；素材丢失时卡片保留并报错，用 `替换` 重新关联。
`resolved_frame_count` 在运行后写回，时间尺因此保持真实长度。第一次运行前可以直接填 `length_seconds`（秒，
人就是这么规划一条镜头的）：面板按 `秒 × 24` 换算并向上对齐 17n+5，并把算式写出来（10 秒 → 240 → 243 帧）。
什么都没填时才会用上游 generator 的 `length` 控件（那个本来就是帧）估算，并且会说明这是估算，不会假装知道。

**这里没有的东西** — 没有 `guide_list` 插口（本插件还没有生产它的节点，合并点先留在内部
`core.guide_timeline.merge_guides`）、不把时间吸附到 17n+5 或 Motion Context（原生节点也不吸附）、不生成台词/TTS、
不做最终混音、不做关键帧补间、不做多 Shot 编排，也不会把你的素材上传到任何外部服务。如果当前 ComfyUI 没有原生
`MiniMaxH3AddGuide`，只有这个节点会报错说明，本插件的其他节点照常加载使用。
### API 接口

| 接口 | 返回 |
|------|------|
| `GET /h3_lvm/projects?scope=segments\|image\|audio\|uploads` | `{"projects": [...], "default": "H3_LVM"}` — `scope=segments`（默认）是视频素材库 + 片段数量（Picker/Manager 用）；`scope=image` / `scope=audio` 是那一类自己的参考库 + 卡片数（两个参考加载器用） |
| `POST /h3_lvm/project` | 请求 `{"project": <用户输入的名字>, "scope": "segments"\|"image"\|"audio"\|"uploads"}` → `{"name": <清洗后的名字>, "created": true/false, "segments"\|"references": N}` — scope 决定在哪个库里新建 |
| `POST /h3_lvm/project/delete` | 请求 `{"project": <库名>, "confirm": <同一个库名>, "scope": ...}` → `{"name": ..., "deleted": true, ...}` — 只动那一个库，不会碰视频素材库或另一类参考 |
| `GET /h3_lvm/ref_presets?project=<项目名>&kind=image\|audio` | `{"project_name": <项目名>, "references": [...]}` — 那一类在该项目下的预设，只有路径；kind 不是 image/audio 时返回中文 400 |
| `POST /h3_lvm/ref_presets` | 请求 `{"project": <项目名>, "kind": "image"\|"audio", "entries": <面板 JSON>}` → `{"name": ..., "kind": ..., "saved": N}` — 只写那一类自己的库文件 |
| `GET /h3_lvm/segments?project=<名称>` | 完整片段列表 + 缩略图 URL |
| `GET /h3_lvm/ref_plan?w=&h=&mp=&upscale=0|1` | `{"width", "height", "actual_megapixels", "area_error", "ratio_error", "mode"}` — 参考图加载器对该源图、目标 MP 与放大开关实际会产出的 32 网格尺寸（卡片上的尺寸就来自这里）；`mode` 是 `target_mp` 或 `grid_align`，卡片上「未放大」的说明就由它决定 |
| `POST /h3_lvm/delete` | 请求 `{"project": <库名>, "segment_id": N}` → `{"deleted": N}` |
| `POST /h3_lvm/merge` | 请求 `{"project": <库名>, "segment_ids": [3, 4, 5]}` → `{"project": ..., "merged_id": 3, "merged_from": [3, 4, 5], "dropped_overlap_frames": N, "renumbered": [{"from": 6, "to": 4}], "segment": {...}}` — 只接受编号连续的片段；选择不连续或帧率/分辨率不一致会返回中文 400 |
| `GET /h3_lvm/uploads?project=<项目名>&output_size=<选项>&custom_max_side=<像素>` | 投放视频库的卡片：`{"project_name", "videos": [...]}` — 每条带 `segment_id`、`storage_name`、`original_name`、`thumbnail`、`cover_url`、`video_url`、`width`、`height`、`source_fps`、`variable_fps`、`duration_sec`、`has_audio`、`out_fps`、`size_bytes`、`browser_preview`，并按这个设置附带 `out_width` / `out_height` / `out_scaled`（运行时真正会解码出的尺寸）；在 ComfyUI 外面被删掉的文件不会让卡片消失，而是带 `missing_file: true` |
| `POST /h3_lvm/uploads/import` | multipart 表单，`project` 字段必须在 `file` **之前**；字节流式写入 `.upload_*` 临时文件，探测通过后才登记卡片 → 返回卡片记录。超过 2 GiB 返回 413；被拒绝或中断的上传不会留下索引幽灵，也不会留下半个文件 |
| `POST /h3_lvm/uploads/delete` | 请求 `{"project": <项目名>, "segment_id": N}` → `{"deleted": N}` — 只删这张卡片、它的文件和封面；后面的卡片编号依次顺延，库保持 1..N 连续；已经不在了返回中文 404 |
| `POST /h3_lvm/uploads/reorder` | 请求 `{"project": <项目名>, "order": [3, 1, 2]}` → `{"project": ..., "order": [1, 2, 3], "videos": N}` — 按给出的顺序把卡片重编号为 1..N，视频与封面不动；顺序和当前卡片对不上（缺号、多号、重复、不是列表）返回中文 400，索引保持不变 |

**WebSocket 事件** — 一次运行保存完片段后（`{"project": <库名>, "segments": [1, 2, ...]}`）和删除片段后（`{"project": <库名>, "deleted_id": N}`）和合并片段后（`{"project": <库名>, "merged_id": N}`）都会广播 `h3_lvm/changed`。`segments` 这个列表就是让 Manager 节点能准确显示自己这次运行的卡片，而不是从整库内容去猜。

`h3_lvm/uploads_changed` 只属于投放视频库
（`{"scope": "uploads", "project": <项目名>, "segment_id": N, "action": "import"|"delete"|"reorder"}`）。
导入、删除或重排投放视频都不会刷新裁切库的卡片，裁切库运行也不会碰投放视频的卡片区——两边听不同的事件。

---

### License

MIT