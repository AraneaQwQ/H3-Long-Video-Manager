# 贡献来源与修改记录

本仓库 [AraneaQwQ/H3-Long-Video-Manager](https://github.com/AraneaQwQ/H3-Long-Video-Manager) 是项目主仓库。ComfyUI V3 迁移、片段删除与缓存修复等改动由 [RAFOLIE](https://github.com/RAFOLIE) 在其分叉上开发，已于提交 `0944899`（full RAFOLIE merge）完整合并进本仓库。

- 项目维护者：AraneaQwQ；完整贡献历史保留在 Git 中。
- RAFOLIE 开发分支的基线：`5863ddd83a63091de7b1387730d4df2e481a06c7`。
- 保留原项目 [MIT LICENSE](LICENSE) 及版权声明；RAFOLIE 的改动同样以 MIT 许可发布。

## 修改记录

- 2026-09-28：修复删除片段后以相同参数重新运行却不恢复素材的问题。Manager 在 save_enabled 开启时绕过自身结果缓存，关闭保存时保留正常缓存；保存全部完成后通知 Picker 刷新，保存失败改为明确报错。隔离实例已验证“保存两段 → 全删 → 原参数排队 → 两段恢复”，上游输入仍命中缓存。

- 2026-09-28：Segment Picker 增加片段卡片删除按钮、确认提示及删除后刷新；修复删除后编号空洞校验，统一素材读写锁和原子索引写入，改用带文件版本的预览 URL。行为及缓存检查见 [CACHE_AND_DELETION.md](CACHE_AND_DELETION.md)。

- 2026-09-28：补充本说明及 README 来源入口。初始准备阶段仅添加来源说明，随后实施的迁移见下列记录。

后续在此记录功能修改、兼容性变化和验证结果，发布前更新到实际状态。

- 2026-09-28：将 2 个活动节点迁移到 ComfyUI V3（ComfyNode、define_schema、类方法 execute、NodeOutput、ComfyExtension）；保留节点 ID、输入名及输出顺序。
- 2026-09-28：适配 Nodes 2.0 的 DOM 控件尺寸与生命周期，移除卡片刷新时的自动缩小；改用包内导入。迁移测试见 [V3_MIGRATION.md](V3_MIGRATION.md)。

- 2026-09-28：增大新建节点默认尺寸（H3 Segment Picker：620 × 460），仅在创建时应用；加载工作流保留已保存尺寸，用户仍可手动缩放。

- 2026-09-28：整理 V3 与 Nodes 2.0 开发版，安装地址改为 RAFOLIE/H3-Long-Video-Manager；保留原作者来源、许可证及 Git 历史。
- 2026-10-02：README 与来源说明改为主仓库口径，安装地址指回 AraneaQwQ/H3-Long-Video-Manager；RAFOLIE 的署名、贡献记录与 Git 历史保留。
- 2026-10-02：采纳 PR #1 的 `segment_id` 输出（贡献者 flyingsnow1），仅取 `comfyui/nodes.py` 改动，README 保持主仓库版本，说明另存 [SEGMENT_ID_OUTPUT.md](SEGMENT_ID_OUTPUT.md)；新增 `tests/test_node_schema.py` 锁定两个节点的输出顺序。

- 2026-10-02：本文件由 `AFOLIE_DEVELOPMENT.md` 改名为 `RAFOLIE_DEVELOPMENT.md`（补回缺失的 R），README 中的链接同步更新；改名前仓库内只有 README 一处引用。
- 2026-10-02：按版本铁规建立 `archive/` + `VERSION.md`：`archive/2026-10-02-a9b7a46/` 是本次改动前的完整快照（40 文件 / 261 KB），`VERSION.md` 记录基线内容、测试命令与结论。
- 2026-10-02：文档与代码对齐——README 的「Project structure」按 `git ls-files` 重建（补 `core/person_crop.py`、`comfyui/asset_paths.py`、`web/delete_button.js`、`web/dom_panel.js`、`tests/test_person_crop.py`、`tests/test_node_schema.py`，`core/extraction.py` 已实现不再是 reserved）；两个节点的输出顺序写进 README 节点表；`PROJECT_SPEC.md` 的 Phase 勾选更新为实际实现状态，Phase 0 计划保留为历史。
- 2026-10-02：同步脚本 `C:\Users\az\Documents\Codex\projects\sync-h3lvm-to-comfyui.ps1` 增加 `archive` 排除项，归档快照不再进入 ComfyUI 运行副本。

- 2026-10-03：H3 Segment Picker 的库名输入换成项目选单（与 ComfyUI-H3-ClipStream v0.7.4 同一套交互）：菜单列出磁盘上所有库并带片段数量，第一项 `＋ 新建项目…` 建一个空库，最后一项 `🗑 删除当前项目…` 在面板内联确认（确认按钮重复库名）后删除整个库，删除是 `shutil.rmtree`，不进回收站，删完切到 `H3_LVM` 或下一个剩余库。后端新增 `list_projects_with_counts()` / `create_project()` / `delete_project(name, confirm)` 与 `POST /h3_lvm/project`、`POST /h3_lvm/project/delete`；`GET /h3_lvm/projects` 的返回形状由名称数组改为 `[{"name", "segments"}]`（内部接口，前端此前未调用过它）。顺带修掉 `_csrf_block` 在模块层引用函数内局部 `web` 的隐患——真命中 403 分支会 `NameError`，现改为模块级受保护导入。新增 `tests/test_project_menu.py`（14 用例），全套 `Ran 91 tests ... OK`。
- 2026-10-03：Picker 面板重排为三行，让「读哪个库」这一步最先看到——第一行是带标签的项目菜单（`📦 项目素材库` + 加大的下拉 + 当前库片段数），新建/删除的内联行紧跟在菜单下面；第二行是工具行（刷新 / 卡片大小 / 当前选中）；卡片区下面只留一行操作图例。旧的 `.h3lvm-header` / `.h3lvm-title` / `.h3lvm-project-tag` / `.h3lvm-selected` 结构删除，新增 `.h3lvm-project-row` / `.h3lvm-toolbar` / `.h3lvm-count` / `.h3lvm-status`。
- 2026-10-03：界面文案全面中文化（`Seg #N` → `片段 N`、`选中: #N` → `当前选中：片段 N`、`API 错误` → `接口读取失败`、空库提示点名当前库名），并通过前端支持的 `widget.label` 把节点上的 `project_name` / `segment_id` 显示为「项目素材库」「片段编号」。`label` 只影响显示，节点字段名与工作流文件不变；纯前端改动，用例数仍为 91。
- 2026-10-03：Manager 节点本体（H3 Long Video Manager）同样中文化并接入项目菜单，新增前端文件 `web/h3lvm_manager.js`。12 个参数全部改为中文 `widget.label` + 中文 tooltip；`motion_context_frames`（none / previous segment head）与 `final_align`（off / h3_grid）用 `getOptionLabel` 显示中文选项，节点字段与保存值不变。`project_name` 在节点上改为下拉（关键在改 nodeDef，见下一条），选项为 `＋ 新建项目…` → 磁盘上的库（显示为 `名称 (N 段)`）→ `🗑 删除当前项目…`，两个哨兵值 `__h3lvm_new__` / `__h3lvm_delete__` 不会写进工作流（先还原再走 prompt/confirm），文案与 Picker 一致，刷新走 `h3lvm/changed` 事件。
- 2026-10-03：修好项目下拉打不开的问题。根因：`widget.type = "combo"` 只改字段，不改实例类——widget 由 `widgetMap.ts: toConcreteWidget` 按 nodeDef 的 V1 spec 创建（`STRING` → `TextWidget`，`combo` → `ComboWidget`），canvas 走实例的 `draw`，所以文本框永远画成文本框。正确做法是在 `beforeRegisterNodeDef`（`litegraphService.ts` 在 `new ComfyNodeDefImpl(nodeDefV1)` 之前 await 调用，可 async）里把 `nodeData.input.optional.project_name` 改写为 `[[选项数组], {default}]`；`migration.ts: transformInputSpecV1ToV2` 见 `spec[0]` 是数组就判为 `COMBO` 并把数组当 options，于是创建出来就是真正的 `ComboWidget`。注册前先 `GET /h3_lvm/projects`（3 秒超时）取库列表；`configure` 之前把旧工作流里存的库名插进选项数组，保证按位置回填的值合法。canvas 的 `ComboWidget._displayValue` 与 `onClick` 都会调用 `options.getOptionLabel`，所以 `名称 (N 段)` 后缀和中文选项文字仍然生效；刷新时原地 `splice` `widget.options.values`（options 与 store state 共享同一对象，整体替换会失效）。
- 2026-10-03：撤掉 Manager 的参数重排。`LGraphNode.configure` 用 `getRestoredWidgetValue(graphId, nodeId, name, positionalIndex)` 按**位置**回填（`LiteGraph.namedValuesRestore` 默认 false；`input_order` 只影响创建顺序，打包产物里 `nodeDefOrderingUtil.sortWidgetValuesByInputOrder` 没有调用者），重排 `node.widgets` 会让旧工作流参数串位（实测 `Motion Context 帧数=7.3`、`输出片段编号=22`）。参数顺序因此保持服务端 schema 顺序，`h3lvm_widget_values` 副本与旧顺序重映射这两层兼容代码一并删除。节点输出槽名（IMAGE / AUDIO / frame_count / total_segments）未改，已有连线不受影响。节点 Python 代码未改，纯前端，用例数仍为 91。

