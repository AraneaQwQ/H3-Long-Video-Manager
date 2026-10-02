// RAFOLIE 2026-10-03: Chinese labels and the visual panel for the
// "H3 Long Video Manager" node.
//
// Display only. Field names and the values stored in workflow files are unchanged:
//   - widget.label and getOptionLabel change what is drawn, nothing else.
//   - project_name is re-declared as a combo in the node definition before the node
//     type is registered, so the widget really is a dropdown of the project bins on
//     disk. A workflow still stores the bin name as a plain string.
//   - That combo is then hidden: the panel shows the same project menu the Segment
//     Picker uses (switch / create / delete), and it writes through this widget, so
//     there is one control per setting instead of two.
//
// The widget order is left exactly as the server declares it. ComfyUI restores saved
// values by position, so re-ordering widgets here would scramble graphs written
// before this file existed.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { installManagerPanel } from "./h3lvm_manager_panel.js";

// The panel reuses the Picker stylesheet; inject it here too so the Manager works
// on its own if the Picker script ever fails to load.
try {
    const styleId = "h3lvm-styles";
    if (!document.getElementById(styleId)) {
        const link = document.createElement("link");
        link.id = styleId;
        link.rel = "stylesheet";
        link.type = "text/css";
        link.href = new URL("./h3lvm_picker.css", import.meta.url).href;
        document.head.appendChild(link);
    }
} catch (error) {
    console.warn("[H3 LVM] CSS injection failed:", error);
}

const NODE_NAME = "H3 Long Video Manager";
const PROJECT_FIELD = "project_name";
const DEFAULT_PROJECT = "H3_LVM";

// Field names stay English inside the workflow; only the label on the node changes.
const LABELS = {
    fps: "源视频帧率",
    segment_duration: "每段时长（秒）",
    motion_context_frames: "Motion Context 帧数",
    segment_id: "输出片段编号",
    scale_percent: "画面缩放 %",
    align_to_h3_grid: "对齐 H3 网格",
    project_name: "📦 项目素材库",
    save_enabled: "保存到素材库",
    save_preview_mp4: "生成 MP4 预览",
    person_crop: "人物裁切",
    person_crop_expand_percent: "人物框外扩 %",
    save_dtype: "素材存盘精度",
};

const TOOLTIPS = {
    fps: "上游视频的真实帧率。MiniMax H3 生成的视频一般是 24 fps。",
    segment_duration: "每段输出的固定时长（秒），已包含 Motion Context 重叠帧。实际帧数会向下取到 17n+5：6.0s@24fps → 141 帧 = 5.875s，每段都一样。",
    motion_context_frames: "与上一段重叠的帧数，用来接上上一段的动作。0 表示不重叠。",
    segment_id: "把第几段直接输出到下游预览；其余片段仍会保存到素材库。",
    scale_percent: "输出前整体缩放画面。",
    align_to_h3_grid: "开启后每段帧数向下取到 H3 支持的 17n+5；关闭则正好是所填时长（H3 可能自行吸附）。",
    project_name: "保存到哪个项目素材库；面板顶部的菜单可以切换、新建或删除项目。",
    save_enabled: "关闭后只在画布输出，不写入素材库。",
    save_preview_mp4: "为每个片段额外生成可播放的 MP4 预览。",
    person_crop: "检测人物并裁掉画面边缘，让人物占画面更大。",
    person_crop_expand_percent: "人物框外扩百分比，0 为紧贴检测框（仍保持原画面比例）。",
    save_dtype: "素材库里的片段张量用什么精度落盘。源视频本身只有 8-bit，所以 int8 体积减半而画面读回来一样；只有需要保留原始浮点张量时才选 fp16。同一个库里可以混用，读取时按各自存的精度还原。",
};

// Raw values are kept as-is; only the text in the dropdown is Chinese.
// Widgets the node still declares so old graphs keep their
// positions, but that no longer do anything and must not be shown.
const RETIRED_FIELDS = ["final_align"];

const OPTION_LABELS = {
    save_dtype: {
        int8: "int8（体积减半，推荐）",
        fp16: "fp16（旧格式，体积翻倍）",
    },
    motion_context_frames: {
        "0": "0 帧（不与上一段重叠）",
        "5": "5 帧",
        "22": "22 帧（默认）",
        "39": "39 帧",
        "56": "56 帧",
    },
};

app.registerExtension({
    name: "H3.LVM.Manager",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) return;

        // The list has to be part of the node definition: the widget class is chosen
        // from it, and a plain string field is always drawn as a text box.
        let bins = [];
        try {
            bins = await listProjects();
        } catch (error) {
            console.warn("[H3 LVM] project list unavailable at register time:", error);
        }
        declareProjectCombo(nodeData, bins);

        const originalCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = originalCreated ? originalCreated.apply(this, arguments) : undefined;
            try {
                translateWidgets(this);
                hideProjectWidget(this);
                hideRetiredWidgets(this);
                installManagerPanel(this);
            } catch (error) {
                console.warn("[H3 LVM] manager node UI setup failed (node still works):", error);
            }
            return r;
        };

        const originalConfigure = nodeType.prototype.configure;
        nodeType.prototype.configure = function (info) {
            try {
                // A saved bin must be a valid option before the graph restores it.
                allowSavedProject(this, info);
            } catch (error) {
                console.warn("[H3 LVM] could not prepare the saved project:", error);
            }
            const r = originalConfigure ? originalConfigure.apply(this, arguments) : undefined;
            this._h3lvmRefreshProjects?.();
            return r;
        };

        const originalExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const r = originalExecuted ? originalExecuted.apply(this, arguments) : undefined;
            this._h3lvmRefreshProjects?.();
            return r;
        };

        const originalRemoved = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            this._h3lvmManagerLifetime?.abort();
            return originalRemoved ? originalRemoved.apply(this, arguments) : undefined;
        };
    },
});

// --- Node definition: project_name becomes a dropdown of the real bins ---
function declareProjectCombo(nodeData, bins) {
    const groups = [nodeData.input?.optional, nodeData.input?.required];
    for (let index = 0; index < groups.length; index++) {
        const group = groups[index];
        if (!group || !(PROJECT_FIELD in group)) continue;
        const spec = group[PROJECT_FIELD];
        const kwargs = Array.isArray(spec) && spec[1] && typeof spec[1] === "object" ? spec[1] : {};
        const saved = typeof kwargs.default === "string" && kwargs.default.trim() ? kwargs.default.trim() : DEFAULT_PROJECT;
        const values = menuValues(bins.map(bin => bin.name), saved);
        group[PROJECT_FIELD] = [values, { ...kwargs, default: saved }];
        delete group[PROJECT_FIELD][1].placeholder;
        return;
    }
}

function menuValues(names, active) {
    const ordered = [];
    for (const name of [active, DEFAULT_PROJECT, ...names]) {
        if (typeof name !== "string") continue;
        const trimmed = name.trim();
        if (!trimmed || ordered.includes(trimmed)) continue;
        ordered.push(trimmed);
    }
    return ordered;
}

async function listProjects() {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 3000);
    try {
        const res = await api.fetchApi("/h3_lvm/projects", { cache: "no-store", signal: controller.signal });
        if (!res.ok) return [];
        const data = await res.json().catch(() => ({}));
        return Array.isArray(data.projects) ? data.projects : [];
    } finally {
        clearTimeout(timer);
    }
}

// --- Labels ---
function translateWidgets(node) {
    for (const widget of node.widgets ?? []) {
        const label = LABELS[widget.name];
        if (label) widget.label = label;
        const tooltip = TOOLTIPS[widget.name];
        if (tooltip) widget.tooltip = tooltip;
        const optionLabels = OPTION_LABELS[widget.name];
        if (optionLabels && widget.options) {
            widget.options.getOptionLabel = (value) => optionLabels[String(value)] ?? String(value ?? "");
        }
    }
}

// --- Loading a saved graph: keep the stored bin selectable ---
function savedProjectValue(node, info) {
    const named = info?.widgets_values_named;
    if (named && typeof named[PROJECT_FIELD] === "string") return named[PROJECT_FIELD].trim();
    const values = info?.widgets_values;
    if (!Array.isArray(values)) return "";
    const index = (node.widgets ?? []).findIndex(widget => widget.name === PROJECT_FIELD);
    if (index < 0 || index >= values.length) return "";
    return typeof values[index] === "string" ? values[index].trim() : "";
}

function allowSavedProject(node, info) {
    const widget = node.widgets?.find(item => item.name === PROJECT_FIELD);
    const options = widget?.options;
    if (!options) return;
    const saved = savedProjectValue(node, info);
    if (!saved) return;
    const values = Array.isArray(options.values) ? [...options.values] : [];
    if (values.includes(saved)) return;
    values.unshift(saved);
    options.values = values;
}

// --- Retired parameters stay in the graph but off the node ---
function hideRetiredWidgets(node) {
    for (const name of RETIRED_FIELDS) {
        const widget = node.widgets?.find(item => item.name === name);
        if (widget?.options) widget.options.hidden = true;
    }
}

// --- The panel owns the project menu, so the canvas widget steps aside ---
function hideProjectWidget(node) {
    const widget = node.widgets?.find(item => item.name === PROJECT_FIELD);
    if (!widget?.options) return;
    // options.hidden is what the frontend layout itself filters on, and the value is
    // still serialised by position, so saved graphs keep working.
    widget.options.hidden = true;
}
