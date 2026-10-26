# 版本说明（VERSION.md）

> 版本铁规：每次改动前，把旧版本完整快照存入 `archive/<日期>-<commit 短 hash>/`，并在本文件顶部追加一条说明。
> 只有用户的明确命令才能删改 `archive/` 中的旧版本。

## 2026-10-26 · Guide v2 移除空状态 VAE / 透传提醒（提交并推送 main）

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-26-b6cab67-guide-v2-empty-note` 保存本轮前完整开发树（108 个源码/文档/测试文件，逐文件哈希 `mismatch: 0`）。
- 按用户反馈，从 `H3 Guide Timeline v2` 节点底部删除「无需 VAE · 无生效 Guide · positive 原样透传」绿色提醒。没有生效 Guide 时不再显示这条状态行；有 Guide 时的 VAE 摘要、编排校验通过、待确认与错误提示仍保留。
- 仅改 `web/guide_timeline.js` 的展示分支，不改 v1/v2 节点 ID、接口、Guide 文档、VAE 调用、空 Guide 透传、双通道开关或执行行为。Guide 前端状态 **106/106 通过**，20 个 `web/*.js` 语法检查 0 失败，目标空状态文案无残留；本轮未重复执行 Python 全量回归。
- 已同步运行副本，108 个开发/运行文件 `mismatch: 0`、`stale: 0`。仅前端与文档变化，`Ctrl+F5` 后验收，无需重启 ComfyUI；本轮由用户明确要求提交并推送 `origin/main`，不创建 tag。

## 2026-10-25 · Guide 双通道与参考加载器更新打包提交

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-25-pre-push-guide-dual-ref-ui` 保存打包前完整开发树（188 个源码/文档/测试文件，逐文件哈希 `mismatch: 0`）。远端 `origin/main` 已 fetch 核对，仍为 `805ae7e`，没有需要合并的新提交。
- 打包范围：Guide Timeline v2 一采 / 二采双通道与独立开关、节点时间轴状态和强度界面优化、移除帧数推算提示；图片与音频参考卡片自定义名称、项目预设保存后的卡片数量即时刷新，以及对应文档和测试。稳定版 Guide v1、裁切算法、Motion Context 与其他节点行为不在本轮新增改动范围内。
- 验证基线：完整既定 Python 入口 **658/658 通过，0 跳过**；Guide 前端状态 **106/106**、参考前端状态 **49/49**，20 个 `web/*.js` 语法检查全部通过。真实 ComfyUI 视觉、手操与双采样成片按各条记录由用户验收。
- 本次由用户明确要求提交并推送 `origin/main`，不创建新 tag。下列 2026-10-25 条目中的「未提交 / 不提交、不推送」是各轮开发当时的记录，均随本次打包进入 `main`，不表示仍然躺在本地。

## 2026-10-25 · Guide Timeline v2 一采 / 二采双通道（未提交）

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-25-pre-guide-v2-dual-channel` 保存本轮前完整开发树（188 个源码/文档/测试文件，逐文件哈希 `mismatch: 0`）。
- `H3 Guide Timeline v2` 新增一采 A / 二采 B 两个可选 `positive` 输入与对应输出，共用原时间轴、latent 和 VAE，但分别在各自上游条件链调用原生 Add Guide。**激活一采 Guide** 默认开启、**激活二采 Guide** 默认关闭，保持现有 v2 工作流的单通道行为；停用通道原样透传，只用二采时一采可留空，两个开关计入执行指纹。稳定版 v1 的节点 ID、schema、输出与执行路径不变。
- 两个通道激活时媒体文件仍逐个读取，但每个通道分别进行原生 VAE 编码；逐图强度分别标记该通道本次新增的图片 keyframe，音频与上游条件保持原生行为。同步更新 README 与 Guide 接口文档。
- 自动验证：Guide 节点专项 **57/57 通过**；新增双通道独立上游条件、图片与音频双路执行、单路开关与透传、仅二采无一采输入、激活通道缺 positive 中文报错、双路停用不校验不编码、开关缓存指纹断言。完整既定 Python 入口 **658/658 通过，0 跳过**。真实 ComfyUI 端口显示、开关手操和双采样成片由用户验收；不提交、不推送、不创建 tag。
- 已同步运行副本 `E:\ai\ComfyUI-aki-v3\ComfyUI\custom_nodes\H3-Long-Video-Manager`：108 个开发/运行文件，`mismatch: 0`、`stale: 0`。本轮修改 Python schema 与执行代码，必须彻底重启 ComfyUI 后 `Ctrl+F5`，仅刷新页面不会加载双通道。

## 2026-10-25 · 保存参考预设后刷新项目卡片数量（未提交）

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-25-pre-ref-preset-menu-refresh` 保存本轮前开发树（197 个可读文件，逐文件哈希 `mismatch: 0`；沙箱拒绝访问的 `.tmp_tests` 临时目录未计入）。
- 图片与音频参考加载器保存项目预设成功后，除重新读取当前预设外，同时刷新项目素材库选单，使当前项目及下拉选项立即显示真实卡片数量，不再保留旧的「（空）」。预设内容、保存格式、卡片状态和节点执行行为不变。
- 自动验证：参考前端状态 **49/49 通过**，20 个 `web/*.js` 语法检查全部通过。本轮仅一行前端刷新修复，未重复执行 Python 全量回归；真实 ComfyUI 保存与选单显示由用户验收。不提交、不推送、不创建 tag。

## 2026-10-25 · 图片与音频参考卡片自定义名称（未提交）

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-25-pre-ref-card-labels` 保存本轮前完整开发树（188 个文件，逐文件哈希 `mismatch: 0`）。
- H3 图片参考加载器与 H3 音频参考加载器的每张卡片新增名称输入框。可选 `label` 随工作流和项目预设保存；留空继续使用随槽位变化的默认「参考图 N / 参考音频 N」。替换素材、拖动、跳过/放回均保留名称，`ref_image_N` / `ref_audio_N` 接口编号与输出行为不变，名称不进入解码缓存指纹。
- 自动验证：参考加载器 Python 专项 **110/110 通过**，前端状态 **49/49 通过**；完整既定 Python 入口 **652/652 通过，0 跳过**（新增 3 条名称解析、预设与缓存断言），20 个 `web/*.js` 语法检查全部通过。差异核对仅名称功能相关 8 个代码/测试文件和 `VERSION.md` 发生变化。真实 ComfyUI 输入体验、布局与手操由用户验收；不提交、不推送、不创建 tag。
- 已同步运行副本 `E:\ai\ComfyUI-aki-v3\ComfyUI\custom_nodes\H3-Long-Video-Manager`：108 个开发/运行文件，`mismatch: 0`、`stale: 0`。本轮包含 Python 名称解析与前端，需彻底重启 ComfyUI 后 `Ctrl+F5`。

## 2026-10-25 · Guide 节点移除帧数推算提示（未提交）

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-25-guide-v2-ui-pre-remove-length-note` 保存本轮前完整开发树（188 个文件，逐文件哈希 `mismatch: 0`）。
- 从 Guide Timeline v1/v2 节点底部移除「秒数 × FPS、17n+5、上次实际运行帧数不一致」等推算说明，避免把界面展示口径误当成生成错误。时间轴长度输入、时间尺、帧数换算、执行校验和实际 latent 行为均不变。
- 自动验证：Guide 状态专项 **106/106 通过**，20 个 `web/*.js` 语法检查全部通过，已移除的提示函数与文案无残留。本轮仅删除前端说明，未重复执行 Python 全量回归。已同步运行副本，108 个开发/运行文件 `mismatch: 0`、`stale: 0`；不提交、不推送、不创建 tag。

## 2026-10-25 · Guide Timeline v2 操作与状态可视化（未提交）

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-25-805ae7e-guide-v2-ui` 保存本轮前完整开发树（108 个源码/文档/测试文件，逐文件哈希 `mismatch: 0`）。本轮只改 v2 的前端展示与编辑体验；稳定版 v1、两个节点的 ID/schema、Guide 文档、强度执行、缓存指纹和模型适配不变。
- 范围：编辑器与节点内图片轨显示逐图强度；v2 节点把待放置、停用、强度 0.00 分开计数，并在原固定高度内显示按需 VAE 与编排校验摘要；详情区增加强度滑杆、数字框和原生 / 0.80 / 0.60 / 不加入快捷档位。滑杆只在 change 时提交，view_state 与缓存口径不变。
- 自动验证：Guide 状态专项 **106/106 通过**，新增混合状态、v1 忽略强度、停用/待放置优先级和 runnable 一致性断言；完整既定 Python 入口 **649/649 通过，0 跳过**；20 个 `web/*.js` 语法检查全部通过。差异核对仅 `VERSION.md`、`web/guide_state.js`、`web/guide_timeline.js`、`web/guide_timeline.css` 四个仓库文件发生变化。真实 ComfyUI 视觉与手操由用户验收；不提交、不推送、不创建 tag。
- 已同步运行副本 `E:\ai\ComfyUI-aki-v3\ComfyUI\custom_nodes\H3-Long-Video-Manager`：108 个开发/运行文件，`mismatch: 0`、`stale: 0`。本轮仅前端与文档变化，无需重启 ComfyUI，浏览器 `Ctrl+F5` 后验收。

## 2026-10-25 · 近期性能、流式 v2 与预览修复打包提交

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-25-9368107-pre-push` 保存打包前完整开发树（108 个源码/文档/测试文件，逐文件哈希 `mismatch: 0`）。远端 `origin/main` 已 fetch 核对，仍为 `9368107`，没有需要合并的新提交。
- 本次打包范围：性能优化两轮、真实源帧率到 24fps 的转换、H3 Video Loader、Manager / Smart Split 独立流式 v2、立体声音频修复、v2 原视频与 Picker 投放视频 H.264 兼容预览、CFR 原始尺寸 FFmpeg 流式快速路径，以及对应文档和测试。稳定版节点、裁切算法、Motion Context、Join Match 等继承行为不在本轮改动范围内。
- 验证基线：完整既定测试入口 **649/649 通过，0 跳过**；开发副本 20 个 `web/*.js` 语法检查 0 失败；真实 HEVC 经投放库生成 H.264/yuv420p 代理并完整解码 832 帧，源文件不变。用户已明确反馈 Picker 黑屏修复测试通过；其他真实界面手操与成片效果仍以各条记录中的验收边界为准。
- 本次由用户明确要求提交并推送 `origin/main`，不创建新 tag。下列 2026-10-24 条目中的「未提交 / 不提交、不推送」是各轮开发当时的记录，均随本次打包进入 `main`，不表示仍然躺在本地。

## 2026-10-24 · Segment Picker 投放视频兼容预览（未提交）

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-24-9368107-picker-preview` 保存本轮前完整开发树（188 个文件，含既有 Python 缓存；逐文件哈希 `mismatch: 0`）。
- 代码路径确认的根因：投放卡片把原始 `/view` 地址直接交给浏览器 `<video>`，此前为 Manager / Smart Split v2 完成的 HEVC 兼容代理没有接入 Picker，因此 H.265 / HEVC 等浏览器不支持的视频仍可能黑屏。
- 新增同源 JSON `POST /h3_lvm/uploads/preview`：只接受投放库项目名与当前视频编号，通过 `resolve_upload()` 解析已入库文件并创建短期只读票据；不接受磁盘路径。代理仍复用 `source_preview.py` 的按需 H.264/yuv420p + AAC 转码、缓存、并发锁、原子替换与 HTTP Range，不开放任意路径 GET。
- Picker 的 HEVC 与浏览器不支持的封装自动使用兼容预览；普通格式优先直接播放，播放错误自动回退，也可手动点击「🔄 兼容预览」。转码只生成 ComfyUI temp 下的临时副本，不改上传原文件、项目索引、正式 `decode_video` 或 24fps 输出。裁切片段库、Manager / Smart Split、Motion Context 与四个输出不变。
- 自动验证：新增真实 HTTP 专项 **4/4 通过**，覆盖项目/编号授权、同源与 JSON 校验、未知编号拒绝、HEVC 推荐、H.264/yuv420p 代理、音轨保留、缓存只转码一次、源字节不变；完整既定测试入口 **649/649 通过，0 跳过**，开发副本 20 个 `web/*.js` 逐个 `node --check` 为 0 失败。
- 真实素材验证：用户此前提供的 27.747 秒 HEVC 抖音视频经「复制到临时投放库 → 项目/编号授权 → 代理」实际生成 H.264/yuv420p，**832 帧全部解码成功**，上传文件和原片的 SHA-256 均未改变。真实浏览器播放和视觉交互仍由用户人工验收。
- 已同步运行副本 `E:\ai\ComfyUI-aki-v3\ComfyUI\custom_nodes\H3-Long-Video-Manager`：108 个开发/运行文件，`mismatch: 0`、`stale: 0`；运行时导入正常，10 个节点注册。此次改了 Python 路由与前端，需彻底重启 ComfyUI 后 `Ctrl+F5`。不提交、不推送、不发布版本。

## 2026-10-24 · Manager / Smart Split v2 CFR 流式解码提速（未提交）

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-24-9368107-ffmpeg-stream` 保存本轮前运行副本。基准与候选边界记录于 `work/stream_v2_speed_baseline.md`：真实 27.747 秒 HEVC 当前原始尺寸裁切 7.745s，其中视频迭代 6.011s；FFmpeg 默认可选帧不同，只有 `fps=24:round=up` 在 CFR 测试中得到一致结果，VFR / 缩放不允许直接替换。
- `comfyui/stream_video.py` 新增 CFR + 原始尺寸 FFmpeg rawvideo 快速路径：`setpts=PTS-STARTPTS,fps=24:round=up`，每帧直接 `readinto` 可写 NumPy uint8 数组，不生成整部视频、不使用只读 torch 缓冲。进程在生成器关闭、帧数上限或异常时回收；启动失败回退 PyAV，已经产出帧后的失败明确报错，绝不从头重读造成重复帧。
- VFR、缩放输出和 FFmpeg 不在 PATH 时完整保留原 PyAV 实现。Manager / Smart Split 第二遍传入已经取得的 `source_info`，不增加一次视频探测；Smart 的低分辨率检测仍走 PyAV。节点 ID、接口、24fps 口径、分段、Motion Context、音频、存储格式与 v1 均未改变。
- 自动验证：60fps、12fps、VFR、缩放、启动失败和 FFmpeg 缺失回退等流式专项通过；完整既定测试入口 **645/645 通过，0 跳过**。真实 HEVC 新快速路径与原 PyAV **666/666 帧逐字节一致**。
- 同机同片完整 Manager v2 基准：总耗时 **7.745s → 3.025s（约 2.56×）**，视频迭代 **6.011s → 0.769s（约 7.82×）**；存盘仍约 1.8s，因此不能把管道提速倍率当成所有机器、所有素材的整节点承诺。真实 ComfyUI 内手操和长素材表现由用户验收。

## 2026-10-24 · v2 原视频 H.264 兼容预览（未提交）

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-24-9368107-preview-proxy` 保存本轮前运行副本。用户提供的黑屏视频经 `ffprobe` 确认为 HEVC/H.265 Main、576×1024、30fps、yuv420p；原预览把源文件直接交给浏览器，因此与浏览器 HEVC 支持不足相符。
- `comfyui/source_preview.py` 保持短期只读票据授权，新增按需 H.264/yuv420p + AAC 代理：最长边不超过 1280、不提升分辨率、不改变源帧率，`libx264 veryfast / CRF 23`，源文件绝不改写。缓存位于 ComfyUI temp 的 `h3-lvm-source-preview`，键包含源 realpath、大小、mtime 与代理格式版本；同 key 并发共用锁，临时文件完整后才 `os.replace`，重复打开不重新转码。正式裁切、24fps 和音频路径不变。
- `server_api.py` 新增同源 JSON `POST /h3_lvm/source_preview_proxy`，只接受既有 ticket，不能接受磁盘路径；代理 GET 仍走原 FileResponse / HTTP Range，未生成时返回错误而不会由 GET 偷偷转码。`probe_video` 只新增 codec / pix_fmt 元数据，不改变解码行为。
- `web/source_preview.js`：普通格式仍优先源文件直读；HEVC/H.265 直接进入兼容预览，其他格式播放 `error` 自动回退；另有 **🔄 兼容预览** 按钮处理浏览器未抛错误的黑屏。转码期间显示状态，关闭弹窗后的迟到响应不会重设播放器；节点尺寸与布局逻辑不变。
- 自动验证：预览 API 专项 **10/10 通过**，覆盖真实 H.264 代理、音轨保留、源帧率、缓存只转码一次、源字节不变、HEVC 推荐、票据与同源校验；完整既定测试入口 **641/641 通过，0 跳过**，`source_preview.js` 的 `node --check` 通过。另用用户提供的 27.747 秒 HEVC 文件实际生成代理成功：H.264/yuv420p、576×1024、832 帧。真实浏览器播放与按钮视觉由用户人工验收；首次代理需完整转码，长视频会等待并占用临时磁盘。

## 2026-10-24 · 文件音频立体声解码修复（未提交）

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-24-9368107-stereo-audio` 保存本轮修复前运行副本的完整文件。根因是 PyAV packed 立体声把左右声道交错在一个平面里，旧代码却把它当成单声道样本；两个声道因此错位，听感、音高和有效声道均异常。24fps 视频转换本身不变速音频。
- `comfyui/video_decode.py` 的 `_audio_to_channels()` 现在按 `frame.format.is_planar` 区分 packed / planar；packed 多声道先解除交错再返回 `[channels, samples]`。完整 Loader / 投放解码与 Manager v2 / Smart Split v2 分段音频统一使用 `s16p` 平面重采样，保留源采样率、声道与时间轴，不做 `atempo` 或音高变换。
- 新增真实 60fps、48kHz、左右声道分别为 440Hz / 880Hz 的 AAC 视频用例，同时覆盖完整解码与按时间段解码；修复前两者都错误输出单声道，修复后声道、音高和时长检查通过。完整既定测试入口 **638/638 通过，0 跳过**。实际素材听感由用户人工验收；源视频和旧库均不被自动改写，已经生成的异常片段需重新运行生成。

## 2026-10-24 · Manager / Smart Split 独立流式 v2（未提交）

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-24-9368107-video-path-label` 保存本轮前的完整工作树（96 文件，逐文件哈希一致）。稳定版 `H3 Long Video Manager` / `H3 Smart Split` 的节点 ID、张量输入、裁切算法与执行行为不变；新节点为 `H3 Long Video Manager v2` / `H3 Smart Split v2`，不自动迁移旧工作流。
- v2 直接选择 input 视频或完整路径，在解码时转为 24fps。Manager v2 单遍流式定长裁切；Smart Split v2 第一遍逐帧低内存检测，第二遍按镜头保存。新增 `core/stream_segments.py`、`comfyui/stream_video.py`、`comfyui/stream_nodes.py`，仅保留当前段、MC 重叠与选中输出段，避免完整长视频 float32 IMAGE。Manager v2 暂不提供 v1 的人物裁切控件。
- 两个 v2 的 schema 均增加 `is_output_node=True`：不连接任何下游输出也能直接点运行，完成裁切和存库；原有四个输出接口保留。稳定版 v1 仍不是输出节点，执行行为不变。保存开启时原有 NaN 指纹继续保证每次运行都真正执行，不被缓存跳过。
- 片段仍写原项目索引与 safetensors 结构，17n+5、末段、Motion Context 和四个输出不变。`segment_store.py` 增加 uint8 输入支持：int8 直接平移存储，fp16 才转换；原 float 路径保留。真实文件测试验证保存后读取与 v2 选中输出逐值一致。
- v2 面板复用现有项目菜单和卡片墙，新增来源控制条与 **▶ 原视频预览**。预览用同源 POST 创建两小时只读票据，GET 只允许票据对应的文件，`FileResponse` 支持 HTTP Range；浏览器 `preload="metadata"`、不自动播放，关闭时暂停、清除 src 并 load。没有任意路径 GET、不复制、不转码、不生成 IMAGE；浏览器不支持的编码只影响预览，不影响 PyAV 执行。
- 来源控制条按后续用户反馈只保留一个 **📁 选择视频…**：点击直接用 tkinter 打开 Windows 系统选框，不再进入自制简洁文件浏览器。可选任意磁盘视频并返回绝对路径，不受 input 限制，不上传、不复制；取消保留当前选择，重复打开会被拒绝。远程浏览器需注意弹窗出现在服务器端，此时粘贴服务器可读取路径。原生弹窗手操由用户验收。
- 自动验证：流式视频 / 分段 / 节点 / 预览 API 专项 **23/23 通过**；加入系统选框后完整 `unittest discover` **636/636 通过，0 跳过**。前端 `node --check` 全量 0 失败，模块 import 检查通过，Guide 状态 103、参考状态 46、Picker 模式规则测试全部通过。真实 ComfyUI 布局、系统选框、原视频播放和长素材峰值内存尚待用户人工验收；不提交、不推送、不标记版本。
- 已同步运行副本 `E:\ai\ComfyUI-aki-v3\ComfyUI\custom_nodes\H3-Long-Video-Manager`：108 个开发/运行文件，`mismatch: 0`、`stale: 0`；独立运行时导入确认 `NODE_LIST: 10`，两个稳定版与两个流式 v2 同时注册。需彻底重启 ComfyUI 加载新 Python 节点和预览路由，再硬刷浏览器。

## 2026-10-24 · 视频加载器服务器文件浏览器（未提交）

- 按钮文案按用户反馈由「选择视频（不上传）」改为 **「选择视频（路径）」**；改动前快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-24-9368107-video-browser`（96 文件，逐文件哈希一致）。仅显示文案变化，行为与测试范围不变。
- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-24-9368107-video-loader` 保存本轮前的加载器完整工作树（93 文件，逐文件哈希一致）。
- 节点新增 **📁 选择视频（路径）** 和独立浮层文件浏览器：进入/返回目录、当前目录筛选、刷新、单选确认；选中后显示文件大小、分辨率、时长、源帧率和音轨信息。确认只写原有 `video` 相对路径并清空 `custom_path`，不上传、不复制、不改变节点尺寸。保留下拉框和完整路径输入；不增加常驻文件列表或内部拖拽功能。
- 新增只读 `GET /h3_lvm/video_files` 与 `GET /h3_lvm/video_file_info`，以 realpath + commonpath 限制在 input 内；目录接口只读目录项，信息接口只探测选中的单个文件，不能读取任意磁盘路径。
- 前端 `web/video_loader.js` / `video_loader.css` 使用原生 dialog 浮层、统一悬停/选中/焦点反馈；未修改 ComfyUI 前端。`node --check` 通过。
- 自动验证：浏览器与接口专项 **11/11 通过**（含真实 aiohttp 路由、60fps 视频信息、一级目录返回、绝对路径与 `..` 越界拒绝）；完整 `unittest discover` **610/610 通过，0 跳过**。文件浏览器真实 ComfyUI 手操与视觉尚待用户验收。
- 已同步运行副本 `E:\ai\ComfyUI-aki-v3\ComfyUI\custom_nodes\H3-Long-Video-Manager` 供用户人工测试：96 个开发/运行文件，`mismatch: 0`、`stale: 0`。需彻底重启 ComfyUI 加载 Python 节点与路由，再硬刷浏览器；不提交、不推送、不标记版本。

## 2026-10-24 · 新增 H3 视频加载器（未提交）

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-24-9368107-fps-conform` 保存本轮前的 24fps 转换修复完整工作树（91 文件，逐文件哈希一致）。
- 新增独立节点 `H3 Video Loader` / `H3 视频加载器（24fps）`，只加入本插件，不修改 ComfyUI 本体或原生 Load Video。文件选单不声明上传控件，直接读取 `input`（含子目录）或用户粘贴的本地完整路径，从机制上绕开浏览器上传与服务器上传大小限制。
- 复用 `video_decode.py` 的 PyAV 时间戳解码：输出固定 24fps，60fps 不慢放；分辨率在逐帧解码时缩小，再累积为 IMAGE，源文件不复制、不改写。输出 `IMAGE / AUDIO / frame_count / fps`，其中 fps 固定为 24，可直接连接 Manager / Smart Split；无音轨时输出等长静音。文件 mtime、大小、路径和输出分辨率进入缓存指纹。
- 边界：该节点仍返回完整 IMAGE，不是无限长视频的流式处理；超长、高分辨率素材需要降低解码尺寸并保证内存足够。后续若做 Manager / Smart Split 文件流式输入，应另行设计，不在本轮暗中改变其接口。
- 自动验证：`tests/test_video_loader.py` 7 条，含无上传控件、嵌套文件列表、路径优先级、中文校验、缓存、静音补齐，以及真实 60fps 文件的 24fps 与音频同步；专项组合 **24/24 通过**。完整 `unittest discover` **606/606 通过，0 跳过**（TEMP/TMP 定向到仓库可写临时目录，避免沙箱拦截既有越界路径测试的探针文件）。
- 尚未同步 ComfyUI 运行副本，以免影响用户正在进行的上一轮人工测试；不提交、不推送、不标记版本。

## 2026-10-24 · 源帧率转换修复（未提交）

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-24-9368107-performance-round2` 保存本轮修改前的第二轮完整工作树（89 文件，逐文件哈希一致）。
- `H3 Long Video Manager` 与 `H3 Smart Split` 的 `fps` 现在明确表示输入素材的真实源帧率。新增 `core/frame_rate.py`，先按真实时长把输入张量转换为 24fps，再进行人物裁切、定长裁切或镜头检测；60fps 输入不会再被直接当成 24fps 慢放，低帧率输入通过重复邻近帧保持原速度。24fps 输入零复制透传，不使用光流插值。
- 视频按最近时间帧采样，目标帧数为 `round(源帧数 × 24 / 源帧率)`；音频按转换后的 24fps 时间轴裁切，真实时长不变，不变调。节点 ID、输入数量、输入顺序、四个输出、裁切算法、17n+5、Motion Context 和存储结构均未改变。
- ComfyUI `IMAGE` 不携带 fps 元数据，无法自动识别源帧率；用户仍需在 `fps` 中正确填写或连接真实源帧率。已经按旧逻辑保存的 60fps 切片不会自动迁移，需用新实现重新运行 Manager / Smart Split，建议使用新项目避免旧卡片混淆。
- 自动验证：新增 `tests/test_frame_rate.py` 5 条，覆盖 60→24、12→24、24fps 零复制，以及两个节点的转换后裁切和音频同步；专项 **48/48 通过**，完整 `unittest discover` **599/599 通过，0 跳过**。
- 已同步 ComfyUI 运行副本 `E:\ai\ComfyUI-aki-v3\ComfyUI\custom_nodes\H3-Long-Video-Manager`：91 个开发/运行文件，`mismatch: 0`、`stale: 0`。Python 改动需彻底重启 ComfyUI；尚未做真实 60fps 素材的人工验收，不提交、不推送、不标记版本。

## 2026-10-24 · 性能优化第二轮（未提交）

- 快照：`C:\Users\az\Documents\Codex\2026-10-02\xia\archive\2026-10-24-9368107-performance-round1` 保存用户已验收的第一轮完整工作树（88 文件，逐文件哈希一致）。
- MP4 预览编码改为每次处理并写入 8 帧，不再一次性生成整段 `rawvideo` 字节；packed int8 也只在当前块内解码为 float，避免整段 float32 与整段字节同时占内存。
- ffmpeg 参数、音频 WAV、输出路径与存储格式不变。stdin 写完后关闭并等待退出；stdout/stderr 直接丢弃以避免管道填满，断管或转换异常时终止并回收仍未退出的进程。
- 自动验证：`tests/test_mp4_encoding.py` 3 条（真实 ffmpeg 的 8+2 帧写入、帧数/像素/音频流、非零退出、BrokenPipe 清理）；完整 `unittest discover` **594/594 通过，0 跳过**。
- 尚未做 ComfyUI 内人工操作与大项目峰值内存计时；当前仍未同步运行副本，不提交、不标记版本。

## 2026-10-24 · 性能优化第一轮（未提交）

- 快照：`archive/2026-10-24-9368107-performance/` 保存本轮修改前的完整 `9368107` 基线。
- 本轮范围：合并封面只解码实际使用的一帧；投放视频降帧时跳过不会被采用的源帧像素转换。裁切算法、Motion Context、存储格式和节点接口不变。
- 自动验证：专项 `tests.test_merge_segments + tests.test_video_decode` **56/56 通过**（含真实 ffmpeg/PyAV 视频）；完整 `unittest discover` **591/591 通过，0 跳过**；两仓库全部 24 个 `web/*.js` 均通过 `node --check`。测试辅助目录改用普通 `os.mkdir`，避免 Windows 受限沙箱无法写入 `tempfile.mkdtemp` 的 0700 目录；该修正只影响测试基础设施。
- 尚未做 ComfyUI 内人工操作与实际项目性能计时；当前仍是未提交开发副本，不标记版本。

## 2026-10-24 · `666f4ac`（当前基线，= tag `v1.5.0`）

- 快照：改动前的状态就是 `ee627c8`（tag `v1.4.0` 之后的文档 commit），已由 `git archive ee627c8` 解到 `archive/2026-10-24-ee627c8/`（87 个文件，与 `git ls-files` 一一对应）。该目录原先存的是本轮在途工作树，那些内容现在全部进了 `666f4ac`，所以按目录名重取干净基线不丢任何东西。提交后的快照在 `archive/2026-10-24-666f4ac/`（87 个文件，由 `git archive v1.5.0` 解出，与提交内容逐字节相同）。
- 本 tag 打包了四条在途改动：下面三条记录（参考池超额保留 + 全部清空、Segment Picker 隐藏重复下拉框、Guide 卡片池文件载入诊断），加上本轮的 **H3 Guide Timeline v2 逐图引导强度** 与 **节点内时间轴卡片的独立尺寸**。三条旧记录里的「未提交」字样已改成指向本 tag。
- 需求（用户任务书 + 两次收窄）：新增**独立**节点 `H3 Guide Timeline v2`（`comfyui/guide_nodes.py: H3GuideTimelineV2`，继承稳定版类，只改 `define_schema()` 里的 node_id / display_name / description / tooltip 和强度路径），保留 v1 全部时间轴能力，只额外给**每张图片 Guide** 一个「引导强度」。稳定版 `H3 Guide Timeline` 的节点 ID、接口、数据格式与执行行为一字未改，也不做自动迁移；两个节点同时出现在 ComfyUI 里，旧工作流继续走旧节点。音频 Guide 不加强度。
- 强度口径（最终）：范围 `0.00–1.00`，步进 `0.05`，默认 `1.00`。`1.00` = 原生 Add Guide 原路径，模型侧什么都不改写；`0.05–0.95` = 逐图强度机制；`0.00` = 卡片、时间位置、强度值照常留在文档里，但这张图片不 VAE 编码、不进 conditioning、不新增 keyframe，也不参与该项校验。
- 为什么不是「latent 乘系数」也不是「串几个全局值」：原生 H3 只有一个全局 `minimax_visual_cond_noise_aug`，串联时最后一个赢，payload 里本来就只有一个数；只把 latent 乘系数会让那一行仍带着近乎干净的 timestep 标签，模型把注入的噪声当**内容**画成纹理畸变。逐图强度必须同时做两件事：把这一条条件的 latent 朝噪声插值 `a*z + (1-a)*noise`（flow-matching 前向过程在时间 a），并把这一行的 modulation timestep 重标为 `max(t_video, a)`，让模型把噪声读成**不确定性**。只做一件就是任务书禁止的失败模式，所以两者一起装、要么都不装。机制参考 ComfyUI-H3Studio 的拆分，只借图片 Guide 需要的最小部分。
- 新增 `comfyui/h3_strength_patch.py`（不编辑 ComfyUI 内核）：给 keyframe / reference 字典写 `noise_aug` 键，按**真实 payload 顺序**（带 latent 的 keyframes，再带 latent 的 refs）逐条对齐——不是卡片序号、也不是卡片数量，输入 `positive` 里已有首尾帧或其他 Guide 时照样对应正确；原生一次加两条 keyframe 时明确拒绝而不是猜。没有 `noise_aug` 的块保持原生逐比特行为（含内核自己的全局插值与全局 timestep 标签）；整个 payload 都没有这个键时补丁是惰性的，所以同进程里普通 H3 工作流不受影响；条数对不上直接抛错。适配装不上（内核实现变了 / 别的插件已改写同一批模型方法 / 模型类不存在）时 v2 低于 1.00 的运行以中文错误停下，不静默退化成全局强度；v1 与 v2 的 `1.00` / `0.00` 路径都不碰模型，照常运行。
- 数据与缓存：v2 的图片条目多一个 `strength`，缺字段按 `1.00` 读，音频条目没有这个字段；强度计入 v2 的执行摘要与缓存指纹（改强度必重新执行；改选中项、缩放、滚动时间轴不重新编码）。v1 的文档解析、摘要与缓存行为不变，`tests/test_guide_timeline_core.py: test_the_v1_digest_bytes_are_frozen` 把 v1 摘要哈希钉死。
- VAE 端口不变：两个 VAE 输入端口与接线方式照旧，可以一直连着；执行时按实际生效的素材决定调用哪一个，图片全是 `0.00` 时不要求连接视频 VAE，没有任何生效 Guide 时 positive 原样透传。
- 前端：`web/guide_state.js` 是同一套规则的 JS 镜像（`STRENGTH_DEFAULT/MIN/OFF/MAX/STEP`、`normalizeStrength`、`strengthOf`、`isMutedImage`、`hasStrength`、`countRunnableV2`、`validateGuidesV2`）；`web/guide_timeline.js` 在图片卡片上显示强度徽标（`1.00` 与 `0.00` 各有样式，`0.00` 文案「强度 0.00 · 不加入」），详情区滑杆与卡片共用同一份 `guide.strength`；复制继承、替换素材保留、拖动换序不改强度。v1/v2 共用同一份前端文件，只靠一个节点版本开关决定是否显示强度，没有第二套渲染器。顺带按用户要求把节点上的「视频时长（秒）」改成「时间轴长度（秒）」。
- 另一条未记录过的改动（补记）：节点内时间轴的卡片有独立尺寸控件 `view_state.strip_marker_side`（`STRIP_MARKER_SIDE_LIMITS` 40–320px、步进 16、默认 100），点「卡片 − / ＋」才写入；此后卡片不随轨道高度、节点宽度或卡片数量改变，未设置时仍走原来的自动尺寸，旧工作流显示不变。`stripLaneHeights` 不读卡片边长，所以两个控件互不影响；纯函数在 `web/guide_state.js: stripCardPlan`。
- 测试：`tests/test_h3_strength_patch.py` 新增 21 条（payload 顺序与空洞对齐、无键时惰性、只移动被标记的行、标签不低于目标流、条数/布局不符拒绝、blend 按锚定帧种子可复现且保持编码器 dtype、全 1.00 什么都不改、模型类缺失/外部补丁/内核变更三种拒绝、拒绝后不动活内核、已标记条件不二次插值、未标记 prompt 保留全局插值）；`tests/test_guide_nodes.py` 51 条（两个节点同时注册、两个 node_id 一个输出同一接线、v2 schema 不动 v1 schema、每个强度值一个缓存键、强度对应它自己那条 keyframe、`0.00` 不解码不编码、只有 `0.00` 时不接视频 VAE 也透传、`0.00` 不影响其他 Guide 也不参与校验、全 1.00 与稳定版张量等价、适配被拒是错误不是静默退化、旧文档在两个节点上都不变）；`tests/test_guide_timeline_core.py` 54 条（`normalize_strength` 边界与缺字段、面板档位、v1 永远看不到 strength、v2 默认满强度、音频无字段、往返保存、摘要与缓存键随强度、视图状态不改键）；`tests/test_node_schema.py` 12 条。四套合跑 `Ran 138 tests ... OK`；全套 `Ran 589 tests in 23.838s ... OK`（日志 `work/h3lvm_full.log`）。前端 `node work/guide_state.test.mjs` → **103 passed, 0 failed**；`work/ref_state.test.mjs` → 46 passed；`work/picker_mode_state.test.mjs` 全绿；`work/check_plugin_web.ps1` → `syntax failures: 0`；`work/check_guide_imports.mjs` 无缺失/未使用导入。运行时导入 `work/check_runtime_import.py` → `NODE_LIST: 7`，`H3 Guide Timeline` 与 `H3 Guide Timeline v2` 同时注册。运行副本 `work/sync_h3lvm.ps1` → **87 files / mismatch 0 / stale 0**。
- 本轮改了 Python 的 schema 与新节点 → 实测要**重启 ComfyUI**，`Ctrl+F5` 不够。
- 未验证（必须用户实测）：`0.80 / 0.60 / 0.00` 对成片画面的实际影响、卡片徽标与详情滑杆的手感、节点内卡片独立尺寸控件的实际观感；与别的改写同一批模型方法的插件（例如 H3Studio）同时装在同一进程时的真实冲突。


## 2026-10-24 · 参考素材池保留超额卡片与全部清空（已提交，见 Tag 线 v1.5.0）

- 快照：`archive/2026-10-24-ee627c8-ref-pool-clear/` 保存本轮修改前完整工作树。
- `H3 图片参考加载器`（共用面板的音频加载器同享）：状态栏分开显示素材总数与启用槽位数；添加唯一新素材时只有启用数量受 H3 槽位上限限制，超额素材自动以跳过状态保留在后排，不再直接丢弃，重复文件仍去重。
- 新增「全部清空」：第一次点击只进入确认状态，第二次才清空当前节点的全部卡片；不删除 input/output 原文件，也不删除项目预设。清空后可继续添加或载入预设。
- 自动验证：`work/ref_state.test.mjs` **46 passed, 0 failed**；`work/check_plugin_web.ps1` **syntax failures: 0**。独立 Chrome 通过 CDP 真实鼠标命中与点击完成 **21 passed, 0 failed**（首次点击仅确认、二次点击才清空、原文件仍可读取、项目预设不变且可重新载入、确认超时自动取消、空列表可序列化）；报告 `work/probe/ref-clear-all-report.json`。
- 部署：已同步 ComfyUI 运行副本，**87 files / mismatch 0 / stale 0**。只改前端，`Ctrl+F5` 后生效；视觉布局仍由用户验收。
- 本轮只改前端状态与交互，不改节点 ID、输入输出 schema、后端执行或预设文件结构。已随 v1.5.0 提交并推送。

## 2026-10-24 · Segment Picker 隐藏重复模式下拉框（已提交，见 Tag 线 v1.5.0）

- 快照：`archive/2026-10-24-ee627c8-picker-mode/` 保存本轮修改前完整工作树。
- `H3 Segment Picker` 的原生 `source_mode` 下拉框设置 `options.hidden = true`，界面只保留顶部的「裁切片段 / 投放视频」两个大按钮。控件与输入 schema 未删除，仍按原位置保存和恢复，按钮、双模式项目状态及后端执行逻辑不变。
- 测试：`work/picker_mode_state.test.mjs` 全绿；`work/check_plugin_web.ps1` **syntax failures: 0**。独立 Chrome 真实鼠标验证 **3/3 passed**：下拉值已隐藏、两个按钮仍存在、两种模式均可切换且节点尺寸不变。
- 部署：已同步 ComfyUI 运行副本，只改前端，`Ctrl+F5` 后生效。已随 v1.5.0 提交并推送。

## 2026-10-24 · Guide 卡片池外部文件载入诊断（已提交，见 Tag 线 v1.5.0）

- 快照：`archive/2026-10-24-ee627c8/` 保存本轮修改前的完整工作树（包含当时尚未提交的 v2 与界面改动）。
- 本轮只改 `web/guide_timeline.js` 的文件导入路径，不改 v1/v2 节点接口、Guide 数据格式或执行行为。
- 已确认并修复的报告层缺陷：上传异常原先被空 `catch` 吞掉，失败计数又误用 `failed.length`（原变量是数字），用户只能看到“上传失败 undefined 个”或完全没有原因。现在逐个记录 `native-upload-start/success/failed`，底栏显示失败文件名与 HTTP/网络原因；非支持格式、空文件列表及其他导入异常也有明确提示。
- `FileList` 在 `addFiles()` 入口统一转成数组；外部拖放按文件自身类型入库，上传失败不留下卡片。上传中提示包含当前文件名，成功添加的类型切换只依据实际上传成功的素材。
- 自动验证：`node work/guide_state.test.mjs` → **103 passed, 0 failed**；`work/check_guide_imports.mjs` 无缺失/未使用导入；`work/check_plugin_web.ps1` → **syntax failures: 0**。同步运行副本后，独立 Chrome 对 `H3 Guide Timeline v2` 执行真实 `/upload/image` 请求与文档渲染，`work/guide_file_drop.mjs` → **14 passed, 0 failed**，其中网络失败分支明确显示 `probe_upload_failure.jpg（Failed to fetch）`，卡片数不变。
- 部署：`work/sync_h3lvm.ps1` 已复制 `web/guide_timeline.js`，全仓 **87 files / mismatch 0 / stale 0**。只改前端，用户 `Ctrl+F5` 后复测。
- 验证边界：探针使用合成 `DragEvent` 驱动产品处理器，上传、失败网络响应、文档写入和卡片渲染是真实的；它**不等于** Windows 资源管理器真人鼠标拖放已通过。用户原始文件的真人拖放仍待验收，不能把本轮自动结果宣称为该手势已修复。

## Tag 线

- `v1.0.0` → `305a5d7`（首个 tag）：定长切段（每段含 MC 重叠帧固定 ≤ 用户输入时长且对齐 17n+5）+ 末段零丢失不对齐、素材存盘 int8/fp16 开关、项目素材库选单（切换/新建/删除整库）、两个节点的中文可视面板与常开卡片区、竖屏卡片完整显示、卡片缩放 100%–400% 共用控件。已推送 `origin`（`git-push-github.ps1 -Tags` 只推 tag，分支要再跑一次不带 `-Tags`）。
- `v1.1.0` → `0a1cdd4`（tag 对象 `5d7b5a3`）：新增 `H3 Smart Split` 节点（按镜头切点分段，长度交给 MiniMax H3 判断，无损覆盖全部帧）+ 两个产出节点共用的一套卡片区 `web/deck_panel.js`（常开、载入即出卡片、`本次` 角标、卡片缩放 100%–400%、点卡片写回输出片段编号）+ 卡片区合并模式（相邻多选、`✅ 确认合并`、新卡片沿用最小 id 且后续编号顺延、接缝去掉 MC 重叠帧并同步裁音频、packed int8/fp16 直拼、`POST /h3_lvm/merge`）。已推送 `origin/main`（远端 main = `0a1cdd4`）与 `v1.1.0`。
- `v1.2.0` → `0b8d8b5`（tag 对象 `87c39ac`）：新增 `H3 图片参考加载器` / `H3 音频参考加载器`（官方 Autogrow 端口的数量与顺序不变，空槽输出真 `None`）+ 按比例缩放的目标 MP 与 32 像素网格、四种重采样滤镜、`放大小图` 开关（关闭时只做网格对齐，不施加目标面积）+ 卡片跳过/放回（状态存在 `media_files` 的 `skip`，活动卡片在前、已跳过在后）+ 卡片拖拽换序 + 音频卡片的时间窗（起始/时长）+ 参考预设按类型分开存（`<output>/h3-lvm-image-refs`、`<output>/h3-lvm-audio-refs`，与视频库 `h3-lvm/` 同级；预设只存路径 + 排序 + 跳过状态，旧共用文件 `h3lvm_references.json` 一次性按类各复制一份且原文件不动）+ `GET /h3_lvm/ref_plan`、项目接口的 `scope=segments|image|audio`、预设接口的 `kind=`、`POST /h3_lvm/ref_presets`。已推送 `origin/main`（远端 main = `0b8d8b5`）与 `v1.2.0`。
- `v1.3.0` → `21f9eba`（tag 对象 `7e65ca2`）：`H3 Segment Picker` 双模式素材库——`裁切片段库`（原有行为与四个输出接口不变）与 `视频投放库`（拖入 MP4 → 卡片 → 直接输出 IMAGE/AUDIO），两套独立的实际存储路径与项目索引（`<output>/h3-lvm/` 与 `<output>/h3-lvm-uploads/`），保存工作流后可恢复；投放库支持导入/删除/卡片拖拽换序（重编号 1..N、文件与封面不改名、`next_id` 只增不减）与 `GET /h3_lvm/uploads`、`POST /h3_lvm/uploads/import`、`POST /h3_lvm/uploads/delete`、`POST /h3_lvm/uploads/reorder`；`comfyui/video_decode.py` 用 ffprobe/ffmpeg 按需探测与解码，输出分辨率只在解码时缩放（预设最长边 3840…480 + `自定义（自己填最长边）` 配 `custom_max_side`，夹到 16–8192、绝不放大、对齐偶数），上传文件永远逐字节保存、永不重编码；面板沿用既有设计语言（项目菜单新建/删除、卡片缩放 100%–400%、竖屏完整显示、全中文文案）。已推送 `origin/main`（含 `21f9eba` 与本次文档 commit）与 `v1.3.0`。

- `v1.3.1` → `1921477`（tag 对象 `482b118`）：投放视频库的卡片编号改为**就是卡片位置**，永远 1..N 连续无空号——导入追加到末尾、删除让后面的卡片顺延补位、拖拽按新顺序重排；`next_id` 语义收窄为存储序号（只生成 `vidNNN`，只增、名字永不复用，所以补位后不会覆盖别人的文件）；`MAX_SEGMENT_ID = 999` 从「编号上限」改为「卡片数上限」；面板删除后把选中项跟到新编号并写明「后面的编号已顺延」。已推送 `origin/main` 与 `v1.3.1`。

- `v1.4.0` → `3d7a75e`（tag 对象 `ebba9af`）：新增 `H3 Guide Timeline` 节点（`comfyui/guide_nodes.py` + `core/guide_timeline.py`）——一个节点替代串联的原生 `MiniMaxH3AddGuide`：Guide 文档存在 `guides` widget，锚点按真实 latent 帧数解析，没有任何启用且已放置的 Guide 时 positive 原样透传，宿主缺 `MiniMaxH3AddGuide` 时只有本节点报中文错。`web/guide_timeline.js` 的 Guide 编排弹窗：图片轨/音频轨 + 素材池 + pointer 拖动（放置、轨道内移动、拖回素材池排序）、裁切与试听、缩放平移、卡片可禁用也可移除、`length_seconds` 直接按秒数给时长。节点内也画同一条时间轴（`📈 显示节点时间轴`），**轨道高度是唯一尺寸控件、编辑器与节点内共用同一份 `view_state.lane_heights`**，卡片边长 = 实际生效轨道高度 − `MARKER_INSET*2`；面板不够高时按比例夹住并把读数标琥珀，完全放不下时自动隐藏，**绝不写 `node.size`**。文档 `GUIDE_TIMELINE.md`（本机 ComfyUI `0.42.4` / 前端 `1.55.18` 的源码核对）+ README 一节。测试：`tests/test_guide_timeline_core.py`、`tests/test_guide_nodes.py`（含与显式串联原生 Add Guide 的张量等价）、`work/guide_state.test.mjs` 89 条。已推送 `origin/main`（远端 main = `3d7a75e`）与 `v1.4.0`。

- `v1.5.0` → `666f4ac`（tag 对象 `3b7d1be`）：新增 `H3 Guide Timeline v2`（`comfyui/guide_nodes.py: H3GuideTimelineV2`，继承稳定版类，只改 node_id / display_name / 强度路径）——每张图片 Guide 一个「引导强度」`0.00–1.00` 步进 `0.05` 默认 `1.00`：`1.00` 走原生 Add Guide 原路径；`0.05–0.95` 走新增 `comfyui/h3_strength_patch.py` 的逐条件机制（按**真实 payload 顺序**给带 latent 的 keyframe/ref 写 `noise_aug`，同时做 latent 朝噪声插值 + 把该行 modulation timestep 重标为 `max(t_video, a)`；缺键的块逐比特不变，整块无键则补丁惰性，条数不符或内核被别的插件改写过就中文报错，不静默退化成全局强度）；`0.00` 保留卡片与时间位置但不 VAE 编码、不进 conditioning、不新增 keyframe。两个 VAE 端口与接线不变，按实际生效素材决定调用哪个，全是 `0.00` 时不要求接视频 VAE。强度进 v2 摘要与缓存指纹，视图状态不进；稳定版节点 ID/schema/文档/执行一字未改，v1 摘要哈希有测试钉住。另外：节点内时间轴卡片独立尺寸 `view_state.strip_marker_side`（40–320px 步进 16，与轨道高度互不影响）、`H3 Segment Picker` 隐藏重复的 `source_mode` 下拉框、参考加载器超额素材保留为跳过卡 + 两步「全部清空」、Guide 卡池 `FileList` 崩溃与上传失败原因显示。测试：`tests/test_h3_strength_patch.py` 21 条新增、`tests/test_guide_nodes.py` 51、`tests/test_guide_timeline_core.py` 54、`tests/test_node_schema.py` 12（四套合跑 `Ran 138 tests ... OK`），全套 `Ran 589 tests in 23.838s ... OK`（`work/h3lvm_full.log`），`work/guide_state.test.mjs` 103 passed，`work/ref_state.test.mjs` 46 passed，`work/picker_mode_state.test.mjs` 全绿，`work/check_plugin_web.ps1` 0 failures，运行时导入 `NODE_LIST: 7` 含两个 Guide 节点。已推送 `origin/main` 与 `v1.5.0`。

## 2026-10-23 · `v1.4.0`（上一基线）

- 快照：改动前的状态就是 `1921477`，已在 `archive/2026-10-21-1921477/`，本轮不另建旧快照。提交后的快照在 `archive/2026-10-23-3d7a75e/`（85 个文件，与 `git ls-files` 数量一致，由 `git archive v1.4.0` 解出，因此与提交内容逐字节相同）。
- 需求（用户给的任务书）：`H3-Guide-Timeline-Plan-v1` —— 新增**一个**集成节点 `H3 Guide Timeline`，用双轨时间轴替代手动串联的原生 `MiniMaxH3AddGuide`。验收以任务书第 8 章 A/B/C/D 为准，第 9 章「明确不做」一条都不做（不改内核、不改现有节点接口、不做 17n+5/MC 吸附、不做 TTS/混音/补间/多 Shot 编排、不把素材上传外部服务）。
- P0 开工调查先做完：`GUIDE_TIMELINE.md` 是对本机实际源码的核对记录（ComfyUI `0.42.4`、前端 `1.55.18`）。关键结论：原生 `MiniMaxH3AddGuide.execute(positive, latent, frame_idx, vae, audio_vae, image, audio)`；总帧数 = `sum(FRAME_PER_TOKEN[k % 5])`，`FRAME_PER_TOKEN = (1,4,4,4,4)`；音频只裁**尾部**（`max_rt = floor(audio_total_rt - 5/3 * frame_idx)`），所以**源音频的起止必须调用方自己在编码前切**；`conditioning_set_values` 是浅拷贝会写回输入 conditioning，所以本节点先深拷贝一层再接链。
- 等价性的根据不是「复刻内核」而是「按调用顺序累积」：原生把关键帧条目 append 进 `minimax_keyframes`，`PackedLayout` 按**列表顺序**打包，时间位置由 `cond_t = cursor + 5/3 * frame_idx` 决定 → 所以「编码前先按 `(frame_index, 图片优先, 原列表次序)` 排序，再逐条串联」就是等价；这条在 `tests/test_guide_nodes.py` 里用张量比较直接测，不是靠肉眼。
- 新增文件：`core/guide_timeline.py`（纯逻辑，不 import torch：规范化 / 校验 / 排序 / 配额 / 摘要 / 执行指纹 / `merge_guides`）、`comfyui/guide_nodes.py`（`H3GuideTimeline`，`display_name` 中文「H3 Guide 时间轴」，category `H3/Guide`，输出只有一个 `positive`；原生节点**懒解析**，本机没有它时只有这个节点抛可读的中文错误，插件其余节点照常注册）、`web/guide_state.js`（同一套规则的 JS 镜像 + 时间轴几何：`createScale` / `tickMarks` / `clampScroll` / `scrollForDrag`）、`web/guide_timeline.js`（节点摘要条 + 浮层编辑器）、`web/guide_timeline.css`（只加 `.h3guide-*`，节点条/卡片/工具行复用 `.h3lvm-*`）。
- 改到的现有文件只有 `comfyui/nodes.py`：把 `H3GuideTimeline` 追加进 `NODE_LIST`（独立模块，导入失败不会带走整个插件）。
- 数据契约：一个 `guides` String widget 装完整文档（`schema_version` / `fps` / `guides[]` / `view_state` / `resolved_frame_count`）。`frame_index` 是权威时间，秒只是输入与显示；音频裁切用采样点 `source_start_sample` / `source_end_sample`，区间半开 `[start,end)` 所以首尾相接不算重叠。配额 16 图 / 16 音 / 32 合计（首版产品限制，不是官方限制），停用与待放置不占。`fingerprint_inputs` 哈希「列表内容 + 每个文件的真实字节」，**不是** widget 字符串——所以拖滑块、改选中项不会重新编码 30 条 Guide。
- 面板（沿用本插件已付过学费的设计）：节点本体是**固定高度 112px** 的摘要条（`🎬 打开 Guide 编辑器` / `🔄 刷新` / 状态行），任何按钮都不改变节点尺寸；编辑器是 `document.body` 上的浮层（拖标题栏移动、`resize:both` 改大小），关闭只停播放器 + 断 `ResizeObserver` + 移除 DOM，**绝不清空数据**。时间尺 / 图片轨 / 音频轨共用**一个**坐标变换（原型把图片放在 4%–96%、音频放在 0%–100%，那正是要避免的错法）。卡片区是共用的 `.h3lvm-deck` + 共用 `卡片大小` 100%–400% + 竖屏整帧缩略图；卡片自带 `秒`/`帧` 输入和 `启用/停用`·`放置`·`替换`·`复制`·`删除`，拖卡片 = 列表换序（复用 `ref_loader.js` 的落点算法），拖文件进网格走 `/upload/image`（音频也走这个，服务端没有 `/upload/audio`）。真实缩略图 + 真实波形（蓝色 = 会被使用的部分），`▶` 只播裁切段；≤40MB 才用 `decodeAudioData` 画波形，更大的只读 `<audio>` 时长并说明。选中/输入提交**不重建卡片区**（会销毁正在输入的 input）。底栏每条错误都是按钮，点了就切 tab + 选中 + 滚过去。
- 前端不会写出后端会拒绝的 JSON：配额在 `tryQuota()` 里先拦，否则重载时 `parseDocument` 抛错 → `readDoc` 走 catch → 数据直接丢。
- 用户实测中发现并已修（同日）：拖标题栏时浮层「往右下角飞出去、不跟鼠标」。根因是 `.h3guide-root` 用 `left:50%; top:50%; transform: translate(-50%,-50%)` 居中，而 `dragTitleBar` 起手把 `transform` 置 `none`，位置却取 `root.offsetLeft`（那是 50% 算出来的值，不是绘制出来的左上角）→ 等于瞬间把面板推走它自身尺寸的一半。修法：用 `getBoundingClientRect()` 读**绘制位置**，在同一个样式批次里写 `left/top` 并去掉 transform（不跳），并给标题栏加 `setPointerCapture`（快速拖出把手不再断跟随）。只改 `web/guide_timeline.js` → 复测只需 `Ctrl+F5`。
- 用户实测中第二处修正（同日）：节点上**不再显示 `guides` 那个 JSON widget**——`hideGuidesWidget()` 设 `widget.options.hidden = true`，与 `hideProjectWidget` / `hideRetiredWidgets` 同一手法。面板是这个列表唯一的编辑器，节点上留一个原始 JSON 框只是噪音，它的 tooltip 还会和面板说明互相打架。`options.hidden` 只影响前端布局，值仍按位置序列化，`readDoc`/`writeDoc` 与已保存的工作流照常。副作用是节点矮一个 widget 的高度（创建时的一次性变化，不是尺寸漂移）。
- 用户实测中第三处（同日，需求）：把节点拉高后摘要条下方一大片空白「要在弹窗里做操作？」。事实是 `addPanel` 把面板设成 `height:100%` 且只有 `getMinHeight`，框架把节点剩余空间全给了这个唯一可增长的 widget——**空白本来就属于我们的面板**，留白是浪费。第一版做的是**只读缩略时间轴**（时间尺 0–100% 五个刻度 + 图片轨 marker + 音频轨 clip，只用百分比定位，hover 显示名称与秒位，点击 = 打开编辑器）。
- 用户实测后否决只读版（「没有实现轨道上卡片以滑块形式自定义其发生时间的功能，且轨道上卡片过于小，无法展示其相关内容，可视化程度极低」）→ 改成**同一个渲染器的第二 surface**，不写第二套渲染器：`createSurface({ruler, trackImage, trackAudio, fitWidth, padding, tickGapPx})` + `measureSurface()` + `renderSurface()`，编辑器的 `renderTimeline()` 只是 `renderSurface(editorSurface)` 的守卫壳；节点内 `nodeSurface = createSurface({ fitWidth: true, padding: STRIP_MARKER_MAX / 2 + 4, tickGapPx: 64 })`，三行 `.h3guide-row`（时间尺 / 图片轨 / 音频轨）与编辑器同一 DOM 结构。所以节点内的 marker 与音频条**可以拖**（`attachLaneDrag(surface, el, guide, widthFrames)`，自动平移只在 `!surface.fitWidth` 下做），拖完卡片数字与详情同步更新；`refreshSelection()` 遍历 `[editorSurface, nodeSurface]`，`applyAllScrolls()` 让两份同时打开时互相同步。旧的 `mini*` DOM / 渲染 / `fitMini` / `MINI_MIN_H` 全部删除，`.h3guide-mini*` 样式全部删除。
- 卡片要「拉高节点就变大」：`.h3guide-marker { width: var(--h3guide-marker-w, 52px) }`（编辑器不设这个变量 → 仍是 52px），strip 在 `renderSurface()` 里按纯函数 `stripMarkerPlan({ laneWidth, count })` 写这个变量（40–72px），并让 `padding = ceil(markerWidth / 2) + 4` 与 marker 宽度成契约，否则首尾卡片会被裁；CSS 上两条 `.h3guide-strip-row-track { flex: 1 1 0; min-height: 46px }` 平分剩余高度，`.h3guide-strip .h3guide-track { height: 100% }`、marker/clip 用 `top: 4px; bottom: 4px` 而不是固定高度、内部缩略图与波形 `flex: 1 1 auto`。显示与否用 `stripVisible({ containerHeight, toolbarHeight, footerHeight, minimum: STRIP_MIN_H = 160 })` 这个**绝对像素**判断（不是 CSS 猜高度），不够就切 `.h3guide-strip-off`（`display: none`）；`ResizeObserver` 只调 `scheduleStrip()`（rAF 去抖 → `fitStrip()`），**绝不写 `node.size`**。默认 `NODE_PANEL_H = 112` 下它不显示——要看到它必须先把节点拉高。
- 有意偏差见 `GUIDE_TIMELINE.md` §5（不用 `asset_id` 间接层、fps 固定 24、`view_state`/`resolved_frame_count` 内嵌同一个 JSON、不公开 `guide_list` 插口、待放置用角标而不是独立区、未接撤销/重做、拖动限制边界而数值越界保留并报错）。
- 有意偏差见 `GUIDE_TIMELINE.md` §5（不用 `asset_id` 间接层、fps 固定 24、`view_state`/`resolved_frame_count` 内嵌同一个 JSON、不公开 `guide_list` 插口、待放置用角标而不是独立区、未接撤销/重做、拖动限制边界而数值越界保留并报错）。
- 时间尺的长度改成**填秒数**（用户反馈：`length` 还要自己换算帧不直觉，「一般做法」就是直接填秒）。输入 `length`(Int 帧) → `length_seconds`(Float 秒，0.1 步进，0–150，0 = 不设置)，节点上显示 `⏱ 视频时长（秒）`，与 `segment_duration` 同一套习惯。换算与对齐放在 `core/guide_timeline.py: align_frame_count()` / `frames_from_seconds()`（照抄原生 `comfy_extras/nodes_minimax_h3.py`：`max(5, round(s*24))` 再向上取 17n+5），前端 `web/guide_state.js: framesFromSeconds()` 是同一套算术的镜像，两边用同一批用例。优先级不变：本节点填的秒 > 上次运行的真实帧数 > 上游 generator 的 `length`（那个本来就是帧，照原样读，文案写明「length（帧）」）。面板把算式写出来而不是只报结果：`10 秒 × 24fps = 240 帧，向上对齐 17n+5 = 243 帧`；与上次运行不一致时照旧报冲突。这个值仍然不参与执行（`execute` 不读它，`fingerprint_inputs` 不含它），`validate_inputs` 的签名跟着改名。Float 输入自带可连线插口，所以时长也可以直接从外面接进来（Float 原语、别处算出来的时长）：`ownSecondsRaw()` 有连线时跟连线读、读不到就不画时间尺（不猜一个假的），没连线时才读控件。
- 测试（本轮）：`tests/test_guide_timeline_core.py` +2（`frames_from_seconds` 的 3.0s→73 / 10.0s→243 / 0.5s→22 / 写成文本的数字 / 别的 fps / 空值与非数字一律 0；`align_frame_count` 与原生规则逐点对齐）、`tests/test_guide_nodes.py` 的输入清单与「填时长不改变执行」改成秒；`work/guide_state.test.mjs` 84 → `86 passed, 0 failed`（新增「秒→帧」与「按文档自己的 fps 换算」两条，并把「与运行一致就不报冲突」换成 4.375 秒 = 107 帧这种真实对齐值）。全套 `Ran 537 tests in 21.757s ... OK`（日志 `work/t_length_full2.log`），`work/check_guide_imports.mjs` 干净，`work/check_plugin_web.ps1` `syntax failures: 0`。**本轮改了 Python 的输入 schema → 实测必须重启 ComfyUI**，`Ctrl+F5` 不够；`work/guide_length_unplace.mjs` 已改成填 10.0 秒并断言 `243 帧` 与那句算式，重启前跑它只会拿到旧 schema 的假失败，所以**这条浏览器用例本轮尚未实测**（重启后已实测，见下面两条）。
- 实测补记（ComfyUI 重启后）：运行副本的 schema 已确认带 `length_seconds`（`/object_info` 的 optional 里是 `FLOAT`，`default 0` / `max 150` / `step 0.1`）；`work/guide_length_unplace.mjs` 跑通 **`18 passed, 0 failed`**（T1–T16：填 `10.0` 秒 → 面板显示 `243 帧 / 10.13s` 与那句 `10 秒 × 24fps = 240 帧，向上对齐 17n+5 = 243 帧`；上次运行 107 帧时报冲突但仍画尺；`移出时间轴` 与 `删除` 用真实鼠标点击走通；保存重开后未放置状态和 `length_seconds === 10` 都还在）。报告 `work/probe/length-unplace-report.json`。
- 拖文件进卡池「完全没反应」的根因（用户报告）：`addFiles` 第一句 `files.filter(...)` —— drop 给的是 **`FileList`，没有 `.filter`**，所以处理器其实跑了、在第一句抛 `TypeError: files.filter is not a function`（`web/guide_timeline.js:1660`），面板因此一点反馈都没有。文件输入那条路没事，因为调用点先做了 `[...input.files]`。修法在根因处：`addFiles` 入口统一 `Array.from(files ?? [])`。顺带两处一致性：投放不再传当前 tab（每个文件按自己的扩展名决定是图片卡还是音频卡——`addGuides` 本来就是这样定 kind），只加到当前看不到的那一格时自动 `setTab` 并在提示里写「已切到音频卡片」，因为「加了卡片但看不见」和「没反应」在用户眼里是同一件事；投放命中区从 `.h3lvm-deck` 扩到整个 `.h3guide-pool`（标题栏和它的 padding 也算，高亮仍画在卡片网格上），`dragleave` 的守卫跟着改。两个拒绝分支现在都记 `native-dragover-rejected` / `native-drop-rejected` + 原因 + 落点命中元素，下次「没反应」能一次分清「处理器没跑」还是「跑了但提前返回」。
- 测试（投放）：新增 `work/guide_file_drop.mjs` D1–D12 **`12 passed, 0 failed`**（报告 `work/probe/file-drop-report.json`）。取证方式写清楚：事件是**合成的** `DragEvent` + 真 `DataTransfer`/`File`（字节从 `/view` 取），上传、写文档、渲染是真的；**Windows 资源管理器 → 页面这一段的真人手势 CDP 驱动不了，仍未实测**，要用户自己拖一次。宿主侧已排除：前端 `1.55.18` 的 bundle 里没有 `"Files"` 判断，文件投放挂在 litegraph canvas 的节点回调（`onDragOver`/`onDragDrop`）上，我们的编辑器挂在 `document.body`，不在那条链上，所以不存在宿主先消费事件。同名文件第二次投放被 `addGuides` 按 media key 去重（提示写「跳过 1 个（重复…）」）是有意的，探针因此每步换文件名。
- 回归（投放这一轮只改前端）：`work/guide_state.test.mjs` `86 passed, 0 failed`，`work/check_plugin_web.ps1` `syntax failures: 0`；复测只需 `Ctrl+F5`，不需要重启。
- 测试：`tests/test_guide_timeline_core.py` +37、`tests/test_guide_nodes.py` +29（含与显式串联原生 Add Guide 的**张量等价**、空列表透传、只用图片不调音频编码、七类错误、`validate_inputs`/`fingerprint_inputs`）；全套 `Ran 529 tests in 19.307s ... OK`（463 → 529），日志 `C:\Users\az\Documents\Codex\2026-10-02\xia\work/t28_full.log`。前端纯函数 `work/guide_state.test.mjs`（`node work/guide_state.test.mjs` 直跑，不需要测试框架）：只读版时 `35 passed`；改成第二 surface 后新增 `stripVisible`（阈值边界 239/240、非数字）与 `stripMarkerPlan`（各分支 + padding 与 `createScale` 的 fit-to-width 契约）共 3 条 → `38 passed, 0 failed`。改节点内时间轴这一轮只动前端，Python 仍复跑确认没被带坏：`Ran 529 tests in 20.421s ... OK`（N=529、日志无 `comfy_api unavailable`，日志 `work/t30_strip.log`）；`work/check_plugin_web.ps1` 语法检查 `syntax failures: 0`；`work/check_guide_imports.mjs` 确认 import 全部可解析、无未使用导入。
- 本轮**改了 Python + 前端**：复测要重启 ComfyUI，不是只 `Ctrl+F5`（最后一轮只改前端 → `Ctrl+F5` 就够）。真实面板尚未在本环境验证：打开/关闭编辑器不改变节点尺寸、时间轴缩放与横向滚动在第 0 帧和末帧不错位、拖图片与拖音频都更新轨道+卡片+详情、`▶` 只播裁切段、保存重开与两个节点同时打开不串数据、运行后时间尺换成真实帧数；把节点拉高（可用空间 ≥ `STRIP_MIN_H = 160px`）后摘要条下方出现**可拖动的完整时间轴**（缩略图 / label / 波形可见），在节点内拖 marker 或音频条 = 改 `frame_index` 且卡片数字与编辑器同步，两份同时显示时互相同步，缩回去它自动消失且不改变节点尺寸。任务书 D 章要求的四种截图还没做。

- 需求（用户报告）：「节点本身（未打开编辑器弹窗前）轨道和上面的卡片大小都无法调整尺寸（应该和编辑器内有一样的功能）」。
- 根因（读代码确认，不是猜）：节点内那条时间轴的轨道高度**只由 CSS 决定**——`.h3guide-strip-row-track { flex: 1 1 0 }` + `.h3guide-strip .h3guide-track { height: 100% }` 平分剩余高度，而卡片边长又被 `markerPlanFor` 里的 `MARKER_SIDE_MAX = 88` 和 `stripMarkerPlan` 的 `STRIP_MARKER_MAX = 72` 双重夹死。结果：拉高节点只会让轨道变高、卡片不变，且面板里没有任何控件。
- 新契约（一处控制、两处同步）：`view_state.lane_heights` 是**唯一**的尺寸控制，编辑器与节点内共用同一份数字；卡片边长 = 实际生效的轨道高度 − `MARKER_INSET*2`，`MARKER_SIDE_HARD_MAX = 320` 只做异常兜底，多张卡片时真正的限制是 fit-to-width 的宽度预算（`stripMarkerPlan` 的上限从 72 改为 `MARKER_SIDE_HARD_MAX`）。删掉 `STRIP_MIN_H` / `STRIP_MARKER_MAX` / `stripVisible`，换成 `stripRoom()` + `stripLaneHeights()`：面板高度是天花板，两条轨道按比例一起缩到放得下、各自不低于 `STRIP_LANE_MIN`（图片 52 / 音频 44），完全放不下就整条时间轴自己隐藏（绝对像素判断，绝不写 `node.size`；门槛仍是 196px，与旧值一致，所以老工作流不会因为这次改动突然看不到时间轴）。
- 为什么不加第二个「卡片大小」控件：卡片是正方形，边长就是轨道内高——两套控件只会互相打架（放大就重叠）。所以读数直接显示那个数字，用户看得见卡片随谁变。
- 前端：节点内时间轴的头部加 `图片轨 − px ＋` / `音频轨 − px ＋`（复用 `.h3guide-secondary` 与 `.h3guide-lane-px`，与编辑器同一设计语言）；读数显示**实际生效**的高度，被面板夹住时变琥珀色并把原因写进 title（`面板只放得下 96px（想要 112px）`）；`applyStripHeights()` 写内联高度，CSS 去掉那两条让轨道自己长高的规则；`setLaneHeight()` 不再要求编辑器是打开的，两个 surface 一起 `syncMarkerSide()`；strip 的 − / ＋ 以「当前画出来的高度」为基准，被夹住时 − 立刻有效、＋ 不会偷偷把编辑器要的数往下改。
- 测试：`work/guide_state.test.mjs` 86 → **89 passed, 0 failed**（新增 `stripRoom` / `stripLaneHeights` 的 196/195 边界、按比例缩到面板、不越下限、floor 后超量回退、`stripMarkerPlan` 的新上限，以及「一条卡片时轨道高度就是控件、12 条时宽度预算才是限制」）；`work/check_plugin_web.ps1` `syntax failures: 0`；`work/check_guide_imports.mjs` 无缺失/未使用导入。本轮只改前端 → 复测只需 `Ctrl+F5`，Python 未动。
- **实测状态（区分清楚）**：本轮的验收来自**用户在真实 ComfyUI 里的手动实测**（节点加载、Guide 编排、节点内 − / ＋ 改变轨道与卡片大小、竖屏素材可读），用户据此明确授权推送与打 tag。自动化浏览器探针 `work/guide_strip_size.mjs`（T1–T20：真实鼠标点节点内的 − / ＋，断言轨道高度与 `--h3guide-marker-side` 同步变化、`node.size` 全程不变、面板不够高时夹住并标琥珀、完全放不下时自动隐藏、保存重开后 `lane_heights` 与 `strip_open` 仍在）**已写好但一次都没跑过**——写探针时 ComfyUI 没在运行（8188 无监听），之后用户手动测过就没有补跑。下一轮再动这块尺寸逻辑，先把它跑一次再说「通过」。
- 运行副本陷阱（本轮「缺失节点」的根因，记录在案）：`E:\ai\ComfyUI-aki-v3\ComfyUI\custom_nodes\H3-Long-Video-Manager` 是 GitHub 的 git 检出，秋叶启动器的「更新」执行 `git reset` 到已推送 commit（reflog：`reset: moving to beafc17`），**未推送的运行时改动会被整批回退**——本轮被回退的是 `comfyui/nodes.py`（Guide 注册）等 8 个文件，而未跟踪的新文件（`comfyui/guide_nodes.py`、`web/guide_*.js/css`）留着，于是插件能加载、节点类型却没注册，前端报「缺失节点」。规则：开发期间不要用启动器更新这个插件；推送完成后再跑一次 `work/sync_h3lvm.ps1`（提权，判据是 `mismatch: 0`），让运行副本与远端一致。

## 2026-10-21 · `1921477`（上一基线）

- 快照：改动前的状态就是 `21f9eba`，已在 `archive/2026-10-19-21f9eba/`，本轮不另建旧快照。提交后的快照在 `archive/2026-10-21-1921477/`（77 个文件，与 `git ls-files` 数量一致，由 `git archive 1921477` 解出，因此与提交内容逐字节相同）。
- 需求（用户报告）：「拖拽视频进入库内后序号是 1，删掉它再放另一个视频，序号就变成 2」。原来的规则不一致——拖拽会按位置重编号，但删除保留稳定 id、`next_id` 只增不减，于是库里会出现空号，新导入的号越推越大。
- 新规则（一条，用户视角）：**投放库的 `segment_id` 就是卡片位置，永远 1..N 连续无空号**。导入 = 追加到末尾（拿 `卡片数 + 1`）；删除 = 后面的卡片编号依次补位；拖拽 = 按新顺序重排（已有）。空库重新从 1 开始。
- `next_id` 语义改为**存储序号**：只用于 `_storage_stem()` 生成 `vidNNN`，只增、名字永不复用。这是补位后的关键护栏——ids 1,2,3 删掉 1 后 `vid003.mp4` 坐到了 2 号，若新导入按卡片号拿 3 号就会 `os.replace` 覆盖它。JSON 字段名不变，不做 schema 迁移，靠 docstring 说明。
- `MAX_SEGMENT_ID = 999` 从「编号上限」改为**卡片数上限**（`卡片数 + 1 > 999` 才拒绝），存储序号不设上限；报错文案改成「卡片已到 999 上限」。
- `comfyui/uploaded_video_store.py`：新增 `_renumber(videos)`（**按传入顺序**发号，不在这里排序——在导入/删除路径由调用方先 `sorted(key=_order_key)`，拖拽路径直接传新顺序，否则重排会被这里的排序抵消）；`import_upload()` 卡片号 = `len(videos)+1`、存储名仍用 `next_id`；`delete_upload()` 删记录后补位，回滚快照改成逐记录拷贝（`_renumber` 原地改 `segment_id`，浅拷贝会让回滚拿到新号）；`resolve_upload()` 报错补一句「编号就是卡片顺序，删掉卡片后后面的会顺延」。
- `web/picker_mode_state.js`：纯函数 `followCardAfterDelete(beforeIds, deletedId, selectedId)`——把被删的号从面板当前顺序里去掉再数一遍就是新号，不需要文件名也不需要服务端配合；非正整数（`null`/`0`/`"abc"`）一律返回 `null`。
- `web/h3lvm_picker.js`：删除前先从 DOM 读 `deckIds()`（卡片顺序 = 当前编号），删除后选中项跟到新编号并在状态行写 `当前选中：视频 2（后面的编号已顺延）`；被删的正是选中项时仍落到第一张。裁切片段库不受影响（`loadDeck` 的 `beforeIds` 只走 uploads 分支）。
- 测试：`tests/test_upload_store.py` 改 3 例（`test_the_numbers_are_the_card_order`、`test_the_card_cap_says_what_to_do` 用 999 条假卡片而不是真导入 999 次、`test_a_delete_already_closes_the_gap`），新增 4 例（删除后补位且 `resolve_upload` 读到正确视频、补位不复用文件名 `vid003`→新卡片拿 `vid004`、空库重新从 1 开始且存储名不复用、存储序号很高也不挡第一张卡片）；`work/picker_mode_state.test.mjs` +9 条 `followCardAfterDelete` 断言。定向 `tests.test_upload_store tests.test_upload_api` 全绿（日志 `work/t27b_uploads.log`），`check_h3lvm_syntax.ps1` 49 文件 0 错，前端 `node --check` 与纯函数测试全绿。
- 测试（真实跑过）：推送前在 `1921477` 上复跑全套 `Ran 463 tests in 21.523s ... OK`，**0 skip**（日志 `C:\Users\az\Documents\Codex\2026-10-02\xia\work\t27_full2.log`）。
- 环境坑（本轮新发现，重要）：在**开发副本**里跑全套必须设 `$env:COMFYUI_ROOT = 'E:\ai\ComfyUI-aki-v3\ComfyUI'`。不设时 `tests/test_node_schema.py::_comfy_roots()` 找不到 ComfyUI 根（它只认这个环境变量，或「仓库位于 `custom_nodes/` 下」），于是 62 个用例静默 skip，而 `tests/test_smart_split_node.py` 在模块级使用 `NODES.__package__`（此时 `NODES` 是 `None`）直接 `ImportError`——看起来只是「1 个 error」，实际整轮少测了 62 个。判据：`Ran N tests` 的 N 必须是 463，且日志里不得出现 `comfy_api unavailable`。
- 本轮**改了 Python + 前端**：复测要**重启 ComfyUI**，不是只 `Ctrl+F5`。面板实测（用户已复测，通过）：导入→删除→再导入，卡片号仍是 1；删中间卡片后后面的卡片号顺延、点它们输出的是各自的视频；选中第 3 张删掉第 1 张，选中的是那张视频本身、状态行显示新号；拖拽换序仍照旧。

## 2026-10-19 · `21f9eba`（上一基线）

- 快照：`archive/2026-10-19-21f9eba/`（77 个文件 / 1016 KB，与 `git ls-files` 数量一致，排除 `.git`、`__pycache__`、`archive/`）。开发副本 `main` = `21f9eba`（`feat: picker dual-source library with uploaded video deck and output scaling`，18 文件 / +4433 −146），annotated tag `v1.3.0`（tag 对象 `7e65ca2`）；上一基线快照仍在 `archive/2026-10-19-f8d2adc/`。
- 本基线包含第二十一至第二十四轮：`H3 Segment Picker` 双模式素材库（裁切片段库 / 视频投放库）、投放库的独立存储与上传 API、投放视频的按需解码与输出分辨率、输出分辨率的「自定义」档。逐轮细节见下一节 `f8d2adc` 的「本轮改动」条目，那里同时记着两轮环境坑（测试必须提权跑，否则一个用例都没真的跑；EOL 因文件而异）。
- 测试（真实跑过）：推送前在 `21f9eba` 上复跑全套 `Ran 459 tests in 20.300s ... OK`（上一基线 328 → 459，日志 `C:\Users\az\Documents\Codex\2026-10-02\xia\work\t26_push.log`）；前端纯函数 `C:\Users\az\Documents\Codex\2026-10-02\xia\work\picker_mode_state.test.mjs` 全绿；`C:\Users\az\Documents\Codex\2026-10-02\xia\work\check_h3lvm_syntax.ps1` 对运行副本 49 个 `.py` 语法自检 0 错误。
- 运行副本：`C:\Users\az\Documents\Codex\2026-10-02\xia\work\sync_h3lvm.ps1` 复制 9 个文件，全仓核对 77 文件 / 0 mismatch / 0 stale。这四轮都改了 Python + 前端 → 复测要**重启 ComfyUI**，不是只 `Ctrl+F5`。
- 未验证（不宣称通过）：投放库在浏览器里的实测仍未确认——拖入 MP4 出卡片、点卡片输出对应视频、卡片拖拽换序后选中的 `segment_id` 跟着视频走、`输出分辨率` 选预设或自定义后卡片上的「源 → 输出」与运行结果一致、裁切片段模式完全不受影响。这些只有自动化测试覆盖，面板行为需要用户重启 ComfyUI 后实测。

## 2026-10-19 · `f8d2adc`（上一基线）

- 快照：`archive/2026-10-19-f8d2adc/`（68 个文件 / 814 KB，与 `git ls-files` 数量一致，排除 `.git`、`__pycache__`、`archive/`）。开发副本 HEAD = `f8d2adc`（tag `v1.2.0` 之后的文档提交），已有 tags `v1.0.0`、`v1.1.0`、`v1.2.0`。这四轮改动已合并为一个提交 `21f9eba`（`main`）并打 annotated tag `v1.3.0`（tag 对象 `7e65ca2`），逐轮细节保留在本节。
- 本轮改动（第二十四轮：输出分辨率的「自定义」档）：
  - 需求：预设档位（3840/1920/1280/960/640/480）不够用时，用户要能自己填最长边——例如只想压到 1440 或 1080，卡在两档之间。
  - `comfyui/video_decode.py`：`RESIZE_CUSTOM = "自定义（自己填最长边）"` 追加在 `RESIZE_OPTIONS` 末尾（**标签里故意不带数字**，数字来自另一个控件）；`CUSTOM_MAX_SIDE_DEFAULT = 1920`（打开自定义的人多半就是为了压 4K）；新增 `parse_custom_max_side()`：填的数字**夹到** `MIN_MAX_SIDE`–`MAX_MAX_SIDE` 而不是判为无效——人填 90000 是「能多小就多小」的意思，而 `scale_plan()` 从不放大，比源大的上限本来就等于不缩放；读不出数字（空、`abc`、`nan`、0、负数）才是 0 = 不缩放。`parse_max_side(value, custom_max_side=None)` 只在标签等于 `RESIZE_CUSTOM` 时读第二个参数，预设档位完全忽略它。`__all__` 补 `RESIZE_CUSTOM` / `CUSTOM_MAX_SIDE_DEFAULT` / `MIN_MAX_SIDE` / `MAX_MAX_SIDE` / `parse_custom_max_side`。
  - `comfyui/nodes.py`：Picker 追加 `io.Int.Input('custom_max_side', default=1920, min=MIN_MAX_SIDE, max=MAX_MAX_SIDE, step=2)`，**追加在 `output_size` 之后**（位置恢复的老规矩：更早的工作流保留四个值，按预设语义运行）；`output_size` 的 tooltip 用 `RESIZE_CUSTOM` 拼出「选『自定义』时用下面的自定义最长边」，选项文案仍然只有一份来源；`execute(..., custom_max_side=)` → `_execute_upload(..., custom_max_side)` → `parse_max_side(output_size, custom_max_side)`。
  - `comfyui/server_api.py`：`GET /h3_lvm/uploads` 多读一个 `custom_max_side` 查询参数，交给同一个 `parse_max_side()` + `scale_plan()`，卡片上的「输出」尺寸永远等于运行时真会发生的事。
  - `web/h3lvm_picker.js`：`customSizeWidget` 的中文 tooltip；`syncCustomSizeLabel()` 按状态改 label——裁切模式 `自定义最长边（裁切不用）`、投放模式选到自定义时 `自定义最长边（生效中）`、否则 `自定义最长边（选自定义后可用）`。**不隐藏控件**：忽隐忽现的字段看起来像坏了，节点高度还会跳，这是本仓库既有的做法（`输出分辨率（裁切不用）` 同理）。改档位或改数字都会重读卡片列表，因为卡片上的「源 → 输出」行跟着变。
  - 测试：`tests/test_video_decode.py` +7（`TestCustomMaxSide` 6：用填的数字、默认值可用、越界夹到边界、没有数字=不缩放、小数仍是像素数、预设档位忽略填的值；`TestDecodeScaled.test_a_typed_custom_size_decodes_at_that_size` 用不在预设里的 30 真解码一次 64×36 → 30×16）；`tests/test_upload_api.py` +4（自定义数字规划卡片、没有数字不缩放、预设忽略填的值、越界夹到 16px 下限且高度保持偶数）；`tests/test_node_schema.py` +1（`custom_max_side` 的 default/min/max 必须等于解码器的同一组常量），并把输入顺序锁成五项。顺带修掉一处会被新档位打穿的旧断言：`test_each_option_parses_to_the_number_it_shows` 原来假定每个档位标签里都有数字，现在改成「没有数字的那一项必须正好是 `RESIZE_CUSTOM`」，这样拼错也藏不住。全套 `Ran 459 tests in 19.027s ... OK`（447 → 459，日志 `work/t25_full.log`；定向 `work/t25_targeted.log`）。前端纯函数 `work/picker_mode_state.test.mjs` 仍全绿（卡片格式化逻辑本轮没改）。
  - 快照说明：本轮与第二十一至二十三轮同处未提交分支，仍没有新的 commit 短 hash，因此不另建快照；推送时四轮一起打 tag（建议 `v1.3.0`）——已按此执行：四轮合并为 `21f9eba`，tag `v1.3.0`。
  - 本轮**改了 Python + 前端**：复测要重启 ComfyUI，不是只 `Ctrl+F5`。真实面板尚未在本环境验证：选到「自定义」后标签变成 `（生效中）`、填 1440 后卡片出现 `源 … → 输出 …`、运行输出确实是那个尺寸、切回预设档位时填的数字不再影响结果。
- 本轮改动（第二十三轮：投放视频的「输出分辨率」）：
  - 需求：用户要「投放 4K 视频交给 MiniMax 压力太大，加一个分辨率设置」。根因比显存更早：`_decode_frames()` 的内存预估用的是**源**尺寸，4K 会被 `MAX_DECODE_BYTES = 12 GiB` 在解码前直接拒掉，所以「4K 读不出来」其实是还没开始解码就被挡住。
  - 设计边界：只缩放解码，绝不重编码。投放库的文件仍然逐字节保存，改这个设置只多一次解码，切回原始没有任何损失；缩放等比、对齐偶数（编码器要求）、绝不放大（放大只会糊），计划尺寸放不下时就不缩。口径是**最长边**而不是「1920×1080」，因为 16:9 和 9:16 在最长边下含义一致。
  - `comfyui/video_decode.py`：`RESIZE_ORIGINAL` / `RESIZE_OPTIONS`（`原始（不缩放）` + `最长边 3840/1920/1280/960/640/480`）/ `DEFAULT_RESIZE` / `MIN_MAX_SIDE`、`MAX_MAX_SIDE`（16–8192，越界或读不出数字一律按「不缩放」处理——旧工作流里的陌生值不该让运行崩掉）、纯函数 `parse_max_side()`（从标签里取数字）与 `scale_plan()`；`_decode_frames(path, target_fps, max_side = 0)` 的预估改用**计划**尺寸、报错文案点名「输出分辨率」这个控件，逐帧 `pixels()` 在累积进张量之前缩放，缩小用 `Interpolation.AREA`（老版本 PyAV 没有这个枚举就退回默认插值）；`info` 增加 `source_width/source_height/max_side/scaled`。选项表只存这一份，节点控件、卡片文案和测试都从这里取。
  - `comfyui/nodes.py`：Picker 追加 `io.Combo.Input('output_size', ...)`，**追加在 `source_mode` 之后**——更早保存的工作流保留三个值并按原始尺寸解码；`execute(..., output_size = DEFAULT_RESIZE)` → `_execute_upload()` → `parse_max_side()` + `decode_video(path, max_side = ...)`；日志带上 `(from WxH)`，方便确认这次到底缩没缩。
  - `comfyui/server_api.py`：`GET /h3_lvm/uploads` 接受 `output_size` 查询参数，服务端用同一个 `scale_plan()` 给每张卡片补 `out_width/out_height/out_scaled`（算法只有一份，卡片不会宣传一个运行时不会发生的尺寸；`import` 放在 handler 内，保持这个模块不依赖 torch）。
  - 前端：`web/picker_mode_state.js::uploadInfoLines()` 在 `out_scaled` 时加一行 `源 W×H → 输出 W×H（原文件不变）`——不缩放时这一行完全不出现，避免用户以为所有视频都被缩过；`web/h3lvm_picker.js` 把控件 label/tooltip 设为中文，投放模式是 `输出分辨率`、裁切模式是 `输出分辨率（裁切不用）`（不隐藏控件，沿用本文件已有的按模式改 label 做法），改档位后重新拉卡片。
  - 测试：`tests/test_video_decode.py` +16（`TestScalePlan` 7：等比、偶数、绝不放大、边界与越界；`TestParseMaxSide` 3；`TestDecodeScaled` 6：真实 ffmpeg 缩放解码、帧数不变、渐变帧序不变、内存预估用计划尺寸并断言报错含「输出分辨率」）；`tests/test_upload_api.py` +6（`TestUploadOutputSize`，含「磁盘上的原文件永不被重缩放」——用 `probe_video` 复读卡片文件确认宽高仍是源尺寸）；`tests/test_node_schema.py` 锁定 Picker 四个输入的顺序，并断言选项表与 `NODES.RESIZE_OPTIONS` 同源。全套 `Ran 447 tests in 18.363s ... OK`（424 → 447，日志 `work/t23_full.log`）。前端纯函数 `work/picker_mode_state.test.mjs` 全绿（新增：4K 卡片出现「源 → 输出」行、未缩放不加行、服务端没给 flag 也不加行）。
  - 环境坑（本轮踩到，记下来）：本仓库的 EOL **因文件而异**——`comfyui/nodes.py` 与 `web/*.js` 是 CRLF，`comfyui/video_decode.py`、`comfyui/server_api.py`、`tests/*.py` 是 LF，README/VERSION 是混合。定点替换的脚本必须按目标文件的 EOL 自适应（`const EOL = text.includes("\r\n") ? "\r\n" : "\n"`），否则锚点全部失配。
  - 快照说明：本轮与第二十一、二十二轮同处未提交分支，改动前状态 = `archive/2026-10-19-f8d2adc/` + 前两轮未提交改动，仍没有新的 commit 短 hash，因此不另建快照；推送时三轮一起打 tag（建议 `v1.3.0`）。
  - 本轮**改了 Python + 前端**：复测要重启 ComfyUI，不是只 `Ctrl+F5`。真实面板尚未在本环境验证：选 `最长边 1920` 后卡片出现「源 → 输出」行、运行输出确实是 1920×1080、切回 `原始（不缩放）` 恢复源尺寸、裁切片段模式完全不受影响。
- 本轮改动（第二十二轮：投放视频库的卡片拖拽排序）：
  - 需求：任务书把「卡片拖拽排序」列在本期不做，但用户明确要求补上——投放视频库的卡片顺序就是长视频的时间轴顺序，只靠编号猜太容易出错。裁切片段库仍然不可拖拽（不改 `H3 Long Video Manager` / `H3 Smart Split` 的裁切算法、Motion Context 行为与存储结构）。
  - 编号规则（与用户确认过）：拖拽后重编号——第一张卡片 = `segment_id 1`，其余依次 1..N；文件与封面不改名（所有读取都走索引记录，重排只写一个索引、不搬一个字节），`next_id` 只增不减，所以重排不会让下一次导入撞上已有编号；顺序和当前一致时不写盘。
  - `comfyui/uploaded_video_store.py`：`_order_key()`（按编号排序，读不出编号的记录排到最后而不是让列表崩掉）、`list_uploads()` 返回前统一按编号排序（面板顺序 = 库顺序，手工编辑过的索引也按左上到右下读）；新增 `reorder_uploads(project, ordered_ids)`（`@project_locked`；`order` 必须是当前编号的完整排列，缺号/多号/重复/非列表都给中文报错——少一个编号会静默丢卡片，另一个标签页的编号会挪错视频）；模块 docstring 增加「Why reordering renumbers」。
  - `comfyui/server_api.py`：`POST /h3_lvm/uploads/reorder`（跨源 403、非 JSON 415、`ValueError` 400、写盘失败 409），成功后广播 `h3_lvm/uploads_changed` 且 `action: "reorder"`。
  - `web/picker_mode_state.js`：纯函数 `moveIds(ids, from, to)`（把一次拖拽变成新的 id 顺序，什么都没动时返回 `null`）、`renumberedId(order, assetId)`（被拖的视频排完是几号，面板据此跟着它）。
  - `web/h3lvm_picker.js`：上传卡片 `draggable = true` + `data-order-index`；文件拖放与卡片拖拽两条通道按拖拽负载区分（外部文件必带 `Files`，自己的卡片带 `application/x-h3lvm-card`）；落点用 `ref_state.js::insertPosition()` 对全部卡片矩形计算（卡片缝隙、工具行、网格外几像素都仍然有意义——那是参考加载器「拖不动」的四个原因，这里不重复犯）；`pointerdown` 兜底补 `dragstart`、指针停在卡片区上下 28px 内自动滚动、`.h3lvm-drop-before` / `.h3lvm-drop-after` 提示落点；`commitOrder()` 成功后把选中的 `segment_id` 跟到被拖视频的新编号（选中跟着视频走，不是跟着数字走），`reordering` 期间忽略自己触发的广播。
  - `web/h3lvm_picker.css`：`.h3lvm-dragging`、`.h3lvm-drop-before`、`.h3lvm-drop-after`、`[draggable="true"] { cursor: grab }`。
  - 文档：README 中英各加「卡片顺序就是时间轴顺序」一段、`POST /h3_lvm/uploads/reorder` 接口行、WebSocket `action` 增加 `"reorder"`，措辞改成「导入、删除或重排…」。
  - 测试：`tests/test_upload_store.py` 新增 `TestCardOrder` 13 例（重编号、文件不动、节点按新编号读到对应视频、缺号/多号/重复/非列表被拒且索引不变、同序不写盘、重排后 `next_id` 不撞号、删除后重排补洞、手工打乱仍按编号列出、没有有效编号被拒、不碰裁切库）；`tests/test_upload_api.py` 新增 `TestUploadReorder` 7 例（200 + 事件、半个顺序 400、缺 `order` 400、非 JSON 415、跨源 403、另一个项目不受影响）；`C:\Users\az\Documents\Codex\2026-10-02\xia\work\picker_mode_state.test.mjs` 增加 20 条断言（`moveIds` / `renumberedId`）→ 通过。全量 `Ran 424 tests in 16.565s ... OK`（上一基线 404 + 本轮 20）。
  - 环境坑（本轮踩到，记下来）：测试**必须提权跑**。沙箱会拒绝测试的子进程写 `%TEMP%`，`tests/_media_clip.py` 里的 ffmpeg 以 `Permission denied` 失败（退出码 4294967283），于是一整轮看起来在跑、其实一个用例都没真的测过。判断方法：`python -c` 里直接调一次 `make_clip`，几秒就能暴露。提权后全套 16.6s。
  - 快照说明：本轮与第二十一轮同处未提交分支，改动前的状态 = `archive/2026-10-19-f8d2adc/` + 第二十一轮的未提交改动，没有新的 commit 短 hash 可用，因此本轮不另建快照；推送时与后续轮次一起打 tag（建议 `v1.3.0`）。
  - 本轮**改了 Python + 前端**：复测要重启 ComfyUI，不是只 `Ctrl+F5`。真实面板的拖拽手感、跨标签页广播、重启后顺序仍在，尚未在本环境验证。
- 本轮改动（第二十一轮：Segment Picker 双模式素材库，按任务书 `H3_Segment_Picker_Dual_Mode_Development_Plan.md`）：
  - 需求：同一个 `H3 Segment Picker` 支持两个物理隔离的库——原有的裁切片段库（Manager / Smart Split 的产物）与新的「投放视频」库（用户自己拖进来的完整视频）。四个输出（IMAGE / AUDIO / frame_count / segment_id）不变，旧工作流零迁移。
  - `comfyui/uploaded_video_store.py`（新增）：根目录 `<output>/h3-lvm-video-uploads/<项目>/`，与裁切库 `<output>/h3-lvm/` 同级不嵌套；索引 `h3lvm_upload_index.json`（原子写 + 每项目 RLock），原文件存 `files/vidNNN.<ext>`，封面 `vidNNN_cover.jpg`。稳定 ID 从 1 递增且永不复用（上限 999，超了给中文提示说明怎么处理）；`safe_suffix()` 只允许 `.mp4 .m4v .mov .mkv .webm .avi .ts .mts`，最终扩展名以探测结果为准而不是信文件名；`checked_upload_file()` 拒绝任何越出 `files/` 的存储名；`list_uploads()` 只读不建目录，文件被外部删掉时给 `missing_file: true` 而不是让卡片消失；索引损坏时报错并保留文件，不静默清空。
  - `comfyui/video_decode.py`（新增）：PyAV（`av`）做探测与解码——`probe_video()` 给出宽高、精确帧率（保留 1001 分母）、时长、有无音轨、是否 VFR；`write_cover()` 出最长边 320 px 的 JPEG 封面；`decode_video(path, 24)` 按 24fps 采样（源快则抽帧、源慢则按同一时间轴补齐），音频重采样 44.1 kHz 并按实际播放时长对齐，无音轨返回 `None` 由节点补静音。上限 `MAX_DECODE_BYTES = 12 GiB` / `MAX_DECODE_FRAMES = 200000`，超了明确报错而不是悄悄截断。缺 PyAV 时错误里带 `pip install av`，不会谎称「这个视频坏了」。
  - `comfyui/nodes.py`：`source_mode` 追加在 `project_name` / `segment_id` 之后（ComfyUI 按位置恢复 widget 值，所以更早保存的工作流两个值不动、继续读裁切库），`execute()` 只做路由，未知模式直接报错不猜；`_execute_segment()` 是原逻辑原样搬过去，新增 `_execute_upload()` 走 `resolve_upload()` + `decode_video()`，`frame_count` 取实际张量长度而不是容器声称的时长，无音轨时补 `frame_count / 24` 秒的 44.1 kHz 静音。
  - `comfyui/server_api.py`：`_scope()` 增加 `uploads`，`_project_library()` 把「列表/新建/删除」做成一张表（新增一个库就是加一行）；`GET /h3_lvm/uploads`、`POST /h3_lvm/uploads/import`（multipart，`project` 字段必须在 `file` 之前，分块写入 `.upload_*` 临时文件，>2 GiB → 413，浏览器留空选择器时不当成「0 字节的视频」）、`POST /h3_lvm/uploads/delete`；写接口全部过 `_csrf_block()`；新事件 `h3_lvm/uploads_changed`。  - 前端：新增纯函数 `web/picker_mode_state.js`（模式常量与中文文案、两模式状态的读/写/归一化、时长与帧率文案、是否需要「输出按 24fps 采样」的标注、浏览器能否直接播放及原因）；`web/h3lvm_picker.js` 重写为双模式面板——顶部两个按钮（`🎬 裁切片段` / `📥 投放视频`）、按模式绑定各自的项目菜单、投放模式下的 `＋ 载入视频` + 隐藏 file input + 卡片区拖放（`acceptsFileDrop` 限定 uploads 模式 + `Files` + 落在卡片区内，`preventDefault/stopPropagation` 抑制 ComfyUI 顺手生成 `LoadImage`）、逐个上传且失败可重试、每个请求绑定 `generation + mode + project` 并用 `isStale()` 丢弃过期响应、切模式时 abort 旧菜单的 AbortController 再重建；状态存在 `node.properties["h3lvm_picker_modes"]`，`onConfigure` / `onExecuted` 经 `node._h3lvmRefresh` 走 `syncFromGraph()` 以工作流里的值为准 seed，所以旧工作流不会被另一个模式的默认值盖掉。
  - `web/project_menu.js`：把 `segments / uploads / image / audio` 的计数字段与文案（`N 段` / `N 个视频` / `N 张参考`）、输入框 placeholder、空库提示、删除确认警告做成显式的 `SCOPE_CONFIG`，不再靠猜字段名。`web/preview_overlay.js` 的 `openPreview(seg, signal, infoText)` 支持传入投放视频的说明文案。`web/h3lvm_picker.css` 新增 `.h3lvm-mode-row` / `.h3lvm-mode-btn(.active)` / `.h3lvm-mode-hint` / `.h3lvm-upload-btn` / `.h3lvm-file-input` / `.h3lvm-drop-zone(.drop-in)` / `.h3lvm-seg-name` / `.h3lvm-missing-badge`；卡片基准尺寸、缩放档位与竖屏整帧显示规则没动。
  - 本期明确不做：投放视频的裁切、Motion Context、17n+5 补齐、合并、拼接、跨库转移、自动切模式。（卡片拖拽排序原本也列在本期不做，用户随后明确要求补上，见第二十二轮。）`web/ref_loader.js` 与两个参考加载器、Manager / Smart Split 的裁切算法、MC 行为和存储结构一行未改。
  - 测试：新增 `tests/test_upload_store.py` 26 例（两库根目录互不包含、同名项目是两个文件夹、删一边不动另一边、稳定 ID 不复用、同名文件两张卡、伪装成 mp4 的音频文件被拒、索引损坏被报告而不是隐藏、外部删除显示 missing、路径穿越与存储名越界、列表不建目录）、`tests/test_video_decode.py` 20 例（精确帧率含 1001 分母、VFR 标记、非视频/纯音频被拒、24fps 直通、30fps 抽帧、低帧率补齐、时长与帧数一致、音频与播放长度一致、无音轨返回 `None`、帧序跟随源、损坏文件可读报错、封面是小 JPEG、竖屏封面保整帧）、`tests/test_upload_api.py` 19 例（scope、导入/删除、空文件、超 2 GiB、同源校验、事件）、`tests/test_picker_dual_mode.py` 11 例（只有两个 widget 的旧工作流仍读裁切库、显式 `segments` 走同一条代码路径、未知模式报错、有声/无声/30fps/VFR 端到端、投放模式不依赖 Manager 或 Smart Split、同名项目在两边是不同素材）；`tests/_media_clip.py` 与 `tests/_plugin_import.py` 是生成小视频与「有/无 ComfyUI 都能导入插件」的测试助手；`tests/test_node_schema.py` 锁定三个输入的顺序与 `source_mode` 默认值。全套 `Ran 404 tests ... OK`（328 → 404，须设 `COMFYUI_ROOT=E:\ai\ComfyUI-aki-v3\ComfyUI`）。前端纯函数 `C:\Users\az\Documents\Codex\2026-10-02\xia\work\picker_mode_state.test.mjs` 39 条断言全绿（新增）。
  - 本轮**改了 Python + 前端**：复测要重启 ComfyUI，不是只 `Ctrl+F5`。真实 ComfyUI 面板的手工验证（两个模式的切换视觉、拖放不生成 `LoadImage`、重启后两模式状态各自恢复、多标签页事件隔离、浏览器播放 `.mkv` / `.avi`）尚未做，见交付报告的「无法在本环境验证」一节。
## 2026-10-11 · `0b8d8b5`（上一基线）

- 快照：`archive/2026-10-10-1bd48e2/`（57 个文件 / 532 KB，与 `git ls-files` 数量一致，排除 `.git`、`__pycache__`、`archive/`）。开发副本 HEAD = `1bd48e2`，已有 tags `v1.0.0`、`v1.1.0`。
- 本轮改动（第十三轮：图片/音频参考加载器，按企划书 `H3_Image_Audio_Reference_Loaders_Implementation_Brief.md`）：
  - 动机：官方 `MiniMaxH3ReferenceToVideo` 的参考端口是 Autogrow 的编号端口（`ref_image_0..8`、`ref_audio_0..2`），要喂参考图就得在画布上摆一排 `LoadImage` + 缩放节点。两个新节点把素材收成卡片，端口数量与顺序保持不变，空槽输出真 `None`（官方 execute 里 `if img is None: continue`）。
  - `core/ref_size.py`：`plan_size()` / `clamp_megapixels()`。目标 MP（默认 0.25，范围 0.02–8.0）+ 32 像素网格，不裁切、不补边；候选尺寸来自理想尺寸 / 面积匹配 / 比例匹配三组，再用确定性 tie-break 选一个。实测最坏（目标 ≥ 0.25 MP、源比例 ≤ 3:1）面积误差 8.95%、比例误差 3.57%；480×640 @ 0.25 MP 会主动让一点比例去保面积。`MAX_SOURCE_PIXELS = 40_000_000`。
  - `core/ref_media.py`：`parse_media_list`（面板 JSON 或纯文件名列表、路径安全校验、超量截断）、`resolve_media_path`、`media_fingerprint`（含 size + mtime_ns，同名替换文件会重新解码）、`fill_slots`（空槽是真 `None`，不是占位）。
  - `comfyui/ref_nodes.py`：`H3 Image Reference Loader`（`media_files` + `target_megapixels`，9 个 `io.Image.Output(display_name="ref_image_N")`，带 `validate_inputs` / `fingerprint_inputs` / `execute`）、`H3 Audio Reference Loader`（3 个 AUDIO）。图片走 PIL + `ImageOps.exif_transpose` + LANCZOS + `convert("RGB")` → `[1,H,W,3]` float32 0..1（与 `LoadImage` 同形状）；音频复用 `comfy_extras.nodes_audio.load`，不重采样、不截断、不混音。
  - `comfyui/server_api.py`：新增 `GET /h3_lvm/ref_plan?w=&h=&mp=`。卡片上显示的输出尺寸由服务端唯一实现回答，避免在 JavaScript 里复刻一份算法（那就是「卡片说的和 tensor 不一样」的来源）。
  - 前端：`web/ref_state.js` 纯函数（解析/序列化、增删改与排序、槽位上限、槽位标签、尺寸与音频信息文案）；`web/ref_loader.js` 面板（复用 `card_zoom.js` / `thumb_fit.js` / `dom_panel.js` 与 `h3lvm_picker.css` 的类名 token，固定 `PANEL_H`、不自调高度；上传走 `/upload/image`，支持拖放 / 添加 / 替换 / 移除，槽位顺序靠拖拽卡片改；图片卡片显示 `源 W×H → 输出 W×H · 实际 MP`，音频卡片内嵌播放器 + 时长 / 采样率 / 声道）；`web/ref_loader.css` 只放 `h3ref-*` 局部样式。
  - 实测反馈（用户）：「改成可以通过拖拽卡片调换顺序的形式，不要用按钮，按钮太不方便，删除和替换图片按钮可以保留」。做法：卡片 `draggable = true`，去掉 `←` / `→` 两个按钮与 `reorder()`，改用 HTML5 拖放换序。外部文件拖入与自己的卡片换序用 `dataTransfer.types` 是否含 `"Files"` 区分（ComfyUI 在 document 上监听文件拖放，会顺手建一个 `LoadImage` 节点，所以这里的拖放事件 `stopPropagation`）；插入位置按卡片中线前/后判定，空白网格 = 追加到末尾，落点用蓝色边线提示（`.h3lvm-card.h3ref-drop-before` / `.h3ref-drop-after`，必须带 `.h3lvm-card` 前缀才压得过 picker 的 `:hover` box-shadow，且本表在 picker 之后加载）。排序仍然只改 `ref_state.js` 的纯函数 `moveEntry()`，用例不变。
  - 实测反馈（用户）：「有些时候拖拽失效啊，感觉触发区域给的太小了」。四个真正的原因：① 落点只认「指针正下方那张卡」，卡片间的缝隙会把卡片甩到末尾；② `dragover`/`drop` 只挂在网格上，指针一出卡片区就完全没反应；③ 缩略图 `<img>` 自带可拖拽，抓图片时拖拽源变成图片，拖影只有一小块（「触发区域很小」的直觉来源）；④ 卡片区会滚动，超出可视范围的行根本拖不到。
  - 修法：新增纯函数 `ref_state.js::insertPosition(rects, x, y, draggedIndex)`（按「到矩形边缘的距离」找最近卡片，同行按中线前/后、不同行按上/下；指针在被拖卡片自己上面返回 -1，即「这次松手不改变什么」），几何信息是参数因此可用桩网格监测试；拖拽事件改挂到整个面板（文件上传仍然只认网格内的落点，避免在工具行上松手就丢文件）；`thumb_fit.js` 给缩略图与模糊背景图加 `draggable = false`，拖拽源回到卡片本身（拖影是整张卡片）；指针停在卡片区上下边缘 28px 内时用 `requestAnimationFrame` 自动滚动；再加一条保险：若浏览器没报 `dragstart`，就用 `pointerdown` 记下的卡片与 `dataTransfer.types` 里的 `CARD_MIME` 把来源补回来。新增 3 个用例（缝隙、末行下方、拖到自己、无效 rects）→ `ref_state.test.mjs` 16/16。
  - 测试：新增 `tests/test_ref_size.py`、`tests/test_ref_media.py`、`tests/test_ref_nodes.py`（0/1/9 图的槽位与 `None` 位置、顺序 = 卡片顺序、batch = 1、RGBA/L/EXIF、缓存键、schema 名称与顺序、音频不重采样）。前端纯函数另测 `C:\Users\az\Documents\Codex\2026-10-02\xia\work\ref_state.test.mjs`（13 例，`node <file>` 直跑；`node --test` 在沙箱里 `spawn EPERM`）。全量 `Ran 250 tests ... OK`（必须用 ComfyUI 自带解释器：系统 `C:\Python314` 缺 `packaging`，节点测试会全部 skip）。
- 本轮改动（第十四轮：图片参考的缩放选项，按补丁企划书 `H3_Image_Resize_Methods_Plan_Patch.md`）：
  - 需求：图片适配固定为「按比例缩放」（不裁切、不补边、不拉到统一宽高），但把两件事交给用户——重采样算法，以及要不要把小图放大到目标 MP。
  - `core/ref_size.py`：新增 `RESAMPLE_METHODS`（`Lanczos` / `Bicubic` / `Bilinear` / `Nearest`，默认 `Lanczos`）、`DEFAULT_UPSCALE_SMALL_IMAGES = False`、`clamp_resampling_method()`（大小写与前后空格宽容，未知值直接报错，不会静默退回默认滤镜）；`_source_size()` 统一校验源尺寸（`plan_size` 也改用它）；`plan_grid_align()`（已在网格上就原样返回，否则 ±1 网格步候选，排序键＝面积变化 → 比例误差 → 单轴变化 → 面积 → w → h）；`plan_reference()` 返回 plan + `mode`（`target_mp` / `grid_align`）。`plan_size()` 行为不变。
  - 语义边界（写进文档也写进测试）：「关闭放大」= 不对小图施加目标面积，**不是**「像素数绝不增加」——300×200 会变成 320×192，因为 32 网格要求这样；已经在 32 网格上的小图原样返回并跳过重采样。
  - `comfyui/ref_nodes.py`：schema 在 `target_megapixels` 之后新增 `io.Combo.Input("resampling_method")` 与 `io.Boolean.Input("upscale_small_images")`；`RESAMPLE_FILTERS` 把四个选项映射到 `Image.Resampling`（老 Pillow 用 `getattr(Image, "Resampling", Image)` 回退到旧常量）；`validate_inputs` / `fingerprint_inputs` / `execute` 都接两个新参数，缓存键的 `extra` 含 mp + method + upscale；`build_image_slot()` 走 `plan_reference()`，计划尺寸与源尺寸一致时跳过 resize；日志加 `mode` / `method`。
  - `comfyui/server_api.py`：`GET /h3_lvm/ref_plan` 增加 `upscale=0|1` 并返回 `mode`；新增 `_query_bool()`。卡片上的尺寸仍然只有服务端一份实现。
  - 前端：`ref_state.js::sizeLine()` 在 `mode === "grid_align"` 时追加「（未放大，仅对齐网格）」；`ref_loader.js` 给两个新控件加中文标签与 tooltip（`🔍 重采样算法`、`↕ 放大小图至目标 MP`），MP 与放大开关的 callback 统一挂上并重新取 `/ref_plan`（重采样算法不改变尺寸，所以不触发取 plan），面板底部说明「关闭放大小图时小图只做网格对齐」。
  - 测试：`tests/test_ref_size.py` 新增 `TestClampResamplingMethod` / `TestPlanGridAlign` / `TestPlanReference`（大图两种模式都到目标面积、小图只在开启时放大、关闭时实际 MP 与源 MP 相差 ≤10%、已对齐小图完全不动、恰好等于目标面积时只做网格对齐、极端比例仍保证 32 倍数、确定性、非法输入报错）；`tests/test_ref_nodes.py` 新增 `TestImageResizeSettings`（`RESAMPLE_FILTERS` 的键 == 选项表、2×2 四色图 Nearest 只出现 4 色而 Bilinear 会插值、换滤镜会改变像素、已对齐小图 + 关闭放大 → tensor 尺寸 == 源尺寸、开启放大才变大、缓存键随 mp/method/upscale 变化、未知滤镜给出可读错误）并把 schema 断言改成四个输入 + options/default；前端 `work/ref_state.test.mjs` 新增「未放大」标记一例。全套 `Ran 275 tests ... OK`（250 → 275），前端 17 项全绿。
  - 待办：用户实测通过后才 commit / annotated tag（建议 `v1.2.0`）/ 推送，并同步 `C:\Users\az\Documents\Codex\CHANGELOG.md`、`PROJECTS.md`。
- 本轮改动（第十五轮：参考加载器的卡片「跳过 / 放回」）：
  - 实测反馈（用户）：「加一个卡片屏蔽功能，可以选卡片让它被绕过并置于后排」「放在替换和移除按钮并列就好了，选 b」。
  - 做法：不新增输入、不新增概念——跳过状态存在同一个 `media_files` 里（条目带 `"skip": true`），节点在填槽位之前把它过滤掉。列表只有一个规范顺序：槽位卡片在前、已跳过卡片在后，所以卡片在卡片区里的位置就是它在列表里的下标。
  - `core/ref_media.py`：`parse_media_list()` 只在跳过为真时写入 `skip`（旧列表的解析结果一字不变），槽位上限只数活动条目（已跳过的不会被截断）；新增 `is_skipped()` / `split_entries()` / `active_entries()`。
  - `comfyui/ref_nodes.py`：两个节点的 `execute` 与 `fingerprint_inputs` 走 `active_entries(...)`（跳过项不进缓存键，因为节点根本不读它），`validate_inputs` 不变；节点描述与 `media_files` tooltip 说明「已跳过的卡片不输出、不占槽位」。
  - `web/ref_state.js`：`normalizeEntry` / `serializeMedia` 同样只在跳过时写 `skip`；新增 `isSkipped` / `splitEntries` / `countActive` / `skipAt` / `restoreAt` / `restoreAll` / `moveActive`；`parseMedia` 与 `addEntries` 的上限只数活动卡片，新卡片永远插在槽位区块末尾、已跳过区块之前。
  - `web/ref_loader.js`：卡片按钮行改成 `↻` / `⊘` / `✕`（被跳过的卡片是 `↩` / `✕`）；卡片区画成两个区块，中间一行 `⊘ 已跳过 N 张 · 不输出、不占槽位（不能拖动）`；添加行新增 `↺ 全部放回`（只在有跳过项时出现，槽位不够的留在后排）；状态行追加 `已跳过 N（不占槽位）`；拖动只认槽位区块（`data-active-index`，被跳过的卡片既不能被拖也不是落点）；面板底部说明补 `⊘ 跳过` / `↩ 放回`。
  - `web/ref_loader.css`：`.h3ref-skipped`（灰边、变暗、缩略图去饱和、不可拖动；卡片尺寸不变，所以网格不会重排）、`.h3ref-deck-sep`（`grid-column: 1 / -1`，与 `.h3lvm-empty` 一样不占列）、`.h3ref-restore`（与添加按钮同一外壳，添加行不会多出一行）。
  - 卡片编号（实测反馈，用户）：「汉字的参考图 0 其实是不对的，官方 skill 把 ref_image_0 写成 picture1，也就是说对于用户来说看到【参考图1 → ref_image_0】才是符合直觉的」。卡片标题只由 `slotTitle()` 生成，它改成 1-based（0 号槽位显示「参考图 1」）；端口名仍由 `slotName()` 生成，保持 0-based，注释里写死两者不许互换。README 中英文的示例跟着改成 `参考图 3 → ref_image_2`。
  - 卡片高度对齐（实测反馈，用户）：「因为有放大和未放大的区别而导致的换行，卡片不好看了，你不能都对齐一下」「不应该是省略，而是（没有）信息行的默认高度和有信息行的维持一致」。卡片的信息块改成固定两行（`web/ref_loader.css` 的 `.h3ref-deck .h3lvm-seg-info`：`line-height: 1.3` + `min-height/max-height: 26px` + `overflow: hidden` + `overflow-wrap: anywhere`）——尺寸没读回来之前就把高度占好，读回来不会跳，长文本换到第二行也不会把这张卡片顶得比邻居高；不用省略号截断，装不下的内容在卡片 tooltip 里（`ref_loader.js` 的 `setInfo()` 同时写文本和 tooltip）。卡片上的「未放大」标记改成短形式 `· 未放大`，完整句子只在 tooltip（`sizeLine({ full: true })`），因为长句子正是把那两行撑爆的东西。
  - 槽位语义：跳过第 2 张后后面的卡片自动补位；放回永远放在槽位顺序末尾，槽位满时什么都不动并给出可读提示（`槽位已满（9），请先移除或跳过一张再放回`）。
  - 测试：`work/ref_state.test.mjs` 新增 9 项（JSON 往返、上限只数活动卡片、`skipAt`/`restoreAt`/`restoreAll`/`moveActive` 的边界与不可变性、新卡片不会插到已跳过卡片后面、已跳过文件仍算重复）；`tests/test_ref_media.py` 新增 4 项；`tests/test_ref_nodes.py` 新增 3 项（跳过的卡片不占槽位且后面补位、已跳过卡片不会把在用的卡片挤出槽位、跳过项不改变缓存键）。全套 `Ran 282 tests ... OK`（275 → 282），前端 26 项全绿（17 → 26）。
  - 待办：用户实测通过后才 commit / annotated tag（建议 `v1.2.0`）/ 推送。

- 本轮改动（第十六轮：参考加载器的「项目参考预设」）：
  - 需求（用户）：「类似 H3 Segment Picker 的新建项目和删除项目，以及下拉菜单。方便用户存储参考图预设组合——但是，我们不要重复存储参考图，而是读取 input 文件夹，保存对应项目下参考图的路径并随时调取，节省空间。」
  - 做法：预设就是卡片列表本身（`{filename, subfolder, type}`），只存路径、不复制媒体；位置 `<output>/h3-lvm/<project>/h3lvm_references.json`，与项目索引同目录。图片与音频分开（9/3 上限不同），已跳过的卡片一并保留。
  - 新增 `comfyui/ref_presets.py`：`preset_path()`、`load_references()`（缺失或损坏 → 空；某一类读不动不影响另一类；条目重新过 `parse_media_list()`，因为素材目录可能已经变过）、`@project_locked save_references(project, kind, entries)`（kind 只认 image/audio，条目同样过解析器，tmp + `os.replace` 原子写，只替换该 kind，另一类原样保留）。复用 `segment_store` 的 `get_project_dir` / `project_locked` / `sanitize_project_name`。
  - `comfyui/server_api.py`：新增 `GET /h3_lvm/ref_presets?project=` 与 `POST /h3_lvm/ref_presets`（CSRF / 415 / 400 / 409 语义与其他写接口一致）。
  - `comfyui/ref_nodes.py`：两个节点的输入**末尾**追加 `io.String.Input("project_name", default=DEFAULT_PROJECT)`（末尾是刻意的：`configure()` 按位置恢复控件值）；`validate_inputs` / `fingerprint_inputs` / `execute` 都带 `project_name=DEFAULT_PROJECT` 默认参数，缓存键与像素都不含它。
  - 前端：`web/ref_state.js` 新增 `pickPresetEntries(preset, kind)`（防御式：缺文件、半截 JSON 都读成空）；`web/ref_loader.js` 第一行挂共用的 `web/project_menu.js`（切换 / 新建 / 删除整库，与其他可视化节点同一套），添加行新增 `📥 载入项目预设` / `📤 存为项目预设`，载入走现成的 `addEntries()`（去重与槽位上限同规则），存为用 `serializeMedia()`（含已跳过卡片），状态行追加 `项目预设 N` / `项目预设 空`，空库时载入按钮禁用，`🔄 刷新` 与切换项目都会重读预设；`project_name` 控件在面板运行后隐藏。面板高度只在创建时增加（380→440 / 300→360），按按钮仍然不会改变节点尺寸。
  - 测试：新增 `tests/test_ref_presets.py` 14 例（往返与顺序、只存路径且体积 <400 字节、存一类不动另一类、已跳过卡片保留、面板 JSON 直接可用、按 kind 的上限、已跳过不占上限、非法 kind、非法条目不落盘、缺文件不建库、损坏文件读为空且下次保存修好、某一类坏不影响另一类、项目名 sanitize）；`tests/test_ref_nodes.py` 的 schema 断言加上 `project_name`，并新增默认值断言与「换项目不改变缓存键」；前端 `work/ref_state.test.mjs` 新增 3 项。全套 `Ran 298 tests ... OK`（282 → 298），前端 29 项全绿（26 → 29）。
  - 本轮**改了 Python**：复测要重启 ComfyUI，不是只 `Ctrl+F5`。

- 本轮改动（第十七轮：预设还原的是「排列」，不只是文件）：
  - 实测反馈（用户）：「不仅仅保留图片路径，还要存为预设时候的跳过/取用情况及它们的排序顺序。」
  - 定位：预设文件本来就带顺序与 `skip`（`parse_media_list()` 原样保留顺序，只在跳过为真时写 `skip`），丢东西的是前端——`loadPreset()` 走 `addEntries()`，那是**追加**：预设的顺序被面板当时的顺序吃掉，被跳过的条目还会落进槽位区块。
  - `web/ref_state.js`：新增 `applyPreset(entries, incoming, max)`——预设的卡片按保存顺序在前、各自的活动/跳过状态原样恢复；面板上有而预设没提的卡片排在后面（载入不能删工作）；槽位上限只数活动区块，且截断从尾部吃，所以先丢「预设没提的卡片」，不会丢用户存下的卡片。返回 `restored / parked / kept / truncated / ignored` 供状态行如实汇报，其中 `kept` 只统计真正回到列表里的，状态行不会同时说「保留了 2 张」和「没载入 2 张」。
  - `web/ref_loader.js`：`loadPreset()` 改走 `applyPreset()`；载入前后 `serializeMedia()` 一致时直接回答「卡片已经和该预设一致」；状态行改成 `已按保存的顺序载入 N 张 · 其中 M 张保持跳过 · 保留 K 张预设外的卡片 · 超出 9 个槽位，未载入 X 张`；`项目预设 N` 在有跳过项时显示 `项目预设 N（含 M 张已跳过）`；两个按钮的 tooltip 写明「含排列顺序与跳过状态」。
  - 测试：`work/ref_state.test.mjs` 新增 6 项（还原顺序、还原跳过状态且槽位数不变、预设外的卡片排在后面、上限先吃预设外的卡片、同一预设载入两次结果不变、坏条目与重复条目只计数不致命、空预设不动面板）；`tests/test_ref_presets.py` 新增 1 项（磁盘文件本身带顺序与 `skip`，活动条目仍与旧格式一字不差）。全套 `Ran 299 tests ... OK`（282 → 299），前端 35 项全绿（29 → 35）。
  - 本轮只改前端与测试；但第十六轮的 Python 改动（`ref_presets.py`、`project_name` 输入）还没重启验证过，复测仍然要**重启 ComfyUI**，不是只 `Ctrl+F5`。

- 本轮改动（第十八轮：音频卡片可以裁时间窗，卡片视觉与其它可视化节点统一）：
  - 实测反馈（用户）：「H3 音频参考加载器那个节点…需要有类似于 load audio 原生节点的，每个音频可以调节其时长及开始时间点的设置接口，并且，它的可视化有点问题，卡片大小不是很匹配我们其他的类似节点的设计语言」。
  - 做法：裁切存在**条目本身**（`start` / `duration`，单位秒），不新增节点输入——每张卡片要自己的窗口，而且只有这样它才能跟着保存、刷新和项目预设一起活下来。语义完全对齐 ComfyUI 原生 `TrimAudioDuration`（`comfy_extras/nodes_audio.py:426`）：`start` 可为负＝从片尾往前算，`duration` 为 0＝一直到片尾，两端都夹进文件内。
  - `core/ref_media.py`：`media_kind()`（按扩展名分 audio / image / other，与前端 `ref_state.js` 同一套正则）、`_clean_seconds()`（有限数字；接受写成文本的数字，因为手写 widget 会加引号；拒绝布尔 / NaN / 负时长）、`parse_media_list()` 只对音频扩展名读 `start` / `duration`（0 或缺失不写字段 → 旧列表字节不变）、`trim_range()`、`trim_audio()`（按采样数切 `[batch, channels, samples]` 的最后一轴，两端 clamp，裁空用中文报错，无裁切时原样返回同一个 dict）、`media_fingerprint()` 每条目加入 `|{start}|{length}`（换窗口必须重新解码）。
  - `comfyui/ref_nodes.py`：`build_audio_slot(path, start, duration)` 解码后裁切；`execute` 从条目取 `trim_range()` 并把窗口写进日志；节点 description 与 `media_files` 的 tooltip 说明这两个字段。仍然不重采样、不混音，采样率与声道原样交给 H3。
  - `web/ref_state.js`：新增 `normalizeTrim` / `trimRange` / `resolveTrim`（镜像后端的 clamp，返回 `{first, last, empty}`）/ `hasTrim` / `formatTime`；`normalizeEntry` 只对音频条目保留 `start` / `duration`；`serializeMedia` 写这两个字段（0 不写）；`audioInfoLine` 显示 `0:01.00 → 0:04.00 · 3.00 秒 … 全片 12.40 秒`，裁空再加 `⚠ 裁切后没有样本`。
  - `web/ref_loader.js` + `web/ref_loader.css`：音频卡改成与图片卡**同规格**——删掉 `.h3ref-deck-audio`（240px 的列宽下限）与 `.h3ref-audio`（32px 的原生播放器条），共用 `--card-min` / `--thumb-h`，由同一个 `卡片大小` 控件缩放；缩略图框里画**波形 canvas**（蓝色＝会被输出，灰色＝不会；`▶` 只播这一段，点波形在窗口内定位，`timeupdate` 到窗口末尾自动停），卡内一行 `开始` / `时长` 数字输入 + `↺` 清除裁切；被跳过的卡片保留这一行但禁用输入，两个区块的卡片因此等高、网格不重排。波形重绘用 `ResizeObserver`（改卡片大小不用重渲染），`render()` 开头 `stopPlayers()` 停掉旧卡片的播放器与观察器。
  - 测试：`work/ref_state.test.mjs` 新增 9 项（秒数解析与四种拒绝、`trimRange`、`resolveTrim` 的负 start / 越界 clamp / 裁空 / 未知长度、`formatTime`、卡片文案含窗口与「全片」、只有音频条目带窗口、未裁切列表序列化字节不变、窗口经 widget JSON 往返、预设连窗口一起还原）→ 44 全绿（35 → 44）。Python 新增 15 项（`media_kind`、只给音频写窗口、写成文本的数字、负 start、四种非法数字、`trim_range`、窗口进缓存键、节点槽位长度＝窗口长度且样本与整段对齐、`trim_audio` 采样数 / 负 start / 两端 clamp / 裁空中文报错 / 无裁切返回同一对象、预设文件本身带窗口）→ `Ran 314 tests ... OK`（299 → 314）。
  - 本轮改了 Python（`core/ref_media.py`、`comfyui/ref_nodes.py`）：复测必须**重启 ComfyUI**，再 `Ctrl+F5`。

- 本轮改动（第十九轮：项目菜单的计数口径 + 载入预设改成整组替换）：
  - 实测反馈（用户）：「H3 图片参考加载器有两个问题，下拉菜单的项目名后的括号内一直都是空，（空）。另一个问题是，载入项目预设后，预设外的卡片还是别留下为好。想要加新卡片就后续再加。」
  - 定位一：`GET /h3_lvm/projects` 只回答 `segments`（视频片段数），而 `web/project_menu.js` 不分面板都用它写菜单文案——只用参考加载器的库片段数永远是 0，于是菜单里永远是（空）。
  - `comfyui/ref_presets.py`：新增 `count_references()`（该库 images + audios 的条目数；缺文件/坏文件按 0，与 `load_references()` 同一口径；计数不会建库）和 `list_projects_with_reference_counts()`（在 `list_projects_with_counts()` 的结果上补 `references`——只有这个模块知道预设存在哪）。`comfyui/server_api.py` 的 `GET /h3_lvm/projects` 改用它，每项变成 `{"name", "segments", "references"}`。
  - `web/project_menu.js`：`createProjectMenu()` 新增 `countFor`（默认 `"segment"`，Picker / Manager 的文案一字不变）。`"reference"` 时菜单项写 `项目名 (4 张)`、行内计数写 `共 4 张参考`、空库写 `无预设`；删除确认按库里真实内容拼（先参考预设，再已保存片段，两者都没有就说「空的素材库文件夹」）。`web/ref_loader.js` 传 `countFor: 'reference'`。
  - `web/ref_state.js`：`applyPreset()` 从「预设在前 + 保留预设外卡片」改成**整组替换**——之后面板就是预设（顺序与跳过状态原样），预设外的卡片（含已跳过的）被移除；返回值里的 `kept` 改成 `dropped`（被移除的张数）。理由：预设就是一个项目的参考组合，留着剩下的等于下一轮悄悄带上用户已经不要的参考，要加卡片走正常「＋ 添加」。槽位上限仍然只数活动区块，截断仍然吃预设的尾部。
  - `web/ref_loader.js`：状态行改成 `已按保存的顺序载入 N 张 · 其中 M 张保持跳过 · 移除了 K 张预设外的卡片 · 超出 9 个槽位，未载入 X 张`；`📥 载入项目预设` 的 tooltip 写明「预设外的卡片会被移除」。空预设时载入按钮本来就是禁用的，所以「整组替换」不会把面板清空。
  - 测试：`work/ref_state.test.mjs` 把 5 项改成替换语义（预设外的卡片被移除、被点名的卡片仍按预设顺序、槽位上限吃预设尾部、第二次载入没有可移除的、空预设会清空面板、音频窗口那条断言 `dropped`）并新增 1 项 → 45 全绿（44 → 45）。Python 新增 `TestProjectCounts` 4 项（两类合计计数、坏文件按 0、计数不建库、`/h3_lvm/projects` 同时带两个计数）→ `Ran 319 tests ... OK`（315 → 319）。
  - 本轮改了 Python（`comfyui/ref_presets.py`、`comfyui/server_api.py`）：复测必须**重启 ComfyUI**，再 `Ctrl+F5`。

- 本轮改动（第二十轮：参考库按类型分开存，图片一套、音频一套）：
  - 需求（用户）：「H3 音频参考加载器不应该和 H3 图片参考加载器共用一个素材库存储项目。因为文件性质不同。」
  - 定位：预设文件 `<output>/h3-lvm/<project>/h3lvm_references.json` 里 `images` / `audios` 两个列表并存，而这个目录本身就是**视频素材库**的 bin。`GET /h3_lvm/projects` 列的是视频库，所以两个加载器的菜单看到的是同一串项目名，一个按片子命名的库看起来同时装着两种材料——参考图片和参考音频是给不同端口的不同材料，一份按片子命名的组合说明不了哪些配音属于它。
  - `comfyui/ref_presets.py` 整文件重写：`KIND_ROOTS = {"image": "h3-lvm-image-refs", "audio": "h3-lvm-audio-refs"}`（在 `get_base_dir()` 下，与视频库 `h3-lvm/` 同级）、`LIST_KEY = "references"`（一个文件只装一份列表）、`LEGACY_KEYS`（旧共用文件里的两个键）。**kind 一律是第一个参数**：`library_dir` / `ref_project_dir` / `preset_path` / `load_references` / `save_references` / `count_references` / `list_reference_projects` / `create_reference_project` / `delete_reference_project`。锁改成本模块自己的 `_library_lock`（按参考库目录的 realpath 取键，不再借用视频 bin 的锁），写文件仍是 tmp + `os.replace`。删掉 `KIND_KEYS` 与 `list_projects_with_reference_counts()`——计数不再由视频库转发，`list_reference_projects(kind)` 直接列本类库并带 `references` 数。
  - 一次性迁移 `_migrate_legacy(kind, name)`：本类库缺文件时读旧共用文件，把**本类**那份列表复制进本类库并返回；旧文件为空或读不动就不建库（不能凭空造出一个用户没存过的库），旧文件本身不删不改。迁移只在第一次读时发生，之后以库为准。
  - `comfyui/server_api.py`：新增 `_scope()`（默认 `segments`，即视频库；`image` / `audio` 是那一类的参考库）。`GET /h3_lvm/projects?scope=segments|image|audio` 按 scope 选目录；`POST /h3_lvm/project` 与 `POST /h3_lvm/project/delete` 的 body 带 `scope`，新建/删除只作用于那一个库；`GET /h3_lvm/ref_presets?project=&kind=` 的 kind 非法时返回中文 400。
  - 前端：`web/project_menu.js` 的 `countFor` 换成 **`scope`**（`segments` / `image` / `audio`），列表请求带 `?scope=`、新建与删除的 body 带 `scope`，文案口径不变（`N 段` / `N 张参考`、`空库` / `无预设`）；`web/ref_state.js` 的 `pickPresetEntries(preset)` 去掉 kind 参数、读 `preset.references`；`web/ref_loader.js` 传 `scope: spec.kind`，预设请求带 `&kind=${spec.kind}`。
  - 测试：`tests/test_ref_presets.py` 按新 API 重写为 29 例（两类互不可见、各有根目录与项目列表、预设不落在视频 bin 里、新建/删除只作用于本类、删除要重名确认、旧共用文件按类各复制一次且只复制一次、迁移后以库为准、空/坏的旧文件不建库、新文件里的旧两列表形状不再被读、计数只数本类）。`work/ref_state.test.mjs` 跟着改成 `{references: [...]}` 并新增「旧两列表形状不再被读」→ 45 全绿。全套 `Ran 328 tests ... OK`（319 → 328）。
  - 实测反馈（用户）：「全改坏了」——两个参考加载器的面板整个不见了，只剩 `media_files` / `project_name` 两个裸控件。定位：`web/project_menu.js` 里 `api.fetchApi(...)` 那一行被改成了带 `?scope=` 的模板串却**丢了后面的 `, { cache: "no-store" })`**，这是**语法错误**；ES 模块语法错误 = 整个扩展不注册 = 所有面板（Picker / Manager / Smart Split / 两个加载器）一起消失，`node --check` 之前只对 `ref_loader.js` 做过，没覆盖共用模块。修：补回 fetch 的第二参数与右括号；同时补上本轮漏掉的 `const refScope = scope !== "segments"`（`binTotal` / `countLabel` / `emptyLabel` / `deleteWarning` 都在用它，否则运行期 ReferenceError），并清掉一处重复注释。防呆：`work/check_plugin_web.ps1`（两个插件的 `web/*.js` 逐个 `node --check`，当前 0 failures）。复测点：两个加载器的 `📦 项目素材库` 列表互不相同；新建/删除只影响本类；拆分之前存的旧预设仍能在对应加载器里看到（第一次读时各复制一份）。
## 2026-10-09 · `0a1cdd4`（上一基线）

- 快照：`archive/2026-10-08-06a259a/`（49 个文件 / 406 KB，与 `git ls-files` 数量一致，排除 `.git`、`__pycache__`、`archive/`）。
- 该基线包含 v1.0.0（annotated tag `v1.0.0` = tag 对象 `ba4897c` → commit `305a5d7`）、`06a259a` 文档提交，以及本轮的 `0a1cdd4`（第十一轮 Smart Split + 第十二轮合并模式，18 文件 / +2754 −240）。annotated tag `v1.1.0` = tag 对象 `5d7b5a3` → commit `0a1cdd4`。`origin/main` = `0a1cdd4`，`v1.0.0` 与 `v1.1.0` 均已推送。
- 下一轮改动前的快照：`archive/2026-10-09-0a1cdd4/`（57 个文件 / 531 KB，`git archive HEAD` 解出，与 `git ls-files` 数量一致）。
- 仓库目录已原地整理：本轮在 `C:\Users\az\Documents\Codex\2026-10-02\xia\work\h3lvm-release-clone`（`robocopy` 整仓副本，含 `.git`）里跑测试并 commit/tag/push，然后逐文件哈希证明副本 == 刚测过的工作树、`git merge-base --is-ancestor 06a259a HEAD` 与 `git fsck` 通过，再把原目录改名、把已推送的副本移到 `C:\Users\az\Documents\Codex\projects\H3-Long-Video-Manager`。现在开发副本 HEAD = `0a1cdd4`、`main...origin/main` 无差异、`.git` 可写，不需要用户再跑 `git fetch` / `git reset`。旧目录只剩 `C:\Users\az\Documents\Codex\projects\h3lvm-old-git-06a259a`（内容与现仓库完全冗余，其中 `.git` 在沙箱里删不动），可手动删除。
- 本轮改动（第十二轮：Smart Split 卡片去掉说明文字 + 卡片区新增合并模式）：
  - 用户实测反馈两条：① Smart Split 卡片下面那两行规则说明「没必要存在」→ 删掉。`web/deck_panel.js` 去掉 `footerLines` 参数与渲染，`web/h3lvm_smart.js`、`web/h3lvm_manager_panel.js` 不再传文案。② 自动切分有时会把一个镜头切得很小，需要手动把某些片段接回去 → 新增合并模式。
  - 交互（用户要求）：`🔗 合并模式` 按钮与 `🔄 刷新`、`卡片大小` 同一行同高度（复用 `.h3lvm-refresh-btn` 保证等高）；进入后点选**相邻**卡片（点不相邻的重新从该段开始选），`✅ 确认合并` 只在选中 ≥2 段时可点；卡片加 `.picked` 高亮与 `已选` 角标，状态行显示已选编号。合并模式是 UI 状态，不落盘、不进工作流。
  - 编号规则（用户要求）：新卡片 id = 所选里最小的 id；随后把 `> 最大所选 id` 的段按升序整体前移 `len(ids)-1`，目录 `segNN` 与目录内 `tensors/thumbnail/mp4` 文件名一起改名，索引条目 retag，改名中途失败按逆序回滚。结果：库内始终 1..N 连续无空洞，`输出片段编号` 不会出现读不到的号。前端在合并成功后同步跟随（段内 → merged_id，之后 → 减 shift）。
  - `comfyui/segment_store.py`：新增 `merge_segments(project, segment_ids)` 与辅助 `new_tag_prefix`、`_segment_dir`、`_checked_merge_ids`、`_load_segment_tensors`、`_rename_segment_dir`、`_retag`、`_MERGE_OWN_KEYS`。语义：只接受 ≥2 且编号连续的 id；帧率或分辨率不一致 → 中文 `ValueError`；**每段（首段除外）去掉头部 `context_frames` 重叠帧**，并按 `overlap / fps * sample_rate` 同步裁掉音频头部（否则每个接缝重复一帧、音频逐段累积漂移）；只要有一段缺音频，合并结果整段不带音频；`video_dtype` 沿用首段；拼接全程保持 packed（int8/fp16），不做 float32 展开（一段长镜头就是几 GB）。meta 写 `segmentation_method="manual_merge"`、`merged_from`、`merged_parts`、`merged_overlap_frames`、`main_start/main_end/main_frames`。
  - `save_segment()` 新增可选 `cover_source`（已解码张量，封面取所选首段的主区间帧，不用为封面再解码整段）；`_encode_mp4()` 先 `_decode_video()`，否则 packed int8 在旧路径下会出黑帧。
  - `comfyui/server_api.py`：新增 `POST /h3_lvm/merge`（CSRF 与其他写接口一致），`ValueError` → 400、`MemoryError` → 507（中文提示）、`OSError` → 409；成功后广播 `h3_lvm/changed {"project", "merged_id"}`。
  - `web/h3lvm_picker.css`：`.h3lvm-merge-btn.on`、`.h3lvm-merge-ok:not(:disabled)`、`.h3lvm-card.picked`、`.h3lvm-pick-badge`。Manager 与 Smart Split 共用 `web/deck_panel.js`，所以两个节点同时得到这个功能。
  - 测试：新增 `tests/test_merge_segments.py` 11 例（帧序与去重叠、封面取自主区间、dtype 保持、帧率/分辨率不符、重排与文件改名、末尾合并不重排、非法 id 组合、缺段、连续两次合并、音频拼接与缺失）→ 全套 `Ran 195 tests ... OK`（184 → 195，须设 `COMFYUI_ROOT`）。桩 DOM `C:\Users\az\Documents\Codex\2026-10-02\xia\work\test_deck_panel.mjs` 扩到 29 项（合并交互、不相邻重开选择、POST body、id 顺延）。
  - 本轮**改了 Python**：复测要重启 ComfyUI，不是只 `Ctrl+F5`。

- 本轮改动（第十一轮：新增 `H3 Smart Split` 节点，按镜头切段）：
  - 需求来源是用户的《H3 Long Video Manager — Smart Split 节点企划书与 Agent 实施指导书》：不想手动填「每段时长」，改成按画面里的镜头切点分段，长度交给 MiniMax H3 自己判断。
  - 新增 `core/smart_split.py`（纯函数层，不 import `core/h3_grid.py`）：`SENSITIVITY_THRESHOLDS`（low 4.5 / medium 3.0 / high 2.0，与 Director `lib/shot_detect.py` 同值三档）、`DETECT_MAX_SIDE = 256` 分析分辨率、`normalize_boundaries()`、`build_smart_segments()`、`assert_lossless()`、`analysis_size()`、`detect_scene_cuts()`（懒导入 scenedetect，`AdaptiveDetector.process_frame/post_process` 逐帧扫描，兼容 0.6 与 0.7 两代 API）。
  - 新增 `comfyui/nodes.py::H3SmartSplit`（`node_id = 'H3 Smart Split'`，category `H3/Video`）：输入顺序 `video, fps, detection_sensitivity, motion_context_frames, segment_id, audio, scale_percent, project_name, save_enabled, save_preview_mp4, save_dtype`；输出与 Manager 完全一致，Picker 与拼接节点无需改动，两个 producer 共用同一个素材库。内部 id 是 0 基，对外 `segment_id` 与落盘目录 `segNN` 一律 1 基。日志打印 `SEGMENT TABLE (SMART, N segments)` 与覆盖率行。
  - 无损约束：主段半开区间必须 `first.start == 0`、`last.end == total`、首尾相接；没有切点时输出 1 段（合法）。不补黑帧、不丢帧、不重复正文帧、不合并短镜头、不限制最大长度、不做 17n+5、不自动推 MC（`motion_context_frames` 默认 `0`）。`detection_sensitivity` 是刻意保留的唯一检测旋钮。
  - 检测跑在节点输入的内存 IMAGE 张量上（`target_fps == fps` 的 1:1 时间轴），不读文件、不做二次解码，`total_frames = video.shape[0]` 就是无损基准。
  - `comfyui/segment_store.py`：`save_segment()` 新增 `thumbnail_frame`（默认 0，clamp 到段范围内），Smart Split 用它把封面停在正文第一帧而不是重叠帧。
  - 新增 `web/h3lvm_smart.js`：中文面板，复用 `web/project_menu.js` 的项目选单（切换 / 新建 / 删除整库）与两行规则说明；固定高度、无折叠按钮。自带 `declareProjectCombo` / `hideProjectWidget` / `allowSavedProject`，不改已实测的 `web/h3lvm_manager.js`。
  - 实测反馈（用户）：「检测分镜功能正常，但它的卡片展示区域不会出现各个裁切好的视频选项卡」。原设计「刻意不做第二套卡片区」被推翻——素材库是共用的，两个产出节点都该看到卡片。
  - 做法是把卡片区抽成一份共用实现而不是复制：新增 `web/deck_panel.js`（`createDeck()`，工具行 + 卡片网格 + 图例 + `h3_lvm/changed` 监听），`web/h3lvm_manager_panel.js` 改为调用它（行为不变，只是不再自带这些代码），`web/h3lvm_smart.js` 挂同一个 `createDeck()`，面板高度与 Manager 一致（`PANEL_H = 320`），并在 `configure()` 里补 `this._h3lvmDeckRefresh?.()`，载入工作流直接出卡片。两个节点共用：片段按 `segment_id` 排序、`本次` 角标、卡片缩放 100%–400%、点卡片写回 `输出片段编号`、空库提示、`abort` 后停止重绘；差异只有文案（`footerLines`）和刷新时是否重读项目列表（`onRefresh`）。
  - 前端用桩 DOM 验证 15 项（`C:\Users\az\Documents\Codex\2026-10-02\xia\work\test_deck_panel.mjs`）：排序、状态行 `库内 N 段 · 本次生成 M 段（片段 …）`、只有带 mp4 的卡片有 ▶、角标只落在本次的卡片、其他项目的 `h3_lvm/changed` 不污染本次、点卡片写回 widget 与 active、空库走 empty 分支、abort 后不再重绘。本轮纯前端，Python 未改，用例数仍为 `Ran 184 tests ... OK`。
  - 依赖：新增 `requirements.txt`（`scenedetect>=0.6.4,<0.8`）。只有 Smart Split 用到；缺包时插件照常加载，Manager / Picker / 拼接输出都不受影响，只有该节点运行时报一条带 `pip install` 命令的错误。
  - 文档：`README.md` 中英文各加节点表行、核心特性、流程图分支、可选依赖说明、`#### H3 Smart Split` 参数表与「刻意没有 `segment_duration` / `align_to_h3_grid` / `final_align` / `person_crop*`」的说明；新增 `SMART_SPLIT_AUDIT.md`（对照 ComfyUI_MiniMaxH3_Director 的真实调用链：检测入口是 `director/http_routes.py` 的 `minimax_detect_shots` 而不是节点；`_merge_close_cuts`、`MIN_SEG_FRAMES = 4`、`_src_frame_to_logical` 均不复用）。
  - 测试：`Ran 184 tests ... OK`（125 → 184）。新增 `tests/test_smart_split_core.py`（43 例：边界归一化、分段构造、无损断言、阈值与分析尺寸）、`tests/test_smart_split_node.py`（7 例端到端，含 MC 重叠、`segment_id` 越界、关闭保存模式；须用 `importlib.import_module(".segment_store", package=NODES.__package__)` 才命中节点实际使用的模块实例）；`tests/test_node_schema.py::TestSmartSplitSchema` 锁定输入顺序与三档灵敏度；`tests/test_segment_store.py::TestThumbnailFrame` 4 例。
  - `.gitignore` 补上测试与探针留下的本地临时目录（`.tmp_tests/`、`.tmp_run*/`、`.probe*/`、`probe_mk*/`、`mk_*/`）：这些目录在沙箱里 `Permission denied` 删不掉，但不应进入版本库。

## 2026-10-03 · `89dd70b`（上一基线）

- 快照：`archive/2026-10-03-89dd70b/`（47 个文件 / 388 KB，与 `git ls-files` 数量一致，排除 `.git`、`__pycache__`、`archive/`）。
- 该基线包含第八轮之前的全部改动（Manager 素材库面板、参数中文化、int8/fp16 存盘精度、定长分段与末段零丢失），已 commit 为 `89dd70b`，测试 `Ran 125 tests ... OK`。
- 本轮改动（第九轮：竖屏画面在卡片里完整显示）：
  - 现象：16:9 等横屏画面在卡片里正常，9:16 竖屏被 `object-fit: cover` 裁成中间一条窄带，只能看到约三分之一的画面。
  - 新增 `web/thumb_fit.js`：两个面板共用的缩略图构建器。按索引里的 `width`/`height` 判断方向（`portraitFromMeta()`），竖屏给 `.h3lvm-thumb-wrap` 和图片加 `is-portrait`，并在图片前插入一层同帧模糊副本 `.h3lvm-thumb-bg`；索引里没有宽高时退回读 `naturalWidth/naturalHeight`。
  - `web/h3lvm_picker.css`：`.h3lvm-thumb.is-portrait { object-fit: contain; }`，模糊背景层用 `filter: blur(10px) brightness(0.4) saturate(1.2)` + `transform: scale(1.25)` 填满左右两侧，不是黑边。缩略图盒子仍是 `width:100% / height:var(--thumb-h)`，卡片尺寸完全不变。
  - 实测反馈「完全糊掉了」→ 层叠顺序错误：绝对定位的 `.h3lvm-thumb-bg` 属于 positioned 层，会画在非定位的普通流 `<img>` 之上，DOM 顺序不起作用，于是整张卡片看到的都是那张放大模糊的副本。修法是把三层显式分层：`.h3lvm-thumb` 加 `position: relative; z-index: 1`（清晰帧），`.h3lvm-thumb-bg` 用 `z-index: 0`，`.h3lvm-active-badge` / `.h3lvm-play-btn` / `.h3lvm-badge` 提到 `z-index: 2`（否则会被清晰帧盖住）。
  - `web/h3lvm_picker.js`、`web/h3lvm_manager_panel.js`：两处重复的缩略图代码改为调用 `appendThumbnail(thumbWrap, seg)`。
  - 纯前端，无新增节点输入、无新增工作流字段，Python 侧未改，用例数仍为 125。前端逻辑用临时桩 DOM 验证过 5 个分支（元数据判定、竖屏加 contain + 模糊层、横屏不变、缺元数据时按图片实际尺寸回退、无缩略图保留占位）；`node --check` 三个文件通过。
  - 本轮改动（第十轮：素材库常开，载入工作流直接出卡片）：
  - 用户反馈：每次离开页面再回来都要「刷新 + 展开素材库」才能看到卡片，而「展开素材库这个功能好没用，一直展开不好吗」。
  - `web/h3lvm_manager_panel.js`：删掉折叠状态与按钮（`PANEL_CLOSED_H`、`PANEL_DELTA`、`collapsed`、`setCollapsed()`、`growNode()`、工具行的 `▾ 展开素材库`），`deck` 不再有 `hidden`；面板高度改为常量 `PANEL_H = 320`（参数 + 项目菜单 + 工具行 + 一行卡片 + 图例），`addPanel(..., PANEL_H)` 的 `getMinHeight` 固定为它。工具行只剩 `🔄 刷新` + `🎬 素材库` 状态。
  - 高度不需要自己管：`addPanel()` 的 `getMinHeight` 固定返回 `PANEL_H`，LiteGraph 的 `_arrangeWidgets()` 每帧把各 widget 的最小高度加起来，一旦超过节点 body 高度就 `setSize([width, l])`（只增不减、宽度不变），`computeSize()` 也会把它算进节点最小尺寸，所以用户拉不到那么小。旧工作流里被折叠过的小节点打开后会自动长到能显示一行卡片，上一版「点展开后节点缩到最小、要手动拉扯」的毛病一起消失。曾写过的 `ensurePanelHeight()` 属于重复实现，已删除。
  - 载入即出卡片：`onNodeCreated` 先于 `configure`，面板初始那次 `render()` 用的是默认库名，读不到用户保存的库。面板改为导出 `node._h3lvmDeckRefresh = render`，`web/h3lvm_manager.js` 的 `nodeType.prototype.configure` 在 `this._h3lvmRefreshProjects?.()` 之后调用它；`onExecuted` 不需要（那里已经由 `h3_lvm/changed` 事件重画）。
  - `README.md` 中英文 Manager 面板段落同步：删掉 `▾ 展开素材库` 与「展开 / 收起只增减一行卡片的高度」，改为常开、载入自动出卡片、高度只增不减；中文段落补上此前缺失的竖屏缩略图说明。
  - 纯前端，无新增节点输入、无新增工作流字段，Python 未改，用例仍为 125；`node --check` 通过 `h3lvm_manager.js`、`h3lvm_manager_panel.js`、`dom_panel.js`。
  - 本轮改动（第十一轮：Manager 面板补上卡片缩放 100%–400%，并抽成共用控件）：
  - 用户指出少了一项通用功能：Picker 有「卡片大小」，常开的 Manager 面板没有。
  - 新增 `web/card_zoom.js`：`createCardZoom({ container, node })`，档位仍是 `[1, 1.5, 2, 3, 4]`（100%/150%/200%/300%/400%），基准仍是 `BASE_CARD_MIN = 130` / `BASE_THUMB_H = 75`，写进容器的 `--card-min` / `--thumb-h`；`mount(toolbar)` 按「分隔线 + 卡片大小 + − + 百分比 + +」的顺序挂到工具行，两个面板因此长得一样、改一处即可。到两端把 `−` / `+` 置灰（`.h3lvm-refresh-btn:disabled`），不再绕回。
  - `web/h3lvm_picker.js`：删掉内联的 `ZOOM_STEPS` / `applyCardZoom()` / 三个控件构造，改为 `createCardZoom({ container, node }).mount(toolbar)`；`fitToContent()` 保留（渲染卡片后仍调用），共用控件内部用 `node.setDirtyCanvas(true, true)` 做同样的事。
  - `web/h3lvm_manager_panel.js`：工具行变成 `🔄 刷新` → 卡片缩放 → `🎬 素材库` 状态。卡片区在面板内滚动（`.h3lvm-deck` 是 `flex: 1 1 0` + `overflow-y: auto`），放大不会改节点尺寸。
  - `web/h3lvm_picker.css`：新增 `.h3lvm-refresh-btn:disabled`；删掉已失效的 `.h3lvm-deck[hidden]`（面板不再折叠，没有任何代码写 `hidden`）。
  - README 中英文：Manager 面板工具行描述加上 `卡片大小` 100%–400%，新增「卡片大小」小节说明这是两个面板共用的控件；Picker 的「面板布局」段落补上档位。
  - 纯前端，无新增节点输入、无新增工作流字段，Python 未改，用例仍为 125；`node --check` 通过 `card_zoom.js`、`h3lvm_picker.js`、`h3lvm_manager_panel.js`；共用控件用桩 DOM 跑过 10 次步进 + 两端夹紧 + 置灰（`C:\Users\az\Documents\Codex\2026-10-02\xia\work\card_zoom.test.mjs`）。

## 2026-10-03 · `90851a8`（更早基线）

- 快照：`archive/2026-10-03-90851a8/`（41 个文件 / 262 KB，与 `git ls-files` 数量一致，排除 `.git`、`__pycache__`、`archive/`）。
- 本轮改动（H3 Segment Picker 项目选单，与 ClipStream v0.7.4 同一套交互）：
  - `comfyui/segment_store.py`：新增 `list_projects_with_counts()`、`create_project()`、`delete_project(name, confirm)`、`MAX_PROJECT_NAME_LENGTH = 80`。新建会写一份空索引，因为 `list_projects()` 只列出含 `h3lvm_index.json` 的目录；删除是 `shutil.rmtree`，不进回收站。
  - `comfyui/server_api.py`：新增 `POST /h3_lvm/project`、`POST /h3_lvm/project/delete`；`GET /h3_lvm/projects` 的返回形状由 `{"projects": [名称]}` 改为 `{"projects": [{"name", "segments"}]}`（内部接口，唯一消费者是本插件前端，前端此前未使用该路由）；抽出 `_csrf_block()` 供三个写接口共用，并把 `from aiohttp import web` 提到模块级受保护导入——原来 `_csrf_block` 在模块层引用函数内的局部 `web`，一旦真的命中 403 分支会 `NameError`。
  - `web/h3lvm_picker.js`、`web/h3lvm_picker.css`：库名标签换成下拉菜单（`＋ 新建项目…` / `库名 (N 段)` / `🗑 删除当前项目…`），新建和删除都在面板内联完成，确认按钮重复库名；删除后切到 `H3_LVM`，没有则切到下一个剩余库。
  - `tests/test_project_menu.py`：14 个用例（列表计数、新建写空索引、同名幂等、空名/超长名拒绝、删除整库、`confirm` 不匹配、已不存在时不建幽灵目录）。
  - 第二轮（同一基线内）：Picker 面板重排为三行——第一行是带标签的项目菜单（`📦 项目素材库` + 大号下拉 + 当前库片段数），新建/删除行紧跟其后；第二行是工具行（刷新 / 卡片大小 / 当前选中）；卡片区下方只留一行操作图例。删掉旧的 `.h3lvm-header`/`.h3lvm-title`/`.h3lvm-project-tag` 结构，新增 `.h3lvm-project-row`/`.h3lvm-toolbar`/`.h3lvm-count`/`.h3lvm-status`。文案全部中文化（`Seg #N` → `片段 N`、`选中: #N` → `当前选中：片段 N`、`API 错误` → `接口读取失败`），并用前端支持的 `widget.label` 把节点上的 `project_name`/`segment_id` 显示为「项目素材库」「片段编号」（只改显示，工作流字段名不变）。
  - 第三轮（同一基线内，Manager 节点本体）：新增 `web/h3lvm_manager.js`（纯前端，节点代码未改）。12 个参数全部上中文标签与中文悬停说明（`widget.label` / `widget.tooltip`，前端在 widget 注册时读取，只改显示）；`project_name` 由文本框改成下拉菜单，列出磁盘上所有库并带片段数量，菜单内含 `＋ 新建项目…`（`window.prompt` 写名字）和 `🗑 删除当前项目…`（`window.confirm` 重复库名后删整库），复用 Picker 那三个接口和同样的文案；`motion_context_frames`、`final_align` 的选项文字用前端支持的 `widget.options.getOptionLabel` 显示为中文，存进工作流的原始值不变。下拉能打开的关键是改 nodeDef 而不是改 widget：在 `beforeRegisterNodeDef` 里把 V1 spec 改写为 `[[选项], {default}]`，`transformInputSpecV1ToV2` 才会把它当 `COMBO` 建出真正的 `ComboWidget`（只设 `widget.type` 无效）。参数顺序保持服务端 schema 顺序——`configure` 按位置回填 `widgets_values`，重排 `node.widgets` 会让旧工作流串位，所以不重排，也不需要按名字存值的兼容层。
  - 第四轮（同一基线内，Manager 节点的「本次生成」卡片条；本轮改动前的快照 `archive/2026-10-03-ca63ce7/`，43 文件 / 318 KB，与 `git ls-files` 一致）：新增 `web/h3lvm_run_strip.js` + `web/h3lvm_manager.css`，把 MP4 预览弹窗从 Picker 抽成共用模块 `web/preview_overlay.js`（`openPreview(seg, signal)`，Picker 改为引用它，删掉本地副本）。Manager 节点参数下面多一个可折叠面板：折叠时只有一行 30 px 的标题（`🎬 本次生成：运行后显示` / `🎬 本次生成 N 段 · 片段 1–6`，连续编号合并成范围），展开后是一行 148 px 宽的卡片（缩略图、`片段 N`、帧数与时长、▶ 预览），点卡片直接写 `segment_id` 这个 widget 并触发它的 callback，等于「选这次跑的哪一段输出到下游」。卡片 id 来自 `comfyui/nodes.py` 保存循环里新收集的 `saved_ids`，随原来的 `h3_lvm/changed` 事件一起发（`{"project", "segments": [...]}`），因此没有新增节点输入、没有新增工作流字段，页面刷新后卡片条回到空状态。渲染时按当前库重新拉 `GET /h3_lvm/segments` 并只保留仍存在的 id，所以在 Picker 里删掉的卡片会同步消失；当前库和这次运行的库不同时空着并提示切回。卡片复用 Picker 的 `.h3lvm-card` 等类，只在 `h3lvm_manager.css` 里覆盖尺寸。`web/dom_panel.js` 的 `addPanel` 支持把 `minHeight` 传成函数（`getMinHeight` 每次布局都会重新问），折叠/展开时改 `node._widgetSlotsDirty` 后 `computeSize()` + `setSize()` 让节点自己缩回去；Picker 传数字，行为不变。纯前端 + 一行事件字段，用例数仍为 91（`nodes.py` 的改动没有测试覆盖，仓库没有 node-execute 的测试 harness）。
  - 第五轮（同一基线内，定长裁切 + 两个面板统一；改动前的快照 `archive/2026-10-03-ca63ce7/`，43 文件 / 318 KB）：
    - 裁切逻辑（用户实测反馈：1962 帧 @ 24fps、每段 6s，结果出现 6.6s / 7.3s 这种反直觉时长）。根因是保存阶段和实时输出阶段各有一次「再对齐」，把已经定长的片段又各自吸附一次。`core/h3_grid.py` 新增 `fixed_slice_frames(duration_frames, align_to_h3)`（6.0s@24fps → 144 → 向下取到 141）与 `generate_fixed_segments(total_frames, slice_frames, context_frames, tail_mode, align_to_h3)`：每段物理长度恒等于 `slice_frames`，正文步进 `main_frames = slice_frames - context_frames`，MC 即前一段尾部的重叠帧；末段 `overlap` 回退到片尾（一帧不丢，内容与上一段重复）或 `drop` 丢弃结尾；`total < slice` 只出一段；`main_frames < 5` 抛中文错误（增大每段时长或减小 MC）。`core/manifest.py` 改用新函数，`SegmentManifest` 新增 `slice_frames` 字段（默认 0，旧数据仍可读）。`comfyui/nodes.py` 删掉那两处再对齐，SEGMENT TABLE 按 extract 长度打印并显示每段固定帧数/秒；`segment_duration`、`align_to_h3_grid`、`final_align` 补中文 tooltip，`final_align` 选项文案改为「末段与上一段重叠（不丢帧，推荐）」/「末段丢弃不足一段」。旧的 `generate_aligned_segments*` 保留为 legacy，其测试保留。验证：1962 帧 → 17 段，每段 141 帧 = 5.875s，全部 17n+5，覆盖到最后一帧；关网格时每段正好 144 帧。
    - UI 问题 1（点展开后节点缩到最小，要手动拉回来）：`web/h3lvm_manager_panel.js` 的 `growNode()` 改为 `node.setSize([w, h ± 202])`，不再调 `computeSize()`。前端 `_arrangeWidgets()` 只在内容高度超过节点高度时才增高、不会主动缩，所以用户自己拉过的宽高会保留。
    - UI 问题 2/3（风格与项目菜单不统一）：项目菜单抽成共享模块 `web/project_menu.js`（`createProjectMenu({node, widget, signal, onChange})`：`📦 项目素材库` 行 + 片段计数 + 内联新建/删除行，哨兵 `__h3lvm_new__` / `__h3lvm_delete__`），Picker 与 Manager 共用。Manager 新增 `web/h3lvm_manager_panel.js`，复用 Picker 的 `.h3lvm-container` / `.h3lvm-project-row` / `.h3lvm-toolbar` / `.h3lvm-deck` / `.h3lvm-card` / `.h3lvm-footer` 类，样式只有 `web/h3lvm_picker.css` 一份（Manager 侧自注入 `<link id="h3lvm-styles">`）。删除 `web/h3lvm_run_strip.js`、`web/h3lvm_manager.css`。Manager 节点上原生 `project_name` 下拉框改为隐藏（`widget.options.hidden = true`；已在本机 `comfyui_frontend_package` 源码确认 `get hidden(){return this._state.options.hidden}`、`getLayoutWidgets()` 过滤 `!w.hidden`），combo 声明保留以保证旧工作流的值仍是合法选项；隐藏 widget 仍按位置序列化，旧图不错位。
    - `web/project_menu.js` 的 `refresh()` 用 `/h3_lvm/projects` 同一份回复写片段计数，Manager 面板顶部不再停在「读取中…」。
    - 用户实测反馈 1（项目素材库不展示库内切片）：Manager 面板的卡片区原来只渲染 `h3_lvm/changed` 里本次运行的编号，所以打开已有的库是空的。现在 `renderOnce()` 按片段编号排序渲染**整个库**，本次运行的片段加 `本次` 角标（新增 `.h3lvm-badge`），状态行改为 `库内 N 段 · 本次生成 M 段（片段 1–6）`，工具行文案改为 `🎬 素材库` / `▾ 展开素材库`；空库显示一行说明而不是空白。
    - 用户实测反馈 2（新建项目后不出现新库）：POST 本身是成功的（`segment_store.create_project()` 会写空索引，14 个用例覆盖），问题是菜单不重绘——`setProject()` 只写 widget，Manager 的 `onChange` 只重绘卡片，下拉里仍是旧列表，看起来像「没建立」。现在 `setProject()` 结尾 `await refresh()`；`refresh()` 加并发去重（`inFlight` 复用同一个请求），和 Picker 的 `loadSegments` 同时触发也只发一次 `/h3_lvm/projects`。
    - 第六轮（同一基线内，末段自动策略；改动前的快照仍是 `archive/2026-10-03-ca63ce7/`）：
      - 起因是用户问「末段与上一段重叠」到底做什么。两种旧策略都不划算：`overlap` 在 1962 帧这个例子里重复 83 帧（3.5s，成片比源片长），`drop` 直接丢 36 帧（1.5s）。剩下的 36 帧本身不是 17n+5（36−5=31 不整除 17），往下最近的合法值 22 会被 MC 全部吃掉（正文 0 帧），往上 39 又超出可用帧数。真正可算的是「MC + 剩余」= 58 帧 → 向下 56（只丢 2 帧）或向上 73（补 15 帧黑帧）。
      - 末段策略改为自动，去掉 `final_align` 这个旋钮：`generate_fixed_segments()` 删掉 `tail_mode` 参数，末段长度取 `min(context + remaining, align_down_to_h3_grid(context + remaining))` 并贴到片尾；正文不足 5 帧时整段丢弃。数学上最多空出一个网格步长（16 帧），不重复任何帧、不补黑帧。`align_down_to_h3_grid()` 对 1–4 帧会向上兜到 5，所以 `min()` 是必须的——否则 MC=0 时末段会倒滑回去重复内容。
      - 实测：1962 帧 @ 24fps、6s、MC=22 → 17 段，前 16 段 141 帧，末段 56 帧（22 MC + 34 正文），代价 2 帧（0.08s）；40s（960 帧）→ 8 段，末段 124 帧，丢 3 帧；265 帧（剩 5 帧）→ 末段整段丢弃，只出 2 段。
      - `comfyui/nodes.py`：`final_align` 保留声明但值被忽略（`del final_align`），前端 `web/h3lvm_manager.js` 用 `RETIRED_FIELDS` 把它隐藏——直接删 widget 会让后面的 `person_crop` 等按位置错位，旧工作流会串位。SEGMENT TABLE 末尾新增一行 `used/source_total source frames used, N unused, tail Xf`。两处「Pad black frames (final_align=up)」的过时注释改为说明真实用途（fps 换算取整兜底）。
      - 测试：`Ran 114 tests ... OK`（110 → 114）。`tests/test_fixed_segments.py` 重写末段用例（`test_tail_shortens_instead_of_repeating`、`test_user_case_tail_is_56_frames`、`test_tail_loses_at_most_one_grid_step`、`test_tail_is_dropped_when_it_would_be_too_short`、`test_tiny_remainder_never_slides_back`、`test_align_off_tail_keeps_every_frame`），共享不变量 `_assert_plan_is_legal()` 断言正文永不重叠且缺口 ≤ 17；`tests/test_core.py::TestManifestSeamless` 五处断言改为「完整段等长 + 末段可短但必须合法」。

  - 第七轮（同一基线内，素材存盘精度开关；改动前的快照仍是 `archive/2026-10-03-ca63ce7/`）：
    - 起因是用户问「一个 40s 视频裁切出来吃掉 20 GB」。实测确认存的是原始张量而不是视频：`E:\ai\ComfyUI-aki-v3\ComfyUI\output\h3-lvm\2\seg01\seg01.safetensors` = 1195 MB，shape `[226, 1280, 720, 3]` float16（226×1280×720×3×2 = 1.25 GB），同段 MP4 只有 4.8 MB。40s@24fps 切 8 段时输出帧数 ≈ 960 + 7×22（MC 重复存）= 1114 帧，1080p 就是 13.2 GB。
    - 关键事实：解码入口 `core/extraction.py` 是 `torch.from_numpy(frames).float() / 255.0`，帧值本来就是 uint8/255，每通道只有 256 个离散值，fp16 多出来的一倍字节没有任何信息量。fp8（e4m3）同样 1 字节但尾数只有 3 bit，[0.5,1] 区间只剩 16 个台阶，比 8-bit 定点更差，因此不做 fp8。
    - `comfyui/segment_store.py`：新增 `INT8_OFFSET = 128`、`VIDEO_DTYPES`、`normalize_save_dtype()`、`_encode_video()`、`_decode_video()`。int8 存 `round(x*255) - 128`，正好把 256 个等级映射到有符号范围；读取按文件里的 dtype 分支还原成 float [0,1]，所以旧 fp16 文件原样可读，同一个库里可以混用。`save_segment()` 新增 `save_dtype="int8"` 参数（放在 `meta` 之后，位置调用不受影响），`seg_meta` 增加 `video_dtype` 字段，保存日志打印 `video=int8|fp16`。
    - `comfyui/nodes.py`：新增 `save_dtype` combo（`int8` / `fp16`，默认 int8），**追加在参数列表末尾**——`configure` 按位置回填 widget，插在中间会让旧工作流串位。`web/h3lvm_manager.js` 上中文标签「素材存盘精度」和选项文字 `int8（体积减半，推荐）` / `fp16（旧格式，体积翻倍）`。
    - 实测体积：1280×720 每帧 5.53 MB（fp16）→ 2.76 MB（int8）；用户那段 1195 MB → 约 595 MB；40s 那次 6.2 GB → 3.1 GB（720p）/ 13.2 GB → 6.6 GB（1080p）。
    - 测试：`Ran 123 tests ... OK`（114 → 123）。`tests/test_segment_store.py::TestSaveDtype` 7 个用例（别名归一化、默认 int8、8-bit 网格上往返 `torch.equal` 精确、文件体积 < 0.6×、fp16 选项仍存 float16、同库混用两种精度、超范围输入 clamp 后仍在 [0,1]）；`tests/test_node_schema.py` 新增两个参数顺序锁定用例（Manager 15 个输入按声明顺序、`save_dtype` 必须在末尾；Picker 两个），防止以后插入字段把旧工作流打乱。

  - 第八轮（同一基线内，末段不做 17n+5 对齐）：
    - 用户决定：前面所有整段照旧对齐 17n+5，最后一段「该多少是多少」（含 Motion Context 重叠帧），无论帧数是否落在网格上都原样交给 MiniMax H3 判断。第六轮的「末段向下吸附，最多空出 16 帧」策略取消。
    - `core/h3_grid.py::generate_fixed_segments()`：末段分支删掉 `align_down_to_h3_grid()`、`min()` 和「正文不足 5 帧就丢弃」的 `break`，只剩 `tail_frames = context_frames + remaining`、`extract_end = total_frames`；短视频（`total_frames < slice_frames`）分支直接返回单段并保留全部帧。模块与函数 docstring 改为零丢失口径。
    - `core/manifest.py`：模块 docstring 与 `build_manifest()` docstring 同步为「末段取剩余全部帧，不做对齐；不重复、不补黑、不丢帧」。
    - `comfyui/nodes.py`：SEGMENT TABLE 每行按 `is_tail = seg.segment_id == total_segments - 1` 输出 `not 17n+5 (tail, left to H3)`；汇总行按 `unused = source_total - used` 计算，`unused == 0` 时不再打印 unused，改打印 `, tail Nf (not aligned, left to H3)`。
    - 实测（全部零丢失）：1962 帧 @ 6s/MC22 → 17 段，前 16 段 141 帧，末段 58 帧（22 MC + 36 正文）；40s（960 帧）→ 8 段，末段 127 帧（105 正文）；1440 帧 → 12 段，末段 131 帧；265 帧 → 3 段，末段 27 帧（正文 5 帧）；100 帧短视频 → 单段 100 帧。
    - 测试：`Ran 125 tests ... OK`（123 → 125）。`tests/test_fixed_segments.py` 重写：去掉 `GRID_STEP`，`_assert_plan_is_legal()` 改为断言正文区间严格首尾相接、`sum(main_frames) == total`、首段 `extract_start == 0`、末段 `extract_end == total`；新增 `test_user_case_tail_is_58_frames`、`test_tail_is_deliberately_off_grid`、`test_nothing_is_lost_or_duplicated`、`test_tail_is_kept_even_when_it_is_tiny`、`test_one_frame_tail_is_kept`、`test_tail_never_slides_back`、`test_short_video_is_one_segment_with_every_frame`。`tests/test_core.py::TestManifestSeamless` 五处旧口径（末段可短但必须合法、缺口 ≤ 17）改为「正文严格首尾相接 + 零丢失」，并锁定 1440 帧案例末段 131 帧。

- 测试：`Ran 125 tests ... OK`（77 → 91 → 110 → 114 → 123 → 125；新增 `tests/test_fixed_segments.py`，`tests/test_core.py::TestManifestSeamless` 改为断言每段等长 + 末段零丢失）。schema 测试仍需 `COMFYUI_ROOT=E:\ai\ComfyUI-aki-v3\ComfyUI`。
- 运行副本（第五轮后）：`core/h3_grid.py`、`core/manifest.py`、`core/models.py`、`comfyui/nodes.py`、`web/h3lvm_manager.js`、`web/h3lvm_picker.js`、`web/h3lvm_picker.css`、`web/dom_panel.js`、`web/preview_overlay.js` 覆盖，新增 `web/project_menu.js`、`web/h3lvm_manager_panel.js`，并删除运行副本里的 `web/h3lvm_run_strip.js`、`web/h3lvm_manager.css`；逐文件 `Copy-Item` + `Get-FileHash` 核对。整仓同步脚本 `C:\Users\az\Documents\Codex\projects\sync-h3lvm-to-comfyui.ps1` 在本沙箱会卡在 robocopy，不用。
- 运行副本（第六轮 + 第七轮 + 第八轮后）：`core/h3_grid.py`、`core/manifest.py`、`comfyui/nodes.py`、`comfyui/segment_store.py`、`web/h3lvm_manager.js`、`tests/test_core.py`、`tests/test_fixed_segments.py`、`tests/test_project_menu.py`、`tests/test_segment_store.py`、`tests/test_node_schema.py`、`README.md`、`VERSION.md`、`RAFOLIE_DEVELOPMENT.md` 逐文件 `Copy-Item` + `Get-FileHash` 核对。核对方式：把开发副本的全部文件（排除 `.git`、`archive/`、`__pycache__` 和临时目录）与运行副本逐个比哈希，结果为 0 处不一致、0 个残留旧文件。

## 2026-10-02 · `a9b7a46`（更早基线）

- 快照：`archive/2026-10-02-a9b7a46/`（40 个文件 / 261 KB，排除 `.git`、`__pycache__`、`archive/`）。
- 该基线包含：ComfyUI V3 迁移 + 片段删除 + 缓存修复（`0944899`，RAFOLIE 全量合并）、`video_fps` NameError 修复（`94692ad`）、主仓库口径署名与安装地址（`a9323b6`）、Picker 第 4 输出 `segment_id` 与 `tests/test_node_schema.py`（`a9b7a46`，采纳 PR #1）。
- 测试：`Ran 77 tests ... OK`。schema 测试需要 `COMFYUI_ROOT=E:\ai\ComfyUI-aki-v3\ComfyUI`，在 `custom_nodes` 下运行时自动识别。
- 运行副本：`E:\ai\ComfyUI-aki-v3\ComfyUI\custom_nodes\H3-Long-Video-Manager` 文件内容与该基线一致。
- 归档目录不进版本控制也不进运行副本：`archive/` 已写入 `.gitignore`，同步脚本也已排除。需要把归档纳入 git 时请明确说明。

## 变更记录

- 2026-10-03（tag）：建首个 tag `v1.0.0` → `305a5d7`，并补上本文件的「Tag 线」小节。
- 2026-10-03（卡片缩放）：Manager 面板补上「卡片大小」100%–400%，并抽成两个面板共用的 `web/card_zoom.js`；到 100% / 400% 两端按钮置灰而不是绕回。
- 2026-10-03（素材库常开）：去掉「▾ 展开素材库」折叠按钮，卡片区一直展开；重新打开工作流时面板在 `configure()` 恢复库名之后自己重画，卡片直接出现，不用点刷新；节点高度交给 ComfyUI（面板 `getMinHeight` 固定 `PANEL_H`，引擎的 `_arrangeWidgets()` 会自动长到能显示一行卡片），插件不再自己 `setSize`。
- 2026-10-03（竖屏卡片）：9:16 等竖屏画面的缩略图不再被裁成中间一条窄带——竖屏改为整帧显示（`object-fit: contain`），左右两侧垫一层同帧模糊副本而不是黑边；横屏照旧铺满。缩略图盒子和卡片尺寸在两种情况下完全一致，缩放档位也不受影响。两个面板的缩略图代码抽成共用模块 `web/thumb_fit.js`。
- 2026-10-03（末段策略，最终版）：末段不再做任何 17n+5 对齐——最后一段直接取剩余全部帧（含 Motion Context 重叠帧），不重复、不补黑帧、不丢帧，帧数是否合法交给 MiniMax H3 判断；整段仍严格对齐 17n+5 且长度一致。1962 帧 @ 6s/MC22 从「末段 56 帧、丢 2 帧」变成「末段 58 帧、零丢失」。
- 2026-10-03（末段策略）：末段不再重复上一段、也不再整段丢弃——结尾不足一段的剩余帧会让最后一段变短（向下吸附到最近的 17n+5），最多空出 16 帧，不补黑帧；`generate_fixed_segments()` 去掉 `tail_mode`，`final_align` 参数废弃并在界面上隐藏（保留声明以免旧工作流参数错位）。1962 帧的例子从「重复 83 帧 / 丢 36 帧」变成「丢 2 帧」。
- 2026-10-03（实测反馈修正）：Manager 面板的卡片区改为读取整个素材库并按片段编号排序，本次运行的片段带 `本次` 角标，状态行显示 `库内 N 段 · 本次生成 M 段`；工具行改为 `🎬 素材库` / `▾ 展开素材库`。新建/删除项目后菜单自己重绘（`setProject()` 结尾 `await refresh()`，`refresh()` 并发去重），修掉「点了建立但库里没出现新文件夹」。
- 2026-10-03：裁切改为定长：每段物理长度 = 每段时长向下吸附到 17n+5（6.0s@24fps → 141 帧 = 5.875s），MC 作为与上一段尾部的重叠，末段可选「回退到片尾不丢帧」或「丢弃不足一段」；删掉保存/实时输出两处二次对齐（6.6s / 7.3s 漂移的根因）。新增 `fixed_slice_frames()`、`generate_fixed_segments()`、`tests/test_fixed_segments.py`；`SegmentManifest` 增加 `slice_frames`。
- 2026-10-03：Manager 节点的「本次生成」卡片条升级为与 Segment Picker 同一套视觉的面板（顶部项目素材库菜单 + 工具行 + 读取整个素材库的卡片网格 + 图例，本次运行的片段带 `本次` 角标）；项目菜单抽成共享模块 `web/project_menu.js`，两个节点共用；删除 `web/h3lvm_run_strip.js`、`web/h3lvm_manager.css`；Manager 上原生 `project_name` 下拉框隐藏（面板里已有同一个菜单）。展开/收起改为按固定增量 `setSize`，节点不再缩到最小。
- 2026-10-03：Manager 节点（H3 Long Video Manager）参数下面新增可折叠的「🎬 本次生成」卡片条：只显示该节点上一次运行保存的片段，点卡片即切换「输出片段编号」，▶ 播放 MP4 预览。新增 `web/h3lvm_run_strip.js`、`web/h3lvm_manager.css`，MP4 预览弹窗抽成 `web/preview_overlay.js` 共用；`comfyui/nodes.py` 在 `h3_lvm/changed` 事件里附带本次保存的片段编号；`web/dom_panel.js` 的 `addPanel` 允许 `minHeight` 为函数。无新增节点输入与工作流字段。
- 2026-10-03：H3 Long Video Manager 节点本体中文化（标签 + 悬停说明 + 下拉选项文字）、`project_name` 换成项目下拉菜单（可新建/删除，在 nodeDef 里声明为 combo）；新增 `web/h3lvm_manager.js`。参数顺序保持服务端顺序（重排会让旧工作流按位置串位，已撤销）。README 参数表补 `fps`、`final_align`，新增「节点上显示为」列（原表 `video_fps` 是过时字段名）。
- 2026-10-03：Picker 面板重排（项目菜单置顶成独立一行 + 片段计数 + 工具行 + 底部图例），界面文案与节点参数显示名全部中文化。
- 2026-10-03：H3 Segment Picker 加项目选单（列出+计数、选单内新建、选单内删除整库）；`GET /h3_lvm/projects` 返回形状改为带计数；新增 `tests/test_project_menu.py`；README 双语接口表补齐 `POST /h3_lvm/project`、`POST /h3_lvm/project/delete`、`POST /h3_lvm/delete`。

- 2026-10-02：建立 `archive/` + `VERSION.md` 版本基线（本文件）。
- 2026-10-02：`AFOLIE_DEVELOPMENT.md` 改名为 `RAFOLIE_DEVELOPMENT.md`（补回缺失的 R），同步 README 中的链接。
- 2026-10-02：README「Project structure」与 `git ls-files` 对齐（补 `core/person_crop.py`、`comfyui/asset_paths.py`、`web/delete_button.js`、`web/dom_panel.js`、`tests/test_person_crop.py`、`tests/test_node_schema.py`）。
- 2026-10-02：`PROJECT_SPEC.md` 的 Phase 勾选与架构树更新为实际实现状态（原 Phase 0 计划保留为历史记录）。
- 2026-10-02：同步脚本 `C:\Users\az\Documents\Codex\projects\sync-h3lvm-to-comfyui.ps1` 排除 `archive/`，归档快照不再进入 ComfyUI 运行副本。
