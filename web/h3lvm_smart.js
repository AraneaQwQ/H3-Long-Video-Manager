// RAFOLIE 2026-10-09: Chinese labels and the project panel for the
// "H3 Smart Split" node.
//
// What this node is: the second producer for the SAME project bin. H3 Long Video
// Manager cuts equal 17n+5 slices; Smart Split cuts on real shot boundaries and
// changes nothing else. So the UI here is the Manager's UI on purpose, including the
// card deck - the deck belongs to the bin, and its code lives in deck_panel.js so
// the two panels cannot drift apart.
//
// Display only. Field names and the values stored in workflow files are unchanged:
//   - widget.label and getOptionLabel change what is drawn, nothing else.
//   - project_name is re-declared as a combo of the real bins before registration,
//     then hidden: the panel's project menu writes through that same widget, so
//     there is one control per setting instead of two.
//
// The widget order is left exactly as the server declares it. ComfyUI restores
// saved values by position, so re-ordering widgets here would scramble graphs.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addPanel } from "./dom_panel.js";
import { createProjectMenu } from "./project_menu.js";
import { createDeck } from "./deck_panel.js";

// The panel reuses the Picker stylesheet; inject it here too so this node works on
// its own if another script fails to load. Same id as the other files = one link.
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

const NODE_NAME = "H3 Smart Split";
const PROJECT_FIELD = "project_name";
const DEFAULT_PROJECT = "H3_LVM";

// Project menu + tool row + one card row + the two rule lines. Same height as the
// Manager panel on purpose. Fixed on purpose: the panel has no collapse button and
// never changes its own height, so pressing the refresh or card-size button can
// never shrink the node to its minimum.
const PANEL_H = 320;

// Field names stay English inside the workflow; only the label on the node changes.
const LABELS = {
    fps: "源视频帧率",
    detection_sensitivity: "镜头切点灵敏度",
    motion_context_frames: "Motion Context 帧数",
    segment_id: "输出片段编号",
    scale_percent: "画面缩放 %",
    project_name: "📦 项目素材库",
    save_enabled: "保存到素材库",
    save_preview_mp4: "生成 MP4 预览",
    save_dtype: "素材存盘精度",
};

const TOOLTIPS = {
    fps: "上游视频的真实帧率。MiniMax H3 生成的视频一般是 24 fps。",
    detection_sensitivity: "只决定「在哪里切」：漏切选高，误切过多选低。任何一档都不改变切分规则本身——不丢帧、不重复主帧、不补帧、不做 17n+5 对齐。",
    motion_context_frames: "每段前面多带几帧重叠画面，用来接上上一段的动作。0 表示不重叠。它只放大提取范围，不会移动镜头切点。",
    segment_id: "把第几段输出到下游预览；所有片段都会照常保存到素材库。",
    scale_percent: "输出前整体缩放画面。",
    project_name: "保存到哪个项目素材库；面板顶部的菜单可以切换、新建或删除项目。",
    save_enabled: "关闭后只在画布输出，不写入素材库。",
    save_preview_mp4: "为每个片段额外生成可播放的 MP4 预览。",
    save_dtype: "素材库里的片段张量用什么精度落盘。源视频本身只有 8-bit，所以 int8 体积减半而画面读回来一样；只有需要保留原始浮点张量时才选 fp16。同一个库里可以混用，读取时按各自存的精度还原。",
};

// Raw values are kept as-is; only the text in the dropdown is Chinese.
const OPTION_LABELS = {
    detection_sensitivity: {
        low: "低（只切明显硬切）",
        medium: "中（默认）",
        high: "高（更容易切出更多镜头）",
    },
    motion_context_frames: {
        "0": "0 帧（不与上一段重叠，默认）",
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

app.registerExtension({
    name: "H3.LVM.SmartSplit",

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
                installSmartPanel(this);
            } catch (error) {
                console.warn("[H3 LVM] smart split node UI setup failed (node still works):", error);
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
            this._h3lvmDeckRefresh?.();
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
            this._h3lvmSmartLifetime?.abort();
            return originalRemoved ? originalRemoved.apply(this, arguments) : undefined;
        };
    },
});

// --- The panel: project menu + the shared card deck ---
function installSmartPanel(node) {
    const lifetime = node._h3lvmSmartLifetime ?? new AbortController();
    node._h3lvmSmartLifetime = lifetime;
    const signal = lifetime.signal;

    function widgetFor(name) {
        return node.widgets?.find(item => item.name === name);
    }

    const container = document.createElement("div");
    container.className = "h3lvm-container";

    // Row 1 - same menu as the Picker and the Manager: switch / create / delete.
    const menu = createProjectMenu({
        node,
        widget: widgetFor(PROJECT_FIELD),
        signal,
        onChange: () => void deck.render(),
    });
    container.appendChild(menu.element);
    node._h3lvmRefreshProjects = menu.refresh;

    // Row 2 - the same card deck as the Manager node. Both nodes write into the same
    // bin, so both show the same cards; the deck code lives in deck_panel.js so the
    // two panels cannot drift apart. Clicking a card sets 输出片段编号, and 合并模式
    // joins the cards that automatic splitting cut too small.
    const deck = createDeck({
        node,
        signal,
        container,
        projectField: PROJECT_FIELD,
        segmentField: "segment_id",
        onRefresh: () => void menu.refresh(),
    });

    addPanel(node, "h3lvm_smart_panel", container, PANEL_H);

    // The deck belongs to the bin, not to this page visit: opening the workflow again
    // shows the cards right away. The project name is only restored in configure(),
    // which runs after onNodeCreated, so configure() calls this hook once the widgets
    // hold their saved values.
    node._h3lvmDeckRefresh = deck.render;

    void deck.render();
}

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

// --- The panel owns the project menu, so the canvas widget steps aside ---
function hideProjectWidget(node) {
    const widget = node.widgets?.find(item => item.name === PROJECT_FIELD);
    if (!widget?.options) return;
    // options.hidden is what the frontend layout itself filters on, and the value is
    // still serialised by position, so saved graphs keep working.
    widget.options.hidden = true;
}