// RAFOLIE 2026-10-03: Chinese labels and a project dropdown for the
// "H3 Long Video Manager" node.
//
// Display only. Field names and the values stored in workflow files are unchanged:
//   - widget.label and getOptionLabel change what is drawn, nothing else.
//   - project_name is re-declared as a combo in the node definition before the node
//     type is registered, so the widget really is a dropdown of the project bins on
//     disk. A workflow still stores the bin name as a plain string.
//   - The dropdown can create and delete bins, the same way the Segment Picker panel
//     does. Those two menu actions are internal markers and are never saved.
//
// The widget order is left exactly as the server declares it. ComfyUI restores saved
// values by position, so re-ordering widgets here would scramble graphs written
// before this file existed.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_NAME = "H3 Long Video Manager";
const PROJECT_FIELD = "project_name";
const DEFAULT_PROJECT = "H3_LVM";

// Menu actions rather than project names; they never become the widget value.
const NEW_PROJECT = "__h3lvm_new__";
const DELETE_PROJECT = "__h3lvm_delete__";
const MENU_ACTIONS = [NEW_PROJECT, DELETE_PROJECT];
const MENU_LABELS = {
    [NEW_PROJECT]: "＋ 新建项目…",
    [DELETE_PROJECT]: "🗑 删除当前项目…",
};

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
    final_align: "段尾对齐",
    person_crop: "人物裁切",
    person_crop_expand_percent: "人物框外扩 %",
};

const TOOLTIPS = {
    fps: "上游视频的真实帧率。MiniMax H3 生成的视频一般是 24 fps。",
    segment_duration: "每一段裁切的时长（秒）。",
    motion_context_frames: "与上一段重叠的帧数，用来接上上一段的动作。0 表示不重叠。",
    segment_id: "把第几段直接输出到下游预览；其余片段仍会保存到素材库。",
    scale_percent: "输出前整体缩放画面。",
    align_to_h3_grid: "把每段帧数对齐到 H3 支持的帧数网格。",
    project_name: "选择保存到哪个项目素材库。下拉里可以切换、新建或删除项目。",
    save_enabled: "关闭后只在画布输出，不写入素材库。",
    save_preview_mp4: "为每个片段额外生成可播放的 MP4 预览。",
    final_align: "最后一段不足时长时，向下或向上取整。",
    person_crop: "检测人物并裁掉画面边缘，让人物占画面更大。",
    person_crop_expand_percent: "人物框外扩百分比，0 为紧贴检测框（仍保持原画面比例）。",
};

// Raw values are kept as-is; only the text in the dropdown is Chinese.
const OPTION_LABELS = {
    motion_context_frames: {
        "0": "0 帧（不与上一段重叠）",
        "5": "5 帧",
        "22": "22 帧（默认）",
        "39": "39 帧",
        "56": "56 帧",
    },
    final_align: {
        down: "向下取整（推荐）",
        up: "向上取整",
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
                installProjectMenu(this);
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
        if (!trimmed || MENU_ACTIONS.includes(trimmed) || ordered.includes(trimmed)) continue;
        ordered.push(trimmed);
    }
    return [NEW_PROJECT, ...ordered, DELETE_PROJECT];
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
    if (!saved || MENU_ACTIONS.includes(saved)) return;
    const values = Array.isArray(options.values) ? [...options.values] : [];
    if (values.includes(saved)) return;
    const at = values.indexOf(DELETE_PROJECT);
    values.splice(at < 0 ? values.length : at, 0, saved);
    options.values = values;
}

// --- Project menu on the project_name widget ---
function installProjectMenu(node) {
    const widget = node.widgets?.find(item => item.name === PROJECT_FIELD);
    if (!widget || !widget.options) return;

    const lifetime = new AbortController();
    node._h3lvmManagerLifetime = lifetime;
    let bins = [];
    let activeName = typeof widget.value === "string" && widget.value.trim() ? widget.value.trim() : DEFAULT_PROJECT;

    // The canvas draws this label for both the widget text and the dropdown rows.
    widget.options.getOptionLabel = (value) => {
        const key = String(value ?? "");
        if (MENU_LABELS[key]) return MENU_LABELS[key];
        const bin = bins.find(item => item.name === key);
        if (!bin) return key;
        return bin.segments ? key + " (" + bin.segments + " 段)" : key + "（空）";
    };

    // The two menu actions are not bins, so the value is put back before anything
    // else sees it.
    const originalCallback = widget.callback;
    widget.callback = (value, ...rest) => {
        const picked = String(value ?? "");
        if (picked === NEW_PROJECT) {
            widget.value = activeName;
            node.setDirtyCanvas?.(true, true);
            void createProject();
            return;
        }
        if (picked === DELETE_PROJECT) {
            widget.value = activeName;
            node.setDirtyCanvas?.(true, true);
            void deleteProject();
            return;
        }
        activeName = picked;
        return originalCallback?.(value, ...rest);
    };

    function writeOptions() {
        // Assign rather than mutate: the array from the node definition is shared by
        // every node of this type, so editing it in place would leak between nodes.
        widget.options.values = menuValues(bins.map(bin => bin.name), activeName);
    }

    async function refresh() {
        if (lifetime.signal.aborted) return;
        const current = typeof widget.value === "string" ? widget.value.trim() : "";
        if (current && !MENU_ACTIONS.includes(current)) activeName = current;
        try {
            bins = await listProjects();
        } catch (error) {
            console.warn("[H3 LVM] projects lookup failed:", error);
        }
        if (lifetime.signal.aborted) return;
        if (!bins.some(bin => bin.name === activeName)) bins = [{ name: activeName, segments: 0 }, ...bins];
        writeOptions();
        if (widget.value !== activeName) widget.value = activeName;
        node.setDirtyCanvas?.(true, true);
    }

    function setProject(name) {
        activeName = name;
        widget.value = name;
        originalCallback?.(name);
        node.setDirtyCanvas?.(true, true);
    }

    async function createProject() {
        const typed = window.prompt("新项目素材库名称（例如：科幻短片 01）", "");
        if (typed === null) return;
        const name = typed.trim();
        if (!name) {
            window.alert("先写个名字。");
            return;
        }
        try {
            const res = await api.fetchApi("/h3_lvm/project", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project: name }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                window.alert(data.error || "建立失败（HTTP " + res.status + "）");
                return;
            }
            setProject(data.name || name);
        } catch (error) {
            console.warn("[H3 LVM] create project failed:", error);
            window.alert("建立失败：连不上后台服务。");
        }
        await refresh();
    }

    function nextProjectAfter(name) {
        const remaining = bins.map(bin => bin.name).filter(item => item && item !== name);
        if (remaining.includes(DEFAULT_PROJECT)) return DEFAULT_PROJECT;
        return remaining[0] || DEFAULT_PROJECT;
    }

    async function deleteProject() {
        const bin = bins.find(item => item.name === activeName) || { segments: 0 };
        const warning = "删除「" + activeName + "」会同时删掉 " + bin.segments + " 个已保存片段（含缩略图和预览），此操作不可撤销。";
        if (!window.confirm(warning)) return;
        try {
            const res = await api.fetchApi("/h3_lvm/project/delete", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project: activeName, confirm: activeName }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                window.alert(data.error || "删除失败（HTTP " + res.status + "）");
                return;
            }
            setProject(nextProjectAfter(activeName));
        } catch (error) {
            console.warn("[H3 LVM] delete project failed:", error);
            window.alert("删除失败：连不上后台服务。");
        }
        await refresh();
    }

    const onChanged = () => {
        void refresh();
    };
    api.addEventListener("h3_lvm/changed", onChanged);
    api.addEventListener("execution_success", onChanged);
    lifetime.signal.addEventListener("abort", () => {
        api.removeEventListener("h3_lvm/changed", onChanged);
        api.removeEventListener("execution_success", onChanged);
        delete node._h3lvmRefreshProjects;
    }, { once: true });

    node._h3lvmRefreshProjects = refresh;
    void refresh();
}
