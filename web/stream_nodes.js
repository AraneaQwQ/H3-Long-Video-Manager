import { app } from "../../scripts/app.js";
import { installManagerPanel } from "./h3lvm_manager_panel.js";
import { installSmartPanel } from "./h3lvm_smart.js";
import { createSourceControls } from "./source_preview.js";

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
};

function prepareWidgets(node) {
    for (const widget of node.widgets ?? []) {
        if (LABELS[widget.name]) widget.label = LABELS[widget.name];
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
            const source = createSourceControls(this);
            this._h3v2Source = source;
            const options = { leading: source.element };
            if (isManager) installManagerPanel(this, options);
            else installSmartPanel(this, options);
            return result;
        };

        const originalConfigure = nodeType.prototype.configure;
        nodeType.prototype.configure = function (info) {
            const result = originalConfigure?.apply(this, arguments);
            this._h3v2Source?.refresh();
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
    },
});
