# H3 Smart Split — 源码审计（Phase 0）

对应企划书 §88 Phase 0 的 12 项交付物。审计范围：本仓库当前源码 +
`AIMixer/ComfyUI_MiniMaxH3_Director` 的真实 Smart Shot Split 实现。
本文只记录事实与结论，不含实现代码。

日期：2026-10-09 · 基线：`06a259a`（tag `v1.0.0`）· 快照：`archive/2026-10-08-06a259a/`

---

## 1. 当前 LVM Segment 数据流

```text
Load Video (IMAGE [F,H,W,C] float32 0-1) + optional AUDIO
        │
        ▼
comfyui/nodes.py  H3LongVideoManager.execute
        │  1. core/segmentation.compute_segment_duration_frames  秒 → 帧
        │  2. core/h3_grid.generate_fixed_segments               帧 → 逻辑区间（17n+5）
        │  3. comfyui/nodes._slice_and_scale / _slice_audio      张量切片（内存内）
        │  4. comfyui/segment_store.save_segment                 落盘 + 索引 + 缩略图
        │  5. server.PromptServer.send_sync("h3_lvm/changed")    通知前端
        ▼
output/h3-lvm/<project>/segNN/segNN.safetensors + segNN_first.png (+ segNN.mp4)
        │
        ▼
comfyui/nodes.py  H3SegmentPicker.execute → segment_store.load_segment → IMAGE + AUDIO
```

关键事实：**节点之间传递的是内存张量，不是文件**。`core/extraction.py` 走的是 PyAV 读文件那条路，
节点没有用它（见 §9）。因此任何「切点」都必须以**输入张量的帧号**表达，不能以文件帧号表达。

## 2. Fixed Segment 调用链

```text
H3LongVideoManager.execute
  → core/segmentation.compute_segment_duration_frames(duration_seconds, fps)
  → core/h3_grid.fixed_slice_frames(duration_frames, align_to_h3)
  → core/h3_grid.generate_fixed_segments(total_frames, slice_frames, context_frames)
      返回 [(start, end)]，正文区间首尾相接，末段取剩余且不吸附
  → core/h3_grid.is_valid_h3_frame_count(...)   仅用于日志断言
```

`WorkingVideoConfig.compute_working_dimensions()`（`core/models.py`）负责 `scale_percent` 的
宽高换算，被两个产出节点共用。

## 3. Extraction 调用链

节点侧（真实使用）：

```text
comfyui/nodes._slice_and_scale(video, start, end, target_w, target_h)   # 张量切片 + 可选缩放
comfyui/nodes._slice_audio(audio, start, end, fps)                     # 按帧号换算采样区间
comfyui/nodes._make_silent_audio / _pad_silent_audio                   # 缺音频时的等长静音
```

`core/extraction.extract_frames()` 是另一条路径：PyAV 打开视频文件 → 取帧 → `_resize`。
它服务于「只有文件、没有张量」的场景，节点没有调用它。Smart Split 也不调用它（原因见 §9）。

## 4. Store 调用链

```text
comfyui/segment_store.save_segment(project, seg_index_1based, video, audio, fps,
                                   save_mp4, save_dtype, meta)
  → sanitize_project_name / resolve_project / get_project_dir
  → _encode_video(video, save_dtype)  → int8 或 fp16
  → _save_tensors → safetensors
  → tensor_to_pil(首帧) → PNG 缩略图
  → _encode_mp4（可选）
  → _upsert_index → h3lvm_index.json（按 segment_id upsert，不清库）
读取：load_segment / load_project_index / list_project / list_projects_with_counts
删除：delete_segment / delete_project
```

`_upsert_index` 只按 id 覆盖，**不会清空整库**。这是 Smart Split 与 Fixed 混写时残留高编号片段的根因，
节点会打印 WARNING 提示（不自动删，删片段是用户和 Picker 的权利）。

## 5. Picker 调用链

```text
web/h3lvm_picker.js            卡片墙：GET /h3_lvm/segments?project=
web/project_menu.js            项目菜单（切换 / 新建 / 删除），写回 project_name widget
web/preview_overlay.js         MP4 预览弹窗
web/thumb_fit.js               缩略图方向自适应（竖屏整帧 + 模糊背景）
web/card_zoom.js               卡片大小 100%–400%
web/dom_panel.js               addPanel()：DOM widget 与 getMinHeight
comfyui/server_api.py          上述 5 个 HTTP 接口
```

Manager 面板 `web/h3lvm_manager_panel.js` + `web/h3lvm_manager.js` 复用同一批模块与同一份 CSS
（`web/h3lvm_picker.css`，`<link id="h3lvm-styles">` 只注入一次）。
**卡片只属于素材库（bin），不属于某个节点**——这是 §38「不要建第二套卡片系统」的依据。

## 6. Director Smart Split 调用链

真实源码：`lib/shot_detect.py`（8.2 KB），入口不是 ComfyUI 节点，而是 HTTP 路由：

```text
web/js/minimax_timeline.js（时间轴 UI）
  → POST /minimax/detect_shots
  → director/http_routes.py:424 minimax_detect_shots()
      读 body: frameRate / totalFrames / sensitivity / minShotFrames / clips[]
      先 scenedetect_available()，缺包直接返回 400 + 安装命令
  → lib/shot_detect.detect_timeline_shot_cuts(clips, frame_rate, total_frames, sensitivity, min_shot_frames)
      对每个 clip 调 detect_shots_in_file(path, sensitivity, min_scene_len_src)
      源帧号 → 逻辑时间轴帧号：_src_frame_to_logical()（按 nativeFps / timeline_fps 比例换算）
      再 _merge_close_cuts(min_gap=min_shot) 合并过近的切点，MIN_SEG_FRAMES = 4
  → lib/shot_detect.detect_shots_in_file()
      AdaptiveDetector(adaptive_threshold=阈值, min_scene_len=min_scene_len_src)
      detect(path, detector, show_progress=False, start_in_scene=True)   # 输入是文件路径
      返回 cuts（含 0 与 end_frame）+ meta{method, threshold, scene_count, sensitivity}
```

`_SENSITIVITY_THRESHOLD = {"low": 4.5, "medium": 3.0, "high": 2.0}`（注释：higher = fewer cuts）。
`scenedetect_install_hint()` 用 `sys.executable` 拼出当前解释器的 pip 命令；`scenedetect_available()`
只做 import 探测。这两个函数名与语义被本实现原样沿用。

与 LVM 的结构性差异（因此不能直接搬代码）：

| Director | LVM |
|---|---|
| 输入是磁盘上的视频文件路径 | 输入是节点上游的 IMAGE 张量 |
| 时间轴由多个 clip 拼接，需要 fps 比例映射 | 时间轴就是这张张量本身，`target_fps == fps`，1:1 |
| 切点结果给前端时间轴用（`cutFrames`） | 切点结果直接变成落盘片段 |
| 会 `_merge_close_cuts` 合并过近切点 | 不合并：检测说什么就切什么 |
| `min_shot_frames` 是第二个旋钮 | 只有 `detection_sensitivity` 一个旋钮 |

## 7. PySceneDetect 实际使用方式

Director：`from scenedetect import AdaptiveDetector, detect` + `detect(path, ...)`，
即高层 API，自己解码、自己按全分辨率分析。

本仓库（`core/smart_split.py`）：只能用低层 API，因为帧在内存里：

```text
from scenedetect.detectors import AdaptiveDetector
from scenedetect.frame_timecode import FrameTimecode
detector = AdaptiveDetector(adaptive_threshold=阈值)
for index, frame in 逐帧: detector.process_frame(index, bgr_uint8, FrameTimecode(index, fps))
cuts = detector.post_process(FrameTimecode(total, fps))
```

- 阈值三档与 Director 完全一致（4.5 / 3.0 / 2.0），`min_scene_len` 用库默认（15），不额外暴露。
- 分析前把帧降到长边 ≤ `DETECT_MAX_SIDE = 256`（`analysis_size()`），因为 1080p 全分辨率逐帧
  差分在 CPU 上慢一个数量级；切点帧号仍是原张量帧号，降分辨率只影响检测灵敏度。
- 懒导入：`scenedetect` 只在 `detect_scene_cuts()` 里 import。缺包时抛 `ImportError`，
  文案里带 `scenedetect_install_hint()` 的 pip 命令；插件其余部分照常加载。
- 兼容 0.6 / 0.7：`post_process` 的签名差异通过 `FrameTimecode` 适配，不假设具体版本。

## 8. 可复用函数

| 复用 | 位置 | 用途 |
|---|---|---|
| `_slice_and_scale` / `_slice_audio` / `_make_silent_audio` / `_pad_silent_audio` | `comfyui/nodes.py` | 切片与音频，Smart Split 直接调用，不复制第二份 |
| `save_segment`（含 `thumbnail_frame`） | `comfyui/segment_store.py` | 落盘、缩略图、索引 |
| `load_project_index` | `comfyui/segment_store.py` | 混写残留检测 |
| `normalize_save_dtype` | `comfyui/segment_store.py` | int8 / fp16 开关 |
| `WorkingVideoConfig.compute_working_dimensions` | `core/models.py` | `scale_percent` 尺寸计算 |
| `createProjectMenu` / `addPanel` / `openPreview` / `appendThumbnail` / `createCardZoom` | `web/*.js` | 前端只写一个面板，其余全部复用 |
| `GET /h3_lvm/projects`、`/h3_lvm/segments`、`h3_lvm/changed` | `comfyui/server_api.py` | 不新增任何接口 |
| `scenedetect_install_hint` / `scenedetect_available` 的语义 | Director `lib/shot_detect.py` | 缺包提示与探测 |

`save_segment` 唯一的新增参数是 `thumbnail_frame`（默认 0，行为不变）。Smart Split 传
`context_frames`，保证卡片封面是**正文首帧**而不是 MC 重叠帧。

## 9. 不可复用函数

| 不复用 | 原因 |
|---|---|
| `core/h3_grid.py` 全部（`align_down/up_to_h3_grid`、`fixed_slice_frames`、`generate_fixed_segments`、`generate_aligned_segments*`） | Smart Split 的定义就是不做 17n+5 对齐、不做定长切段。`core/smart_split.py` 不 import `h3_grid`，这一点由 `tests/test_node_schema.py` 与 `tests/test_smart_split_core.py` 双向锁住 |
| `core/segmentation.compute_segment_duration_frames` | 没有「每段时长」这个输入 |
| `core/extraction.extract_frames` | 它打开文件；Smart Split 的帧已经在内存张量里，再解码一次会引入第二套帧号与色彩路径 |
| `core/person_crop.crop_video_to_person` | 人物裁切会改变帧数与画面，与「按检测原样保存」冲突；第一版不提供 |
| `core/manifest.build_manifest` | 面向 Fixed 的连续性报告，Smart 的区间不规则，硬套会误导 |
| Director 的 `detect()` 高层 API、`_src_frame_to_logical`、`_merge_close_cuts` | 见 §6 的差异表 |

## 10. 需要新增文件

```text
core/smart_split.py                 检测 + 边界 → 逻辑区间（唯一的新逻辑）
tests/test_smart_split_core.py      核心：边界归一化、无损、MC、降分辨率、缺包提示
tests/test_smart_split_node.py      端到端：张量边界、落盘、封面、segment_id、越界
web/h3lvm_smart.js                  中文标签 + 项目菜单面板
requirements.txt                    可选依赖声明（只有 Smart Split 用到）
SMART_SPLIT_AUDIT.md                本文
```

## 11. 需要修改文件

```text
comfyui/nodes.py            新增 H3SmartSplit；NODE_LIST 注册；复用既有 helper
comfyui/segment_store.py    save_segment 增加 thumbnail_frame（默认 0，旧行为不变）
tests/test_node_schema.py   注册与输入顺序锁定；禁止 Fixed 专属参数泄漏；MC 默认 0
tests/test_segment_store.py thumbnail_frame 的默认 / 生效 / 越界 clamp
README.md                   中英文 Smart Split 段落、可选依赖、目录结构
VERSION.md                  本轮基线说明
```

## 12. 不修改文件

```text
core/h3_grid.py            core/segmentation.py    core/extraction.py
core/manifest.py           core/models.py          core/person_crop.py
comfyui/server_api.py      comfyui/asset_paths.py
web/h3lvm_picker.js        web/h3lvm_manager.js    web/h3lvm_manager_panel.js
web/h3lvm_picker.css       web/project_menu.js     web/preview_overlay.js
web/thumb_fit.js           web/card_zoom.js        web/dom_panel.js
```

不修改 `h3lvm_picker.css` / `project_menu.js` 是刻意的：Smart Split 的面板必须与已实测通过的两个
面板长得一模一样，改共享文件等于把已验证的 UI 重新置于风险中。

---

## 结论（写下来就不再摇摆）

1. 检测跑在**节点输入的内存张量**上，`total_frames = video.shape[0]` 是无损基准；不读文件、不二次解码。
2. 主段半开区间必须 `first.start == 0`、`last.end == total`、首尾相接；无切点 = 1 段，是合法结果不是错误。
3. 不做：H3 对齐、补帧、丢帧、合并短镜头、限制最大长度、自动 MC、独立 Store/Picker/Extraction、新 server API。
4. `detection_sensitivity` 是唯一的检测旋钮（与 Director 同值三档），其余行为不可被用户隐式改变。
5. Smart Split **不调用 H3 Grid**。