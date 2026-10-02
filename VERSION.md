# 版本说明（VERSION.md）

> 版本铁规：每次改动前，把旧版本完整快照存入 `archive/<日期>-<commit 短 hash>/`，并在本文件顶部追加一条说明。
> 只有用户的明确命令才能删改 `archive/` 中的旧版本。

## 2026-10-03 · `90851a8`（当前基线）

- 快照：`archive/2026-10-03-90851a8/`（41 个文件 / 262 KB，与 `git ls-files` 数量一致，排除 `.git`、`__pycache__`、`archive/`）。
- 本轮改动（H3 Segment Picker 项目选单，与 ClipStream v0.7.4 同一套交互）：
  - `comfyui/segment_store.py`：新增 `list_projects_with_counts()`、`create_project()`、`delete_project(name, confirm)`、`MAX_PROJECT_NAME_LENGTH = 80`。新建会写一份空索引，因为 `list_projects()` 只列出含 `h3lvm_index.json` 的目录；删除是 `shutil.rmtree`，不进回收站。
  - `comfyui/server_api.py`：新增 `POST /h3_lvm/project`、`POST /h3_lvm/project/delete`；`GET /h3_lvm/projects` 的返回形状由 `{"projects": [名称]}` 改为 `{"projects": [{"name", "segments"}]}`（内部接口，唯一消费者是本插件前端，前端此前未使用该路由）；抽出 `_csrf_block()` 供三个写接口共用，并把 `from aiohttp import web` 提到模块级受保护导入——原来 `_csrf_block` 在模块层引用函数内的局部 `web`，一旦真的命中 403 分支会 `NameError`。
  - `web/h3lvm_picker.js`、`web/h3lvm_picker.css`：库名标签换成下拉菜单（`＋ 新建项目…` / `库名 (N 段)` / `🗑 删除当前项目…`），新建和删除都在面板内联完成，确认按钮重复库名；删除后切到 `H3_LVM`，没有则切到下一个剩余库。
  - `tests/test_project_menu.py`：14 个用例（列表计数、新建写空索引、同名幂等、空名/超长名拒绝、删除整库、`confirm` 不匹配、已不存在时不建幽灵目录）。
  - 第二轮（同一基线内）：Picker 面板重排为三行——第一行是带标签的项目菜单（`📦 项目素材库` + 大号下拉 + 当前库片段数），新建/删除行紧跟其后；第二行是工具行（刷新 / 卡片大小 / 当前选中）；卡片区下方只留一行操作图例。删掉旧的 `.h3lvm-header`/`.h3lvm-title`/`.h3lvm-project-tag` 结构，新增 `.h3lvm-project-row`/`.h3lvm-toolbar`/`.h3lvm-count`/`.h3lvm-status`。文案全部中文化（`Seg #N` → `片段 N`、`选中: #N` → `当前选中：片段 N`、`API 错误` → `接口读取失败`），并用前端支持的 `widget.label` 把节点上的 `project_name`/`segment_id` 显示为「项目素材库」「片段编号」（只改显示，工作流字段名不变）。
  - 第三轮（同一基线内，Manager 节点本体）：新增 `web/h3lvm_manager.js`（纯前端，节点代码未改）。12 个参数全部上中文标签与中文悬停说明（`widget.label` / `widget.tooltip`，前端在 widget 注册时读取，只改显示）；`project_name` 由文本框改成下拉菜单，列出磁盘上所有库并带片段数量，菜单内含 `＋ 新建项目…`（`window.prompt` 写名字）和 `🗑 删除当前项目…`（`window.confirm` 重复库名后删整库），复用 Picker 那三个接口和同样的文案；`motion_context_frames`、`final_align` 的选项文字用前端支持的 `widget.options.getOptionLabel` 显示为中文，存进工作流的原始值不变。下拉能打开的关键是改 nodeDef 而不是改 widget：在 `beforeRegisterNodeDef` 里把 V1 spec 改写为 `[[选项], {default}]`，`transformInputSpecV1ToV2` 才会把它当 `COMBO` 建出真正的 `ComboWidget`（只设 `widget.type` 无效）。参数顺序保持服务端 schema 顺序——`configure` 按位置回填 `widgets_values`，重排 `node.widgets` 会让旧工作流串位，所以不重排，也不需要按名字存值的兼容层。
- 测试：`Ran 91 tests ... OK`（77 → 91，第二轮为纯前端改动，用例数不变）。schema 测试仍需 `COMFYUI_ROOT=E:\ai\ComfyUI-aki-v3\ComfyUI`。
- 运行副本：`comfyui/segment_store.py`、`comfyui/server_api.py`、`web/h3lvm_picker.js`、`web/h3lvm_picker.css`、`web/h3lvm_manager.js` 已逐文件覆盖到 `E:\ai\ComfyUI-aki-v3\ComfyUI\custom_nodes\H3-Long-Video-Manager`（哈希一致）。整仓同步脚本 `C:\Users\az\Documents\Codex\projects\sync-h3lvm-to-comfyui.ps1` 在本沙箱会卡在 robocopy，改用逐文件 `Copy-Item`。

## 2026-10-02 · `a9b7a46`（上一基线）

- 快照：`archive/2026-10-02-a9b7a46/`（40 个文件 / 261 KB，排除 `.git`、`__pycache__`、`archive/`）。
- 该基线包含：ComfyUI V3 迁移 + 片段删除 + 缓存修复（`0944899`，RAFOLIE 全量合并）、`video_fps` NameError 修复（`94692ad`）、主仓库口径署名与安装地址（`a9323b6`）、Picker 第 4 输出 `segment_id` 与 `tests/test_node_schema.py`（`a9b7a46`，采纳 PR #1）。
- 测试：`Ran 77 tests ... OK`。schema 测试需要 `COMFYUI_ROOT=E:\ai\ComfyUI-aki-v3\ComfyUI`，在 `custom_nodes` 下运行时自动识别。
- 运行副本：`E:\ai\ComfyUI-aki-v3\ComfyUI\custom_nodes\H3-Long-Video-Manager` 文件内容与该基线一致。
- 归档目录不进版本控制也不进运行副本：`archive/` 已写入 `.gitignore`，同步脚本也已排除。需要把归档纳入 git 时请明确说明。

## 变更记录

- 2026-10-03：H3 Long Video Manager 节点本体中文化（标签 + 悬停说明 + 下拉选项文字）、`project_name` 换成项目下拉菜单（可新建/删除，在 nodeDef 里声明为 combo）；新增 `web/h3lvm_manager.js`。参数顺序保持服务端顺序（重排会让旧工作流按位置串位，已撤销）。README 参数表补 `fps`、`final_align`，新增「节点上显示为」列（原表 `video_fps` 是过时字段名）。
- 2026-10-03：Picker 面板重排（项目菜单置顶成独立一行 + 片段计数 + 工具行 + 底部图例），界面文案与节点参数显示名全部中文化。
- 2026-10-03：H3 Segment Picker 加项目选单（列出+计数、选单内新建、选单内删除整库）；`GET /h3_lvm/projects` 返回形状改为带计数；新增 `tests/test_project_menu.py`；README 双语接口表补齐 `POST /h3_lvm/project`、`POST /h3_lvm/project/delete`、`POST /h3_lvm/delete`。

- 2026-10-02：建立 `archive/` + `VERSION.md` 版本基线（本文件）。
- 2026-10-02：`AFOLIE_DEVELOPMENT.md` 改名为 `RAFOLIE_DEVELOPMENT.md`（补回缺失的 R），同步 README 中的链接。
- 2026-10-02：README「Project structure」与 `git ls-files` 对齐（补 `core/person_crop.py`、`comfyui/asset_paths.py`、`web/delete_button.js`、`web/dom_panel.js`、`tests/test_person_crop.py`、`tests/test_node_schema.py`）。
- 2026-10-02：`PROJECT_SPEC.md` 的 Phase 勾选与架构树更新为实际实现状态（原 Phase 0 计划保留为历史记录）。
- 2026-10-02：同步脚本 `C:\Users\az\Documents\Codex\projects\sync-h3lvm-to-comfyui.ps1` 排除 `archive/`，归档快照不再进入 ComfyUI 运行副本。
