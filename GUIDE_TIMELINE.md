# H3 Guide Timeline — 开工调查（P0）与接口核对

日期：2026-10-22　对应计划书：H3-Guide-Timeline-Plan v1.0
本文件是实施前的源码核对记录，也是这个节点的接口说明。所有结论都来自本机实际安装的源码，
不是聊天里的记忆。

## 1. 环境

- ComfyUI `0.42.4`（`comfyui_version.py`），前端 `comfyui_frontend_package 1.55.18`。
- 本仓库：`H3-Long-Video-Manager`（V3 `ComfyExtension` 入口，`comfy_entrypoint()` 注册路由 + `NODE_LIST`）。
- 现有节点：`H3LongVideoManager` / `H3SmartSplit` / `H3SegmentPicker` /
  `H3 Image Reference Loader` / `H3 Audio Reference Loader`（`comfyui/nodes.py:796`）。
  新节点不改它们的接口，只追加到 `NODE_LIST`。

## 2. 原生 Add Guide（唯一被复用的原生实现）

`E:\ai\ComfyUI-aki-v3\ComfyUI\comfy_extras\nodes_minimax_h3.py:166` `MiniMaxH3AddGuide`：

```
execute(cls, positive, latent, frame_idx, vae=None, audio_vae=None, image=None, audio=None)
```

- `latent["samples"]` 必须是 H3 的 AV NestedTensor；`tensors[0]` 是 `[B,24,T,H/16,W/16]`。
- 总帧数：`sum(FRAME_PER_TOKEN[k % 5] for k in range(video.shape[2]))`，
  `FRAME_PER_TOKEN = (1, 4, 4, 4, 4)`（`comfy/ldm/minimax/model.py:30`）。
  等价于 `align_frame_count()` 的逆运算：latent_t=2 → 5 帧，之后每 +5 个 latent 帧 +20 像素帧。
- 图片：`guide_frames = image.shape[0]`；`<5` 时只用第一帧（=1），否则向下取到 `17n+5`。
  需要 `vae`，`_resize(..., "center")` 到 latent 画布后 `vae.encode`。
- 时间位置：`resolved_frame_index = frame_idx if frame_idx >= 0 else frame_count + frame_idx`；
  越界直接报错（单帧和片段是两条不同的错误文案）。
- 音频：需要 `audio_vae`；`_encode_ref_audio` 先重采样到 `audio_vae.audio_sample_rate`（默认 32000），
  编码成 `[1,32,2,T]`，然后把**尾部**裁到 `max_rt = floor(audio_total_rt - FRAME_RESCALE * resolved_frame_index)`，
  `FRAME_RESCALE = 5/3`（= 40/24，音频 latent 40 帧/秒 vs 视频 24 帧/秒）。
  也就是说原生节点只裁尾，**源音频的起止点必须由调用方在编码前自己切**。
- 累积：`keyframes = list(positive[0][1].get("minimax_keyframes", []))` → append → `conditioning_set_values`。
  `conditioning_set_values` 只做浅拷贝（`c.copy()` 后直接 `c2[1].update(...)`），
  **会写回输入 conditioning 的同一个 dict**。所以本节点先深拷贝一层再接链，避免污染上游/其他分支。
- 消费端：`comfy/model_base.py:2234` 把 `minimax_keyframes` 放进 `payload["keyframes"]`，
  `comfy/ldm/minimax/model.py:377`（`PackedLayout`）按**列表顺序**打包，时间位置由
  `cond_t = cursor + FRAME_RESCALE * resolved_frame_index` 决定。
  → 位置由 frame_index 决定，但打包顺序由列表顺序决定，所以「导入顺序不同、时间顺序相同」
  必须先按 frame_index 归一化排序才谈得上等价。本节点按 (frame_index, 图片优先, 原列表次序) 排序。

## 3. 本节点的接口（实现后）

- node_id `H3 Guide Timeline`，display_name `H3 Guide 时间轴`，category `H3/Guide`。
- 输入：`positive`(Conditioning)、`latent`(Latent)、`length_seconds`(Float, 可选)、`vae`(Vae, 可选)、
  `audio_vae`(Vae, 可选)、`guides`(String JSON)。`length_seconds` 只给编辑器的时间尺用，单位是秒
  （与 `H3 Long Video Manager` 的 `segment_duration` 同一套习惯），换算成帧并向上对齐 17n+5，不参与执行。
  除此之外没有别的控件：`resolved_frame_count` 与 `view_state` 都存在 `guides` 这一个 JSON 文档里
  （为什么这样做见 §5）。
- 输出：`positive`(Conditioning) 一个。
- 不暴露 `guide_list` 插口：当前没有任何生产 `guide_list` 的节点，先保留内部合并点（`core.guide_timeline.merge_guides`）。
- 执行：解析 → 过滤停用/待放置 → 空列表原样透传 → 由 latent 解析真实总帧数 → 全量校验 →
  排序 → 逐条调用原生 `MiniMaxH3AddGuide.execute` 累积 → 返回最后的 positive。
- 摘要通过 `io.NodeOutput(positive, ui={"h3_guide_timeline": [{...}]})` 回传：
  `execution.py:386` 允许 dict，`enrich_output_with_media_metadata` 只处理带 filename/type 的条目，
  自定义键原样透传，前端用 `api.addEventListener("executed", ...)` 读取。

## 4. 复用点与不重复造的东西

- 素材路径规则、`/view` 解析、越界路径拒绝：`core/ref_media.py`（`resolve_media_path`、`ALLOWED_TYPES`）。
- 图片解码：`comfyui/ref_nodes.py` 的写法（EXIF、丢 alpha、[1,H,W,3] 0..1），但**不预缩放**——
  原生 Add Guide 自己 `_resize` 到 latent 画布，预缩放只会二次损失。
- 音频解码：`comfy_extras.nodes_audio.load`（和 LoadAudio 同一个解码器）。
- 前端：`web/h3lvm_picker.css` 的共享外壳类、`card_zoom.js` 的 100–400% 档位、
  `ref_loader.js` 的 `/upload/image` 上传与 AudioContext 解码/波形画法。
- 不新增后端路由：上传走 ComfyUI 自带的 `/upload/image`，预览走 `/view`，波形在前端解码。

## 5. 与计划书的有意偏差（都写进代码注释，不是遗漏）

| 计划书里的写法 | 本实现 | 原因 |
|--------------|--------|------|
| 每条 Guide 用 `asset_id` 间接引用一张 asset 表 | 直接在条目里存 `asset{filename, subfolder, type}` | 本插件的素材身份本来就是 ComfyUI 的三元组（`core/ref_media.py` 的 `/view` 与路径安全检查、两个参考加载器都是这个写法）。再加一层 id 表只会多一个可能和磁盘不一致的缓存，而「素材丢失」需要的是能直接看见的路径 |
| 文档里 `fps` 可配 | 固定 `DEFAULT_FPS = 24`，字段保留 | 原生 Add Guide 的 `FRAME_RESCALE = 5/3` 就是按 40/24 写死的；把 fps 变成用户可调会让音频长度与 `max_rt` 的换算出现一个原生根本不支持的自由度。字段留着是为了以后真的支持时旧文档能自解释 |
| 面板状态可以另存 | `view_state`（选中项 / 当前 tab / 缩放 / 滚动）与 `resolved_frame_count` 内嵌在同一个 `guides` JSON | 只有一个 widget 才能靠 `configure()` 按位置恢复；多一个 widget 会改变已有工作流的控件位置，而这两项都不参与执行（`fingerprint_inputs` 只哈希列表内容 + 文件真实字节，所以挪滑块不会重新编码 30 条 Guide） |
| 可选的 `guide_list` 插口 | 不公开，合并点留在 `core.guide_timeline.merge_guides` | 计划书 §4 自己说「没有可测试的生产节点就先不公开无用插口」。本插件没有任何节点生产 `guide_list` |
| 待放置项可以单独一区 | 用卡片角标「待放置」，仍在同一个网格里 | 卡片区顺序 = 列表顺序 = 拖拽换序的对象；再分一个区就会出现「拖到哪算哪个顺序」的歧义，而这是本插件已经付过学费的地方 |
| 撤销/重做 | 未接 | 一次拖动 = 一次 `writeDoc`，粒度已经和 LiteGraph 的历史不同；接进宿主历史需要 widget 级的事务，属于下一版 |
| 拖出范围可以「保留越界」或「限制在范围内」 | 拖动限制边界；数值输入允许越界并保留 + 底栏报错 | 计划书要求两种策略选一种并一致记录。鼠标拖是「我要放这里」，钳制更符合直觉；手填数字是「我知道我在填什么」，保留并报错比偷偷改掉诚实 |

## 6. 实现现状与验证边界（2026-10-22）

- 已实现：`core/guide_timeline.py`（规范化 / 校验 / 排序 / 配额 / 摘要 / 指纹，纯 Python，不 import torch）、
  `comfyui/guide_nodes.py`（`H3GuideTimeline`，原生节点懒解析：本机没有 `MiniMaxH3AddGuide` 时只有这个节点报错，
  插件其余部分照常加载）、`web/guide_state.js`（同一套规则的 JS 镜像 + 时间轴几何 + 节点内时间轴的纯函数
  `stripRoom` / `stripLaneHeights` / `stripMarkerPlan`）、`web/guide_timeline.js`（**一个渲染器两个 surface**：浮层编辑器的
  `editorSurface` 与节点内的 `nodeSurface`，后者按宽度铺满、marker 与音频条同样可拖）、`web/guide_timeline.css`。
- 自动化：`tests/test_guide_timeline_core.py` 37 项、`tests/test_guide_nodes.py` 29 项（含与显式串联原生节点的张量等价比较），
  全套 `Ran 529 tests ... OK`；前端纯函数 `work/guide_state.test.mjs` 89 项全绿。
- 轨道与卡片的大小只有一套控制：`view_state.lane_heights`。卡片是正方形，边长 = **实际生效**的轨道高度 − `MARKER_INSET*2`，
  所以「轨道高度」和「卡片大小」是同一个数字，两处（浮层编辑器的轨道头、节点内时间轴的头部）改的是同一份 view state。
  节点面板自己拥有高度，所以那里的高度是一个请求：`stripLaneHeights` 会把两条轨道按比例一起缩到面板放得下（各自不低于
  `STRIP_LANE_MIN`），读数显示实际生效值并在被夹住时变琥珀色；完全放不下时整条时间轴自己隐藏，绝不写 `node.size`。
  多条卡片时真正的限制是 fit-to-width 的宽度预算（`stripMarkerPlan`），不是任何固定尺寸。
- 未验证（必须用户实测）：真实 ComfyUI 里的面板交互与计划书 D 章要求的四种截图（完整布局 / 选中编辑音频 / 冲突定位 / 窄宽度），
  以及节点内那条时间轴（把节点拉高才出现，默认 112px 节点高度下不显示，这是设计而不是 bug）。
  浏览器端没有 DOM 测试环境，所以「拖拽、试听、缩放、保存重开」只能算已实现、未实测。