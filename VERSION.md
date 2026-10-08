# 版本说明（VERSION.md）

> 版本铁规：每次改动前，把旧版本完整快照存入 `archive/<日期>-<commit 短 hash>/`，并在本文件顶部追加一条说明。
> 只有用户的明确命令才能删改 `archive/` 中的旧版本。

## Tag 线

- `v1.0.0` → `305a5d7`（首个 tag）：定长切段（每段含 MC 重叠帧固定 ≤ 用户输入时长且对齐 17n+5）+ 末段零丢失不对齐、素材存盘 int8/fp16 开关、项目素材库选单（切换/新建/删除整库）、两个节点的中文可视面板与常开卡片区、竖屏卡片完整显示、卡片缩放 100%–400% 共用控件。已推送 `origin`（`git-push-github.ps1 -Tags` 只推 tag，分支要再跑一次不带 `-Tags`）。
- `v1.1.0` → `0a1cdd4`（tag 对象 `5d7b5a3`）：新增 `H3 Smart Split` 节点（按镜头切点分段，长度交给 MiniMax H3 判断，无损覆盖全部帧）+ 两个产出节点共用的一套卡片区 `web/deck_panel.js`（常开、载入即出卡片、`本次` 角标、卡片缩放 100%–400%、点卡片写回输出片段编号）+ 卡片区合并模式（相邻多选、`✅ 确认合并`、新卡片沿用最小 id 且后续编号顺延、接缝去掉 MC 重叠帧并同步裁音频、packed int8/fp16 直拼、`POST /h3_lvm/merge`）。已推送 `origin/main`（远端 main = `0a1cdd4`）与 `v1.1.0`。

## 2026-10-09 · `0a1cdd4`（当前基线）

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
