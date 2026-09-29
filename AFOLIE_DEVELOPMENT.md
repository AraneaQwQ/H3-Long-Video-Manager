# 来源与后续开发说明

本开发副本基于 [AraneaQwQ/H3-Long-Video-Manager](https://github.com/AraneaQwQ/H3-Long-Video-Manager)，后续由 [RAFOLIE](https://github.com/RAFOLIE) 维护自己的修改。

- 原项目维护者：AraneaQwQ；完整贡献历史保留在 Git 中。
- 初始基线：`5863ddd83a63091de7b1387730d4df2e481a06c7`。
- 保留原项目 [MIT LICENSE](LICENSE) 及版权声明。
- 本副本的修改不代表原作者发布或背书；原作者应获得原始工作的署名。

## 修改记录

- 2026-09-28：修复删除片段后以相同参数重新运行却不恢复素材的问题。Manager 在 save_enabled 开启时绕过自身结果缓存，关闭保存时保留正常缓存；保存全部完成后通知 Picker 刷新，保存失败改为明确报错。隔离实例已验证“保存两段 → 全删 → 原参数排队 → 两段恢复”，上游输入仍命中缓存。

- 2026-09-28：Segment Picker 增加片段卡片删除按钮、确认提示及删除后刷新；修复删除后编号空洞校验，统一素材读写锁和原子索引写入，改用带文件版本的预览 URL。行为及缓存检查见 [CACHE_AND_DELETION.md](CACHE_AND_DELETION.md)。

- 2026-09-28：补充本说明及 README 来源入口。初始准备阶段仅添加来源说明，随后实施的迁移见下列记录。

后续在此记录功能修改、兼容性变化和验证结果，发布前更新到实际状态。

- 2026-09-28：将 2 个活动节点迁移到 ComfyUI V3（ComfyNode、define_schema、类方法 execute、NodeOutput、ComfyExtension）；保留节点 ID、输入名及输出顺序。
- 2026-09-28：适配 Nodes 2.0 的 DOM 控件尺寸与生命周期，移除卡片刷新时的自动缩小；改用包内导入。迁移测试见 [V3_MIGRATION.md](V3_MIGRATION.md)。

- 2026-09-28：增大新建节点默认尺寸（H3 Segment Picker：620 × 460），仅在创建时应用；加载工作流保留已保存尺寸，用户仍可手动缩放。

- 2026-09-28：整理 V3 与 Nodes 2.0 开发版，安装地址改为 RAFOLIE/H3-Long-Video-Manager；保留原作者来源、许可证及 Git 历史。
