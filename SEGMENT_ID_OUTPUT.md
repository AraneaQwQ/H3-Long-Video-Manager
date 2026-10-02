# segment_id 输出（原片 vs 二采对比）

贡献者：flyingsnow1（[PR #1](https://github.com/AraneaQwQ/H3-Long-Video-Manager/pull/1)，2026-09-30）。

H3 Segment Picker 会把节点自身的 `segment_id` 作为第 4 个输出（Int）回传，供下游判断当前取用的是否为首段，从而把原视频与二次生成（二采）视频按帧对齐比较。

## 用法

- `segment_id == 1`：首段，原片与二采结果可直接对比。
- `segment_id > 1`：非首段的二采片段头部带有 Motion Context 多出的帧。用 `comfyui-various` 的 Extract Image Sequence From Batch 裁掉与 H3 Long Video Manager 中 `motion_context_frames` 相同的帧数，再合并，即可跳过这些多出的帧。

## 兼容性

- 输出追加在末尾，顺序为 `IMAGE`、`AUDIO`、`frame_count`、`segment_id`；已有工作流的三根连线按索引仍然有效。
- 两个节点的输出顺序由 `tests/test_node_schema.py` 锁定。

接线参考（图片来自 PR #1）：

![segment_id 接线参考](https://github.com/user-attachments/assets/133fe290-3eac-409f-b48c-148982af5438)
