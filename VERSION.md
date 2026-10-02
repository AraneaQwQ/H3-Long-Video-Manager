# 版本说明（VERSION.md）

> 版本铁规：每次改动前，把旧版本完整快照存入 `archive/<日期>-<commit 短 hash>/`，并在本文件顶部追加一条说明。
> 只有用户的明确命令才能删改 `archive/` 中的旧版本。

## 2026-10-02 · `a9b7a46`（当前基线）

- 快照：`archive/2026-10-02-a9b7a46/`（40 个文件 / 261 KB，排除 `.git`、`__pycache__`、`archive/`）。
- 该基线包含：ComfyUI V3 迁移 + 片段删除 + 缓存修复（`0944899`，RAFOLIE 全量合并）、`video_fps` NameError 修复（`94692ad`）、主仓库口径署名与安装地址（`a9323b6`）、Picker 第 4 输出 `segment_id` 与 `tests/test_node_schema.py`（`a9b7a46`，采纳 PR #1）。
- 测试：`Ran 77 tests ... OK`。schema 测试需要 `COMFYUI_ROOT=E:\ai\ComfyUI-aki-v3\ComfyUI`，在 `custom_nodes` 下运行时自动识别。
- 运行副本：`E:\ai\ComfyUI-aki-v3\ComfyUI\custom_nodes\H3-Long-Video-Manager` 文件内容与该基线一致。
- 归档目录不进版本控制也不进运行副本：`archive/` 已写入 `.gitignore`，同步脚本也已排除。需要把归档纳入 git 时请明确说明。

## 变更记录

- 2026-10-02：建立 `archive/` + `VERSION.md` 版本基线（本文件）。
- 2026-10-02：`AFOLIE_DEVELOPMENT.md` 改名为 `RAFOLIE_DEVELOPMENT.md`（补回缺失的 R），同步 README 中的链接。
- 2026-10-02：README「Project structure」与 `git ls-files` 对齐（补 `core/person_crop.py`、`comfyui/asset_paths.py`、`web/delete_button.js`、`web/dom_panel.js`、`tests/test_person_crop.py`、`tests/test_node_schema.py`）。
- 2026-10-02：`PROJECT_SPEC.md` 的 Phase 勾选与架构树更新为实际实现状态（原 Phase 0 计划保留为历史记录）。
- 2026-10-02：同步脚本 `C:\Users\az\Documents\Codex\projects\sync-h3lvm-to-comfyui.ps1` 排除 `archive/`，归档快照不再进入 ComfyUI 运行副本。
