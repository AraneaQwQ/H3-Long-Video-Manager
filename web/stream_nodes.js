import { app } from "../../scripts/app.js";
import { installManagerPanel } from "./h3lvm_manager_panel.js";
import { installSmartPanel } from "./h3lvm_smart.js";
import { createSourceControls } from "./source_preview.js";
import { createParameterPanel, hideParameterWidgets } from "./parameter_panel.js";
import { MANAGER_V2_SETTINGS_SECTIONS, SMART_V2_SETTINGS_SECTIONS } from "./v2_settings.js";

const MANAGER_V2 = "H3 Long Video Manager v2";
const SMART_V2 = "H3 Smart Split v2";

const LABELS = {
    video: "视频文件（路径）",
    custom_path: "本地完整路径（可选，优先）",
    segment_duration: "每段时长（秒）",
    detection_sensitivity: "镜头切点灵敏度",
    motion_context_frames: "Motion Context 帧数",
    segment_id: "输出片段编号",
    scale_percent: "画面缩放 %",
    align_to_h3_grid: "对齐 H3 帧数（17n+5）",
    project_name: "📦 项目素材库",
    save_enabled: "保存到素材库",
    save_preview_mp4: "生成 MP4 预览",
    save_dtype: "素材存盘精度",
    playback_speed: "参考视频慢放倍率",
    playback_speed_custom: "自定义慢放倍率",
};

const TOOLTIPS = {
    segment_duration: "每段时长已包含 Motion Context；慢放后会按照慢放后的时间轴计算。",
    detection_sensitivity: "只影响镜头切点检测；慢放在检测之前执行。",
    motion_context_frames: "在当前慢放后的时间轴上，为接续段额外保留的前置重叠帧。",
    segment_id: "选择直接输出到下游的片段；其余片段仍可保存到项目素材库。",
    scale_percent: "流式解码时逐帧缩放，不会先生成完整原尺寸视频。",
    align_to_h3_grid: "开启后按 H3 支持的 17n+5 帧数裁切。",
    save_enabled: "是否把裁切片段写入项目素材库；独立运行时请保持开启。",
    save_preview_mp4: "保存片段时额外生成浏览器可播放的 MP4。",
    save_dtype: "int8 节省存盘空间；fp16 保留旧版浮点存盘格式。",
    playback_speed: "先通过重复邻近帧慢放，再检测镜头或裁切；输出仍为 24fps，音频使用 atempo 同步慢放并保持音调。",
    playback_speed_custom: "只有主选项为 custom 时生效，范围 0.1–1.0，步进 0.1。",
};

const OPTION_LABELS = {
    detection_sensitivity: {
        low: "低（只切明显硬切）",
        medium: "中（默认）",
        high: "高（更容易切出更多镜头）",
    },
    motion_context_frames: {
        "0": "0 帧（不重叠）",
        "5": "5 帧",
        "22": "22 帧",
        "39": "39 帧",
        "56": "56 帧",
    },
    save_dtype: {
        int8: "int8（体积减半，推荐）",
        fp16: "fp16（旧格式，体积翻倍）",
    },
    playback_speed: {
        "1.0x": "1.0x（原速，默认）",
        "0.75x": "0.75x（慢放到 75%）",
        "0.5x": "0.5x（慢放到 50%）",
        custom: "custom（自定义 0.1~1.0x）",
    },
};

function prepareWidgets(node) {
    for (const widget of node.widgets ?? []) {
        if (LABELS[widget.name]) widget.label = LABELS[widget.name];
        if (TOOLTIPS[widget.name]) widget.tooltip = TOOLTIPS[widget.name];
        const options = OPTION_LABELS[widget.name];
        if (options && widget.options) {
            widget.options.getOptionLabel = value => options[String(value)] ?? String(value ?? "");
        }
        if (widget.name === "project_name" && widget.options) widget.options.hidden = true;
    }
}

app.registerExtension({
    name: "H3.LVM.StreamNodesV2",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const isManager = nodeData.name === MANAGER_V2;
        const isSmart = nodeData.name === SMART_V2;
        if (!isManager && !isSmart) return;

        const originalCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalCreated?.apply(this, arguments);
            prepareWidgets(this);
            const sections = isManager ? MANAGER_V2_SETTINGS_SECTIONS : SMART_V2_SETTINGS_SECTIONS;
            const lifetimeKey = isManager ? "_h3lvmManagerLifetime" : "_h3lvmSmartLifetime";
            const lifetime = this[lifetimeKey] ?? new AbortController();
            this[lifetimeKey] = lifetime;
            hideParameterWidgets(this, sections, ["segment_id"]);
            const source = createSourceControls(this);
            this._h3v2Source = source;
            const settings = createParameterPanel(this, {
                sections,
                labels: LABELS,
                tooltips: TOOLTIPS,
                optionLabels: OPTION_LABELS,
                signal: lifetime.signal,
            });
            this._h3v2Settings = settings;
            const leading = document.createElement("div");
            leading.className = "h3lvm-v2-leading";
            leading.append(source.element, settings.element);
            const options = {
                leading,
                leadingHeight: 48 + settings.minHeight,
            };
            if (isManager) installManagerPanel(this, options);
            else installSmartPanel(this, options);
            return result;
        };

        const originalConfigure = nodeType.prototype.configure;
        nodeType.prototype.configure = function (info) {
            const result = originalConfigure?.apply(this, arguments);
            this._h3v2Source?.refresh();
            this._h3v2Settings?.refresh();
            this._h3lvmRefreshProjects?.();
            this._h3lvmDeckRefresh?.();
            return result;
        };

        const originalExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const result = originalExecuted?.apply(this, arguments);
            this._h3lvmRefreshProjects?.();
            return result;
        };

        const originalRemoved = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            this._h3v2Source?.close();
            this._h3lvmManagerLifetime?.abort();
            this._h3lvmSmartLifetime?.abort();
            return originalRemoved?.apply(this, arguments);
        };

        const originalConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const result = originalConnectionsChange?.apply(this, arguments);
            this._h3v2Settings?.refresh();
            return result;
        };
    },
});
