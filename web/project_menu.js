// RAFOLIE 2026-10-03: the project bin menu, shared by both panels.
//
// Why: the Segment Picker already had a labelled project row with inline create and
// delete, and the Manager node had a raw canvas dropdown instead. Same action, two
// looks — so the row now lives here once and both nodes use it.
//
// It writes through the node widget (project_name) so the graph and any saved
// workflow keep the same field; nothing here is stored twice.

import { api } from "../../scripts/api.js";

const DEFAULT_PROJECT = "H3_LVM";

// Menu actions rather than bin names.
const NEW_PROJECT = "__h3lvm_new__";
const DELETE_PROJECT = "__h3lvm_delete__";

/**
 * @param {object} options
 * @param {object} options.node     the LGraphNode that owns the project_name widget
 * @param {object} options.widget   the project_name widget (string or combo)
 * @param {AbortSignal} options.signal  dies with the node
 * @param {(name: string) => void} [options.onChange]  called after the bin changes
 * @returns {{element: HTMLElement, refresh: () => Promise<void>, name: () => string}}
 */
export function createProjectMenu({ node, widget, signal, onChange }) {
    let bins = [];

    const root = document.createElement("div");

    // Row 1 - which bin to read is the first decision in this workflow, so it gets
    // a full-width labelled row of its own.
    const projectRow = document.createElement("div");
    projectRow.className = "h3lvm-project-row";

    const projectLabel = document.createElement("span");
    projectLabel.className = "h3lvm-project-label";
    projectLabel.textContent = "📦 项目素材库";
    projectLabel.title = "打开菜单可以切换项目，也可以新建或删除项目";

    const projectSelect = document.createElement("select");
    projectSelect.className = "h3lvm-project";
    projectSelect.title = "切换项目素材库；菜单内可新建或删除项目";

    const projectCount = document.createElement("span");
    projectCount.className = "h3lvm-count";
    projectCount.textContent = "读取中…";

    projectRow.append(projectLabel, projectSelect, projectCount);
    root.appendChild(projectRow);

    // Name entry for a new bin; only visible while the menu is on "＋ 新建项目…".
    const createRow = document.createElement("div");
    createRow.className = "h3lvm-new";
    createRow.hidden = true;
    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.className = "h3lvm-new-input";
    nameInput.placeholder = "新项目名（例如：科幻短片 01）";
    const createBtn = document.createElement("button");
    createBtn.className = "h3lvm-refresh-btn";
    createBtn.textContent = "✔ 建立";
    const cancelCreateBtn = document.createElement("button");
    cancelCreateBtn.className = "h3lvm-refresh-btn";
    cancelCreateBtn.textContent = "✕ 取消";
    const createError = document.createElement("span");
    createError.className = "h3lvm-new-error";
    createRow.append(nameInput, createBtn, cancelCreateBtn, createError);
    root.appendChild(createRow);

    // Deleting a bin is the mirror of creating one, so it opens in the same place.
    const deleteRow = document.createElement("div");
    deleteRow.className = "h3lvm-new h3lvm-danger";
    deleteRow.hidden = true;
    const deleteText = document.createElement("span");
    deleteText.className = "h3lvm-danger-text";
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "h3lvm-danger-btn";
    const cancelDeleteBtn = document.createElement("button");
    cancelDeleteBtn.className = "h3lvm-refresh-btn";
    cancelDeleteBtn.textContent = "✕ 取消";
    const deleteError = document.createElement("span");
    deleteError.className = "h3lvm-new-error";
    deleteRow.append(deleteText, deleteBtn, cancelDeleteBtn, deleteError);
    root.appendChild(deleteRow);

    function currentName() {
        const raw = widget?.value;
        return typeof raw === "string" && raw.trim() ? raw.trim() : DEFAULT_PROJECT;
    }

    // Creating a bin, the panel's own reload and the refresh button can all ask for
    // the list at the same moment; one request at a time keeps the menu consistent.
    let inFlight = null;

    function refresh() {
        if (!inFlight) {
            inFlight = refreshBins().finally(() => { inFlight = null; });
        }
        return inFlight;
    }

    async function refreshBins() {
        let list = [];
        let fetched = false;
        try {
            const res = await api.fetchApi("/h3_lvm/projects", { cache: "no-store" });
            if (res.ok) {
                const data = await res.json().catch(() => ({}));
                list = Array.isArray(data.projects) ? data.projects : [];
                fetched = true;
            }
        } catch (error) {
            if (!signal.aborted) console.warn("[H3 LVM] projects lookup failed:", error);
        }
        if (signal.aborted) return;

        const active = currentName();
        if (!list.some(bin => bin.name === active)) {
            list.unshift({ name: active, segments: 0 });
        }
        bins = list;

        // The number beside the menu is the bin total from this same reply, so the
        // Manager panel shows a real count too instead of a stuck "reading" label.
        if (fetched) {
            const shown = bins.find(bin => bin.name === active);
            if (shown) {
                projectCount.textContent = shown.segments ? `共 ${shown.segments} 段` : "空库";
            }
        }

        projectSelect.innerHTML = "";
        const newOption = document.createElement("option");
        newOption.value = NEW_PROJECT;
        newOption.textContent = "＋ 新建项目…";
        projectSelect.appendChild(newOption);
        for (const bin of bins) {
            const option = document.createElement("option");
            option.value = bin.name;
            option.textContent = bin.segments ? `${bin.name} (${bin.segments} 段)` : `${bin.name}（空）`;
            if (bin.name === active) option.selected = true;
            projectSelect.appendChild(option);
        }
        const deleteOption = document.createElement("option");
        deleteOption.value = DELETE_PROJECT;
        deleteOption.textContent = "🗑 删除当前项目…";
        projectSelect.appendChild(deleteOption);

        // A hidden canvas combo still has to accept the value the graph stores.
        if (widget?.options) {
            widget.options.values = [active, ...bins.map(bin => bin.name)]
                .filter((name, index, all) => name && all.indexOf(name) === index);
        }
        if (widget && widget.value !== active) widget.value = active;
    }

    async function setProject(name) {
        closeCreateRow();
        closeDeleteRow();
        if (widget) {
            widget.value = name;
            widget.callback?.(name);
            node.setDirtyCanvas?.(true, true);
        }
        onChange?.(name);
        // The menu has to show the bin that was just created (and drop the one just
        // deleted) on its own. Waiting for the panel to reload is what made 建立 look
        // like it did nothing.
        await refresh();
    }

    function openCreateRow() {
        createRow.hidden = false;
        createError.textContent = "";
        nameInput.focus();
    }

    function closeCreateRow() {
        createRow.hidden = true;
        nameInput.value = "";
        createError.textContent = "";
    }

    async function createProject() {
        const typed = nameInput.value.trim();
        if (!typed) {
            createError.textContent = "先写个名字。";
            nameInput.focus();
            return;
        }
        createBtn.disabled = true;
        createError.textContent = "";
        try {
            const res = await api.fetchApi("/h3_lvm/project", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project: typed }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                createError.textContent = data.error || `建立失败（HTTP ${res.status}）`;
                return;
            }
            await setProject(data.name || typed);
        } catch (error) {
            console.warn("[H3 LVM] create project failed:", error);
            createError.textContent = "建立失败：连不上后台服务。";
        } finally {
            createBtn.disabled = false;
        }
    }

    function openDeleteRow() {
        const name = currentName();
        const bin = bins.find(item => item.name === name) || { segments: 0 };
        deleteText.textContent = `删除「${name}」会同时删掉 ${bin.segments} 个已保存片段（含缩略图和预览），此操作不可撤销。`;
        deleteBtn.textContent = `✔ 删除「${name}」`;
        deleteRow.dataset.project = name;
        deleteError.textContent = "";
        deleteRow.hidden = false;
    }

    function closeDeleteRow() {
        deleteRow.hidden = true;
        deleteRow.dataset.project = "";
        deleteError.textContent = "";
    }

    // The panel always needs somewhere to point, so after a delete it moves to the
    // default bin when there is one, otherwise to whatever is left.
    function nextProjectAfter(name) {
        const remaining = bins.map(item => item.name).filter(item => item && item !== name);
        if (remaining.includes(DEFAULT_PROJECT)) return DEFAULT_PROJECT;
        return remaining[0] || DEFAULT_PROJECT;
    }

    async function deleteProject() {
        const name = deleteRow.dataset.project;
        if (!name) return;
        deleteBtn.disabled = true;
        deleteError.textContent = "";
        try {
            const res = await api.fetchApi("/h3_lvm/project/delete", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project: name, confirm: name }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                deleteError.textContent = data.error || `删除失败（HTTP ${res.status}）`;
                return;
            }
            await setProject(nextProjectAfter(name));
        } catch (error) {
            console.warn("[H3 LVM] delete project failed:", error);
            deleteError.textContent = "删除失败：连不上后台服务。";
        } finally {
            deleteBtn.disabled = false;
        }
    }

    projectSelect.onchange = () => {
        const chosen = projectSelect.value;
        if (chosen === NEW_PROJECT) {
            projectSelect.value = currentName();
            openCreateRow();
            return;
        }
        if (chosen === DELETE_PROJECT) {
            projectSelect.value = currentName();
            openDeleteRow();
            return;
        }
        if (chosen && chosen !== currentName()) setProject(chosen);
    };
    createBtn.onclick = (event) => {
        event.stopPropagation();
        createProject();
    };
    cancelCreateBtn.onclick = (event) => {
        event.stopPropagation();
        closeCreateRow();
    };
    nameInput.onkeydown = (event) => {
        event.stopPropagation();
        if (event.key === "Enter") createProject();
        if (event.key === "Escape") closeCreateRow();
    };
    deleteBtn.onclick = (event) => {
        event.stopPropagation();
        deleteProject();
    };
    cancelDeleteBtn.onclick = (event) => {
        event.stopPropagation();
        closeDeleteRow();
    };

    void refresh();

    return { element: root, refresh, name: currentName, countText: projectCount };
}
