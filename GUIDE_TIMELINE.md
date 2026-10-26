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
- 弹窗的轨道与卡片大小共用 `view_state.lane_heights`。卡片是正方形，边长 = **实际生效**的轨道高度 − `MARKER_INSET*2`。
  节点内时间轴另有可选的 `view_state.strip_marker_side`：用户点「卡片 − / ＋」后才写入，范围 40–320px、步进 16px；
  此后卡片不再随轨道高度、节点宽度或卡片数量改变，只随这个控件改变。未设置时仍走旧的自动尺寸，旧工作流显示不变。
  节点面板自己拥有高度，所以那里的高度是一个请求：`stripLaneHeights` 会把两条轨道按比例一起缩到面板放得下（各自不低于
  `STRIP_LANE_MIN`），读数显示实际生效值并在被夹住时变琥珀色；完全放不下时整条时间轴自己隐藏，绝不写 `node.size`。
  自动模式下多条卡片的限制是 fit-to-width 的宽度预算（`stripMarkerPlan`）；独立尺寸模式由 `stripCardPlan` 固定边长。
  `stripLaneHeights` 不读取卡片边长，所以两个控件双向独立。大卡片可超出图片轨层叠显示，但不会撑高轨道；
  最外层面板仍按节点真实边界裁切。
- 未验证（必须用户实测）：真实 ComfyUI 里的面板交互与计划书 D 章要求的四种截图（完整布局 / 选中编辑音频 / 冲突定位 / 窄宽度），
  以及节点内那条时间轴（把节点拉高才出现，默认 112px 节点高度下不显示，这是设计而不是 bug）。
  浏览器端没有 DOM 测试环境，所以「拖拽、试听、缩放、保存重开」只能算已实现、未实测。
## 7. v2：逐张图片引导强度（2026-10-23）

- 两个节点：`H3 Guide Timeline`（稳定版，未改动）与 `H3 Guide Timeline v2`（`H3GuideTimelineV2`，
  继承旧类，只改 `define_schema()` 里的 node_id / display_name / description / tooltip 和强度路径）。
  旧工作流不会自动迁移，两个节点可以同时存在。
- 数据：v2 的图片条目多一个 `strength`（0.00-1.00，步进 0.05，缺字段按 1.00 读）。三档语义：`1.00` = 原生路径；
  `0.05-0.95` = 逐图强度；`0.00` = 卡片、时间位置和强度值都留在文档里，但这张图不 VAE 编码、不进 conditioning、不新增 keyframe。
  两个 VAE 端口和接线方式不变，可以一直连着：执行时按实际生效的素材决定调用哪个，全是 `0.00` 图片时不要求连接视频 VAE，
  没有任何生效 Guide 时 positive 原样透传。`schema_version` 仍是 1，
  `strength` 键本身就是 v2 文档的标记；v1 的解析、序列化、执行摘要与缓存指纹逐字节不变
  （`tests/test_guide_timeline_core.py` 里有一条硬编码哈希守卫）。共用纯函数用版本明确的包装：
  `parse_guides_v2` / `serialize_guides_v2` / `execution_digest_v2` / `guide_fingerprint_v2` / `has_reduced_strength`。
- 强度为什么不能只调全局值：原生 H3 只有一个全局 `visual_cond_noise_aug`，串联几个全局设置得不到逐图强度，
  把 latent 直接乘以强度也不是同一件事。原生 `_cond_video_rows` 对每个视觉条件都用
  `aug * r + (1 - aug) * noise`（`aug` 默认 `VISUAL_COND_TIMESTEP = 0.999`），并且 `_forward` 给所有视觉条件行
  打同一个时间标签。机制参考 ComfyUI-H3Studio 的 `h3_studio.py` / `extra_conds_patch.py` / `h3_row_aug_patch.py`，
  只借图片 Guide 需要的最小部分。
- 生效路径（`comfyui/h3_strength_patch.py`，不改 ComfyUI 内核文件）：
  1. 节点在每次调用原生 `MiniMaxH3AddGuide.execute` 前记下已有 keyframe 的身份，调用后按「新增的那一个」写入
     `noise_aug = round(strength * VISUAL_COND_TIMESTEP, 6)`，并用同一系数把该 keyframe 的 latent 向噪声混合
     （种子按锚定帧 `frame_index` 固定，可复现；用槽位序号会让「把某张卡改成 0.00」连带改变别的卡的噪声）。
     卡片序号从不被当成 keyframe 序号：输入 `positive` 可能已有首尾帧或别的 Guide，
     普通参考图也不是 keyframe。若这次新增的不是恰好一个，直接中文报错，不猜。
  2. 类级改写 `MiniMaxH3Model._cond_video_rows`（带自己强度的条件不再二次加噪）与 `_forward`（按块生成时间标签，
     使加噪强度与时间标签始终一致）。安装前比对 `_cond_video_rows` 源码与 `_forward` 的两处锚点，装完跑一次
     自检（每条 packed segment 一个标签、标签都能索引到调制表；没有任何强度时标签必须与今天完全一致）。
  3. 只有本次 v2 执行里存在 `0.05-0.95` 的图片才安装补丁；`1.00` 完全不碰模型，`0.00` 连编码都不做，也不需要补丁。
     锚点不符、编译失败、
     自检不过，或检测到别的插件（`_guide_row_aug`，ComfyUI-H3Studio）已经改写过同一批方法 → 不安装，
     v2 低强度运行明确报错；旧节点与 v2 的 1.00 路径不受影响。补丁是进程级的，所以没有 v2 参数的普通 H3
     工作流必须保持原样——这一条由自检和 `tests/test_h3_strength_patch.py` 守。
- 自动化：`tests/test_h3_strength_patch.py` 21 项、`tests/test_guide_nodes.py` 51 项（两个节点 ID 与接口、
  多图不同强度且输入已有 keyframe 时对应正确、全 1.00 与旧节点张量等价、`0.00` 不解码不编码也不新增 keyframe、
  只有 `0.00` 时不接视频 VAE 也照常透传、适配被拒绝时报错而旧节点照常）、
  `tests/test_guide_timeline_core.py` 54 项；前端 `work/guide_state.test.mjs` 100 项（取整与 Python 一致）。
  全套 23 个模块 589 项，只有 `tests/test_ref_media.py:196` 那条「写根目录外应被拒绝」的探针在本沙箱里报
  PermissionError（环境限制，不是实现问题）。
- 未验证（必须用户实测）：0.80 / 0.60 / 0.00 对成片画面的实际影响、卡片上强度徽标与详情编辑的手感；
  本机没有安装 ComfyUI-H3Studio，所以「与它共存」只有代码层的拒绝路径，没有实测。

## 8. v2 双通道：一采与二采（2026-10-25）

- v2 新增 `positive`（一采 A）与 `positive_b`（二采 B）两个可选 conditioning 输入，以及对应的两个输出。
  后续新增可选 `latent_b`（二采 B）：两个通道共用时间轴、视频 VAE 与音频 VAE，但分别在自己的 AV latent 上
  读取宽高、视频帧数与音频轨长度，并在各自的上游 conditioning 上调用原生 Add Guide；不合并两条条件链，
  也不把一采新增的 keyframe 写进二采。`latent_b` 未连接时回退到一采 `latent`，兼容已有双通道工作流。
- **激活一采 Guide**（`enable_a`）默认开启，**激活二采 Guide**（`enable_b`）默认关闭，因此既有 v2 工作流仍只执行一采。
  每个开关同时控制该通道的 positive 与 latent：停用后不校验 latent、不校验或编码 Guide，其输入 positive 原样透传；
  只用二采时一采 positive 与 latent 都可留空。两个开关计入 v2 执行指纹，latent 本身仍由 ComfyUI 的正式输入缓存键管理。
- 每个素材每个通道只解码一次媒体文件，但激活两个通道时会分别调用原生 VAE 编码，计算量按通道数增加。
  逐图强度仍只标记该通道本次新增的图片 keyframe，音频、上游条件和稳定版 v1 的行为不变。
- 自动验证：`tests/test_guide_nodes.py` **60 项**，完整既定 Python 入口 **661 项，0 跳过**；
  新增独立 latent 尺寸编码、仅二采无一采 latent、分通道长度校验与停用二采忽略无效 latent 的回归覆盖。
  真实 ComfyUI 的双通道端口、开关手操与双采样成片仍需用户验收。

## 9. 串行二采：共享文档与独立执行节点（2026-10-26）

- 真实日志确认：同一个 v2 节点若一边向一采输出 conditioning，另一边又接收依赖一采采样 / 放大结果的
  二采输入，ComfyUI 会按整个节点建立依赖图并形成环。开关只控制执行，不能删除已连接输入的图依赖。
- 现有 `H3 Guide Timeline v2` 的 ID、一采 / 二采接口和执行保持兼容，追加 `共享 Guide 文档` STRING 输出。
  新增 `H3 Guide Timeline v2 B`（显示名「H3 Guide 时间轴 v2（二采）」）：只有独立的二采 positive、latent、
  VAE 与一个 positive 输出，执行和缓存均不依赖一采节点的 conditioning 或 latent。
- 一采 v2 的共享文档输出连接独立二采节点的 `shared_guides` 后，后端以该文档执行，前端两个编辑器直接
  读写一采节点的同一个 guides widget；任一节点编辑都会同步其他已连接节点。未连接时二采节点使用自己的文档，
  也可单独作为普通 v2 执行节点。文档连接只从一采流向二采，不形成反向依赖。
- 当前串行工作流接线：一采 v2 的 A 输出仍接一采 Motion Context；新增独立二采节点接收二采 Reference to Video
  的 positive / LATENT，输出接二采 Motion Context；再连接两个节点的「共享 Guide 文档」。不要再把二采
  Reference to Video 接回一采 v2 的旧 `positive_b` / `latent_b`，旧通道仅用于两路输入相互独立的并行流程。
- `fingerprint_inputs` 现在接受并忽略 `length_seconds` 等视图参数；共享文档的内容与素材字节仍决定执行指纹，
  视图状态不改变指纹。独立二采支持逐图强度、0.00 不编码、旧文档读取和只连接共享文档时的本地文档回退。
- 自动验证：Guide 节点专项 **64/64**，完整既定 Python 入口 **665/665，0 跳过**；共享链接前端专项 **6/6**、
  原 Guide 状态 **106/106**，20 个 `web/*.js` 语法检查全部通过。真实 ComfyUI 的依赖环、编辑器同步与成片仍需用户验收。

## 10. 当前接口：一采单通道与二采信息传输（2026-10-26）

本节取代第 8、9 节中的双通道与双编辑器接口说明；那两节只保留为开发历史。

- `H3 Guide Timeline v2` 的节点 ID 不变，但已删除 `positive_b`、`latent_b`、二采 positive 输出及
  `enable_a` / `enable_b`。现在只有一组 `positive / latent`、一个 positive 输出和一个「共享 Guide 文档」输出。
  共享文档固定位于输出槽 1，positive 固定位于输出槽 0。
- `H3 Guide Timeline v2 B` 的节点 ID 不变，显示名改为 **H3 Guide 时间轴 v2（二采信息传输）**。
  输入依次为二采 positive、二采 latent、`shared_guides`、视频 VAE、音频 VAE、`enable_guide`；输出只有二采 positive。
- 二采信息传输节点没有编辑器、时间轴、本地 `guides` 或 `length_seconds`。唯一内容来源是一采 v2 的共享文档；
  开启开关但未连接共享文档时给出中文错误。关闭开关时在文档解析、latent 校验和 VAE 编码之前直接透传 positive。
- 二采仍复用 v2 的图片强度、0.00 跳过编码、音频处理和原生 Add Guide 链。开关与共享文档共同计入缓存指纹，
  视图状态不参与指纹。稳定版 v1 的节点 ID、接口、文档和执行路径不变。
- 这次端口删减会改变旧工作流的槽位契约。彻底重启 ComfyUI 并 `Ctrl+F5` 后，需要重接相关连线；旧连线若引用
  已删除的输出槽，会在 ComfyUI 校验阶段报 `list index out of range`，这不是 VAE 或 Guide 素材错误。
- 自动验证：Guide 节点专项 **56/56**，完整 Python 入口 **657/657，0 跳过**；Guide 前端状态 **106/106**，
  20 个 `web/*.js` 语法检查全部通过。运行副本独立进程已核验三个节点的真实 schema；浏览器重接、手操与成片由用户验收。

## 11. V3 RETURN_TYPES 继承缓存修复（2026-10-26）

- 真实 prompt 中二采传输节点的 `shared_guides` 已正确连接 v2 输出槽 1，但执行器仍报 `list index out of range`。
  按节点加载顺序复现发现：v2 schema 有两个输出，实际 `RETURN_TYPES` 却继承 v1 的一个输出。
- 原因是 ComfyUI V3 的输出缓存通过类属性保存；父类初始化后，子类读取到非空的继承缓存，跳过自己的输出初始化。
  `object_info` 直接展示 schema，所以网页看到的两个输出与执行器看到的一个输出不一致。
- v2 和二采传输节点现在分别初始化自己的输出缓存。真实加载顺序下：v1 为 `['CONDITIONING']`，v2 为
  `['CONDITIONING', 'STRING']`，二采传输节点为 `['CONDITIONING']`。已经接正确的共享文档线不需要重接。
- 自动验证：Guide 专项 **57/57**，完整 Python 入口 **658/658，0 跳过**；Guide 前端状态 **106/106**，
  20 个 `web/*.js` 语法检查全部通过。真实 ComfyUI 重启后的原工作流由用户验收。

## 12. 已连接共享文档的校验阶段语义（2026-10-26）

- ComfyUI 的输入校验先于上游执行。已连接的 `shared_guides` 在这个阶段尚未有字符串值，读为 `None`
  不代表用户没有连接，不能据此拒绝输入。
- 二采传输节点因此在 `shared_guides is None` 时不在自定义校验中报错；真正未连接时，`execute` 仍会
  明确提示连接共享文档或关闭二采 Guide。实际文档字符串可用时仍会做格式解析。
- 使用真实 Guide 文档和真实节点类，通过 ComfyUI 原 `execution.validate_inputs` 重放同样的共享链接，
  结果为 `GUIDE_B_VALID True`、`GUIDE_B_ERRORS []`。完整 Python 回归 **658/658，0 跳过**，
  Guide 专项 **57/57**，前端状态 **106/106**。未把该结果当作完整两采成片验收。
