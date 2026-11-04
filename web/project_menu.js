// RAFOLIE 2026-10-03: the project bin menu, shared by both panels.
//
// The menu writes through the node widget (project_name), so the graph and any
// saved workflow keep the same field; nothing here is stored twice.
//
// 2026-11-02: the plain <select> became a card grid. A name alone is hard to
// scan once a story has several bins, so each project shows its first saved
// card as a cover, its count and its last update. Rename, create and delete
// live in the same popup; selecting a card still only writes project_name.

import { api } from "../../scripts/api.js";

const DEFAULT_PROJECT = "H3_LVM";

// What a menu is allowed to say about one library. Every scope counts a different
// key ("segments" / "videos" / "references") and holds a different thing, so the
// unit word and the delete warning belong here rather than in a refScope boolean.
const REFERENCE_CONFIG = {
    field: "references",
    label: "📦 项目素材库",
    labelTitle: "打开菜单可以切换项目，也可以新建、重命名或删除项目",
    placeholder: "新项目名（例如：科幻短片 01）",
    empty: "无预设",
    count: (total) => `${total} 张参考`,
    warning: null, // reference bins describe the preset plus any segments, below
};

const SCOPE_CONFIG = {
    segments: {
        field: "segments",
        label: "📦 项目素材库",
        labelTitle: "打开菜单可以切换项目，也可以新建、重命名或删除项目",
        placeholder: "新项目名（例如：科幻短片 01）",
        empty: "空库",
        count: (total) => `${total} 段`,
        warning: (name, total) =>
            `删除「${name}」会同时删掉 ${total} 个已保存片段（含缩略图和预览），此操作不可撤销。`,
    },
    uploads: {
        field: "videos",
        label: "📦 项目视频库",
        labelTitle: "当前模式的投放视频库；这里的新建/重命名/删除会同时处理同名项目",
        placeholder: "新项目名（例如：投放素材 01）",
        empty: "空视频库",
        count: (total) => `${total} 个视频`,
        warning: (name, total) =>
            `删除「${name}」会同时删掉 ${total} 个投放视频（原文件与封面），此操作不可撤销；`
            + "裁切片段库里的同名项目不受影响。",
    },
    image: REFERENCE_CONFIG,
    audio: REFERENCE_CONFIG,
};

const COVER_ICON = { segments: "🎬", uploads: "📹", image: "🖼️", audio: "🎵" };

// One popup at a time. Opening a second menu closes the first one, which is
// what a click outside already looks like.
let openMenuClose = null;
const projectRequests = new Map();

function fetchProjectBins(url) {
    if (!projectRequests.has(url)) {
        const request = (async () => {
            const res = await api.fetchApi(url, { cache: "no-store" });
            if (!res.ok) return [];
            const data = await res.json().catch(() => ({}));
            return Array.isArray(data.projects) ? data.projects : [];
        })().finally(() => { projectRequests.delete(url); });
        projectRequests.set(url, request);
    }
    return projectRequests.get(url);
}

function fullTime(value) {
    return String(value ?? "").trim().replace("T", " ");
}

function makeElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
}

export function createProjectMenu({ node, widget, signal, scope = "segments", onChange }) {
    // An unknown scope reads as the cut-segment bin, which is what the backend does.
    const config = SCOPE_CONFIG[scope] ?? SCOPE_CONFIG.segments;
    const refScope = config.field === "references";
    let bins = [];
    let currentPaintKey = "";
    let inFlight = null;
    let search = "";
    let editingName = "";
    let pendingDelete = "";
    let modalOpen = false;
    let sortField = "name"; // name | updated
    let sortDir = "asc";    // asc | desc
    let projectColumns = 5; // 3..6 cards per row
    const sortStoreKey = `h3lvm.projectSort.${scope}`;
    const columnsStoreKey = "h3lvm.projectColumns";
    try {
        const saved = JSON.parse(localStorage.getItem(sortStoreKey) || "{}");
        if (saved.field === "name" || saved.field === "updated") sortField = saved.field;
        if (saved.dir === "asc" || saved.dir === "desc") sortDir = saved.dir;
        const savedColumns = parseInt(localStorage.getItem(columnsStoreKey) || "", 10);
        if (savedColumns >= 3 && savedColumns <= 6) projectColumns = savedColumns;
    } catch (_) {
        // Private mode or a broken preference must not break the menu.
    }

    const root = document.createElement("div");

    // Row 1 - the current bin is a card, not a bare line of text. Its cover is
    // the first saved card's thumbnail; clicking anywhere on it opens the grid.
    const projectRow = document.createElement("div");
    projectRow.className = "h3lvm-project-row";

    const projectLabel = makeElement("span", "h3lvm-project-label", config.label);
    projectLabel.title = config.labelTitle;

    const currentCard = makeElement("button", "h3lvm-project-current");
    currentCard.type = "button";
    currentCard.title = config.labelTitle;
    const currentCover = makeElement("div", "h3lvm-project-current-cover");
    const currentBody = makeElement("div", "h3lvm-project-current-body");
    const currentNameText = makeElement("span", "h3lvm-project-current-name");
    const currentMeta = makeElement("span", "h3lvm-project-current-meta");
    const projectCount = makeElement("span", "h3lvm-count");
    const currentUpdated = makeElement("span", "h3lvm-project-updated");
    currentMeta.append(projectCount, currentUpdated);
    currentBody.append(currentNameText, currentMeta);
    currentCard.append(currentCover, currentBody);

    const chevron = makeElement("span", "h3lvm-project-chevron", "▾");
    currentCard.append(chevron);
    projectRow.append(projectLabel, currentCard);
    root.appendChild(projectRow);

    // Popup: a fixed overlay escapes the DOM widget's overflow clipping, so the
    // grid can be larger than the node without resizing the canvas node.
    const overlay = makeElement("div", "h3lvm-project-overlay");
    overlay.hidden = true;
    const modal = makeElement("div", "h3lvm-project-modal");

    const head = makeElement("div", "h3lvm-project-modal-head");
    const title = makeElement("span", "h3lvm-project-modal-title", config.label);
    const modalCount = makeElement("span", "h3lvm-project-modal-count");
    const closeBtn = makeElement("button", "h3lvm-project-close", "✕");
    closeBtn.type = "button";
    closeBtn.title = "关闭项目菜单";
    head.append(title, modalCount, closeBtn);

    const searchRow = makeElement("div", "h3lvm-project-search-row");
    const searchInput = document.createElement("input");
    searchInput.type = "search";
    searchInput.className = "h3lvm-project-search";
    searchInput.placeholder = "搜索项目…";
    const sortSelect = document.createElement("select");
    sortSelect.className = "h3lvm-project-sort";
    sortSelect.title = "项目排序字段";
    for (const [value, text] of [["name", "按名称"], ["updated", "按修改时间"]]) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = text;
        sortSelect.appendChild(option);
    }
    const sortDirBtn = makeElement("button", "h3lvm-project-sort-dir");
    sortDirBtn.type = "button";
    const columnsSelect = document.createElement("select");
    columnsSelect.className = "h3lvm-project-columns";
    columnsSelect.title = "每行显示几个项目";
    for (const count of [3, 4, 5, 6]) {
        const option = document.createElement("option");
        option.value = String(count);
        option.textContent = `${count} 列`;
        columnsSelect.appendChild(option);
    }
    // The button no longer opens or hides anything: it puts the cursor into the
    // always-visible name field, so typing can also start with a click on the field.
    const newBtn = makeElement("button", "h3lvm-project-new-btn", "＋ 新建项目");
    newBtn.type = "button";
    newBtn.title = "把光标放进项目名称框";

    // The name field and its buttons are always on screen: no second line, no
    // toggling. The two buttons stay disabled until the field holds something, so
    // the row reads as "type a name, then confirm".
    const createGroup = makeElement("div", "h3lvm-project-create");
    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.className = "h3lvm-project-name";
    nameInput.placeholder = config.placeholder;
    const createBtn = makeElement("button", "h3lvm-project-create-btn", "✔ 建立");
    createBtn.type = "button";
    const cancelCreateBtn = makeElement("button", "h3lvm-project-cancel-btn", "✕ 取消");
    cancelCreateBtn.type = "button";
    const createError = makeElement("span", "h3lvm-project-error");
    createGroup.append(nameInput, createBtn, cancelCreateBtn, createError);

    searchRow.append(newBtn, createGroup, searchInput, sortSelect, sortDirBtn, columnsSelect);

    // Deleting a bin is confirmed in a centered card over the grid, not in a row
    // above it: the sentence names what the delete removes, the two buttons sit
    // together, and the destructive click is a deliberate one.
    const deleteRow = makeElement("div", "h3lvm-project-confirm");
    deleteRow.hidden = true;
    const confirmCard = makeElement("div", "h3lvm-project-confirm-card");
    const confirmTitle = makeElement("span", "h3lvm-project-confirm-title");
    const deleteText = makeElement("span", "h3lvm-project-confirm-text");
    const deleteBtn = makeElement("button", "h3lvm-danger-btn");
    deleteBtn.type = "button";
    const cancelDeleteBtn = makeElement("button", "h3lvm-refresh-btn", "✕ 取消");
    cancelDeleteBtn.type = "button";
    const deleteError = makeElement("span", "h3lvm-new-error");
    const confirmActions = makeElement("div", "h3lvm-project-confirm-actions");
    confirmActions.append(cancelDeleteBtn, deleteBtn);
    confirmCard.append(confirmTitle, deleteText, confirmActions, deleteError);
    deleteRow.appendChild(confirmCard);

    const grid = makeElement("div", "h3lvm-project-grid");
    const modalHint = makeElement("span", "h3lvm-project-modal-hint");
    modalHint.textContent = "点卡片切换项目 · ✎ 重命名会同步所有同名库 · 🗑 删除只处理当前库。";
    modal.append(head, searchRow, grid, modalHint, deleteRow);
    overlay.appendChild(modal);

    document.body.appendChild(overlay);
    // The popup sits above the canvas; keep its pointer events from panning or
    // zooming the graph behind it.
    for (const type of ["pointerdown", "mousedown", "click", "dblclick", "wheel"]) {
        overlay.addEventListener(type, event => event.stopPropagation(), { signal });
    }

    function currentName() {
        const raw = widget?.value;
        return typeof raw === "string" && raw.trim() ? raw.trim() : DEFAULT_PROJECT;
    }

    function rawCount(bin, field = config.field) {
        const value = Number(bin?.[field]);
        return Number.isFinite(value) && value > 0 ? value : 0;
    }

    function binTotal(bin) {
        return rawCount(bin);
    }

    function countLabel(total) {
        return config.count(total);
    }

    function countTextFor(bin) {
        const total = binTotal(bin);
        return total ? `共 ${countLabel(total)}` : config.empty;
    }

    function updatedValue(bin) {
        const raw = String(bin?.updated_at ?? "").trim();
        if (!raw) return 0;
        const stamp = Date.parse(raw.replace(" ", "T"));
        return Number.isFinite(stamp) ? stamp : 0;
    }

    function sortedBins() {
        const list = bins.slice();
        list.sort((a, b) => {
            if (sortField === "updated") {
                const diff = updatedValue(a) - updatedValue(b);
                if (diff) return diff;
            }
            return a.name.localeCompare(b.name, "zh-Hans-CN", {
                numeric: true,
                sensitivity: "base",
            });
        });
        if (sortDir === "desc") list.reverse();
        return list;
    }

    function saveSort() {
        try {
            localStorage.setItem(sortStoreKey, JSON.stringify({ field: sortField, dir: sortDir }));
        } catch (_) {
            // Preference storage is optional.
        }
    }

    function syncSortUi() {
        sortSelect.value = sortField;
        sortDirBtn.textContent = sortDir === "asc" ? "↑" : "↓";
        sortDirBtn.title = sortDir === "asc" ? "当前正序，点击切换为倒序" : "当前倒序，点击切换为正序";
    }

    function saveColumns() {
        try {
            localStorage.setItem(columnsStoreKey, String(projectColumns));
        } catch (_) {
            // Preference storage is optional.
        }
    }

    function applyColumns() {
        grid.style.setProperty("--project-cols", String(projectColumns));
        columnsSelect.value = String(projectColumns);
    }

    function deleteWarning(name, bin) {
        if (!refScope) {
            const total = binTotal(bin);
            if (!total) return `删除「${name}」会删掉这个空的素材库文件夹，此操作不可撤销。`;
            return config.warning(name, total);
        }
        const parts = [];
        if (binTotal(bin)) parts.push(`它的参考预设（${binTotal(bin)} 张卡片）`);
        const segments = rawCount(bin, "segments");
        if (segments) parts.push(`${segments} 个已保存片段（含缩略图和预览）`);
        if (!parts.length) return `删除「${name}」会删掉这个空的素材库文件夹，此操作不可撤销。`;
        return `删除「${name}」会同时删掉 ${parts.join(" 与 ")}，此操作不可撤销。`;
    }

    function makeCover(bin) {
        const box = makeElement("div", "h3lvm-project-cover");
        if (bin?.cover_url) {
            const image = document.createElement("img");
            image.loading = "lazy";
            image.decoding = "async";
            image.alt = "";
            image.src = bin.cover_url;
            image.onerror = () => {
                image.remove();
                box.appendChild(makeElement("span", "h3lvm-project-cover-icon",
                    COVER_ICON[scope] || "📁"));
            };
            box.appendChild(image);
        } else {
            box.appendChild(makeElement("span", "h3lvm-project-cover-icon",
                COVER_ICON[scope] || "📁"));
        }
        return box;
    }

    function paintCurrent() {
        const active = currentName();
        const bin = bins.find(item => item.name === active)
            || { name: active, [config.field]: 0, cover_url: "", updated_at: "" };
        const paintKey = JSON.stringify([active, bin]);
        if (paintKey === currentPaintKey) return;
        currentPaintKey = paintKey;
        currentCover.textContent = "";
        currentCover.appendChild(makeCover(bin));
        currentNameText.textContent = active;
        projectCount.textContent = countTextFor(bin);
        const updated = fullTime(bin.updated_at);
        currentUpdated.textContent = updated ? `更新 ${updated}` : "";
        currentUpdated.title = updated ? `最后修改：${updated}` : "";
        currentUpdated.hidden = !updated;
        currentCard.title = `${config.labelTitle}：当前「${active}」`;
    }

    function makeAction(label, titleText, handler) {
        const button = makeElement("button", "h3lvm-project-action", label);
        button.type = "button";
        button.title = titleText;
        button.onclick = (event) => {
            event.preventDefault();
            event.stopPropagation();
            handler();
        };
        return button;
    }

    function renderTile(bin) {
        const tile = makeElement("div", "h3lvm-project-tile");
        tile.tabIndex = 0;
        tile.setAttribute("role", "button");
        tile.dataset.name = bin.name;
        if (bin.name === currentName()) tile.classList.add("active");
        tile.appendChild(makeCover(bin));

        const body = makeElement("div", "h3lvm-project-tile-body");
        if (editingName === bin.name) {
            const input = document.createElement("input");
            input.type = "text";
            input.className = "h3lvm-project-rename-input";
            input.value = bin.name;
            const error = makeElement("span", "h3lvm-new-error");
            const actions = makeElement("div", "h3lvm-project-rename-actions");
            const save = makeElement("button", "h3lvm-refresh-btn", "✔ 保存");
            save.type = "button";
            const cancel = makeElement("button", "h3lvm-refresh-btn", "✕");
            cancel.type = "button";
            save.onclick = (event) => {
                event.preventDefault();
                event.stopPropagation();
                void commitRename(bin.name, input.value, error, save);
            };
            cancel.onclick = (event) => {
                event.preventDefault();
                event.stopPropagation();
                editingName = "";
                renderGrid();
            };
            input.onkeydown = (event) => {
                event.stopPropagation();
                if (event.key === "Enter") {
                    event.preventDefault();
                    void commitRename(bin.name, input.value, error, save);
                }
                if (event.key === "Escape") {
                    event.preventDefault();
                    editingName = "";
                    renderGrid();
                }
            };
            actions.append(save, cancel);
            body.append(input, actions, error);
        } else {
            body.appendChild(makeElement("span", "h3lvm-project-tile-name", bin.name));
            const meta = makeElement("div", "h3lvm-project-tile-meta");
            meta.appendChild(makeElement("span", "h3lvm-project-tile-count", countTextFor(bin)));
            const updated = fullTime(bin.updated_at);
            if (updated) {
                const time = makeElement("span", "h3lvm-project-tile-time", updated);
                time.title = `最后修改：${updated}`;
                meta.appendChild(time);
            }
            body.appendChild(meta);
            const actions = makeElement("div", "h3lvm-project-actions");
            actions.append(
                makeAction("✎", "重命名这个项目", () => {
                    pendingDelete = "";
                    editingName = bin.name;
                    renderGrid();
                }),
                makeAction("🗑", "删除这个项目", () => {
                    editingName = "";
                    showDeleteConfirm(bin);
                }),
            );
            body.appendChild(actions);
        }
        tile.appendChild(body);

        tile.onclick = (event) => {
            if (event.target.closest("button, input")) return;
            void chooseProject(bin.name);
        };
        tile.onkeydown = (event) => {
            if (event.target !== tile) return;
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                void chooseProject(bin.name);
            }
        };
        return tile;
    }

    function renderGrid() {
        const needle = search.trim().toLowerCase();
        const ordered = sortedBins();
        const filtered = needle
            ? ordered.filter(bin => bin.name.toLowerCase().includes(needle))
            : ordered;
        grid.textContent = "";
        modalCount.textContent = `${bins.length} 个库`;
        if (!filtered.length) {
            grid.appendChild(makeElement("div", "h3lvm-project-empty",
                bins.length ? "没有匹配的项目。" : "还没有项目，点「＋ 新建项目」开始。"));
            return;
        }
        const fragment = document.createDocumentFragment();
        filtered.forEach(bin => fragment.appendChild(renderTile(bin)));
        grid.appendChild(fragment);
        if (editingName) {
            const input = grid.querySelector(".h3lvm-project-rename-input");
            if (input) requestAnimationFrame(() => {
                input.focus();
                input.select();
            });
        }
    }

    function resetCreateInput() {
        nameInput.value = "";
        showCreateError("");
        syncCreateButtons();
        nameInput.blur();
    }

    // Nothing can be confirmed until a real name is in the field; whitespace alone
    // does not count, which matches what the backend accepts.
    function syncCreateButtons() {
        const ready = nameInput.value.trim().length > 0;
        createBtn.disabled = !ready;
        cancelCreateBtn.disabled = !ready;
    }

    function showCreateError(message) {
        createError.textContent = message;
        createError.title = message;
    }

    function closeDeleteRow() {
        deleteRow.hidden = true;
        pendingDelete = "";
        deleteError.textContent = "";
    }

    function openModal() {
        if (openMenuClose && openMenuClose !== closeModal) openMenuClose();
        openMenuClose = closeModal;
        modalOpen = true;
        overlay.hidden = false;
        searchInput.value = search;
        resetCreateInput();
        closeDeleteRow();
        editingName = "";
        renderGrid();
        void refresh();
    }

    function closeModal() {
        modalOpen = false;
        overlay.hidden = true;
        editingName = "";
        pendingDelete = "";
        resetCreateInput();
        closeDeleteRow();
        if (openMenuClose === closeModal) openMenuClose = null;
    }

    currentCard.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        openModal();
    };

    closeBtn.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        closeModal();
    };
    overlay.onclick = (event) => {
        if (event.target === overlay) closeModal();
    };
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || !modalOpen) return;
        event.stopPropagation();
        // Escape backs out of the confirmation first, so a half-pressed delete
        // cannot take the whole menu (and the clicked project) with it.
        if (!deleteRow.hidden) {
            closeDeleteRow();
            return;
        }
        closeModal();
    }, { signal });

    searchInput.oninput = () => {
        search = searchInput.value;
        renderGrid();
    };
    sortSelect.onchange = () => {
        sortField = sortSelect.value === "updated" ? "updated" : "name";
        saveSort();
        syncSortUi();
        renderGrid();
    };
    sortDirBtn.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        sortDir = sortDir === "asc" ? "desc" : "asc";
        saveSort();
        syncSortUi();
        renderGrid();
    };
    columnsSelect.onchange = () => {
        const next = parseInt(columnsSelect.value, 10);
        if (next >= 3 && next <= 6) {
            projectColumns = next;
            saveColumns();
            applyColumns();
        }
    };
    newBtn.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        closeDeleteRow();
        nameInput.focus();
        nameInput.select();
    };
    cancelCreateBtn.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        resetCreateInput();
    };
    // Enter in the name field does call createProject; the button has to do the same,
    // otherwise the form only works for keyboard users.
    createBtn.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        void createProject();
    };
    nameInput.oninput = syncCreateButtons;
    nameInput.onkeydown = (event) => {
        event.stopPropagation();
        if (event.key === "Enter") {
            event.preventDefault();
            void createProject();
        }
        if (event.key === "Escape") resetCreateInput();
    };

    function showDeleteConfirm(bin) {
        pendingDelete = bin.name;
        resetCreateInput();
        confirmTitle.textContent = `删除项目「${bin.name}」`;
        deleteText.textContent = deleteWarning(bin.name, bin);
        deleteBtn.textContent = `✔ 删除「${bin.name}」`;
        deleteError.textContent = "";
        deleteRow.hidden = false;
        cancelDeleteBtn.focus();
    }

    cancelDeleteBtn.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        closeDeleteRow();
    };
    deleteBtn.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        void deleteProject();
    };

    function updateWidgetValues() {
        const active = currentName();
        if (widget?.options) {
            widget.options.values = [active, ...bins.map(bin => bin.name)]
                .filter((name, index, all) => name && all.indexOf(name) === index);
        }
        if (widget && widget.value !== active) widget.value = active;
    }

    async function refreshBins() {
        let list = [];
        try {
            list = (await fetchProjectBins(
                `/h3_lvm/projects?scope=${encodeURIComponent(scope)}`)).slice();
        } catch (error) {
            if (!signal.aborted) console.warn("[H3 LVM] projects lookup failed:", error);
        }
        if (signal.aborted) return;

        const active = currentName();
        if (!list.some(bin => bin.name === active)) {
            list.unshift({ name: active, [config.field]: 0, cover_url: "", updated_at: "" });
        }
        const changed = JSON.stringify(list) !== JSON.stringify(bins);
        bins = list;
        updateWidgetValues();
        paintCurrent();
        if (modalOpen && !editingName && changed) renderGrid();
    }

    function refresh() {
        if (!inFlight) {
            inFlight = refreshBins().finally(() => { inFlight = null; });
        }
        return inFlight;
    }

    async function setProject(name, closeAfter = false) {
        resetCreateInput();
        closeDeleteRow();
        editingName = "";
        if (widget) {
            widget.value = name;
            widget.callback?.(name);
            node.setDirtyCanvas?.(true, true);
        }
        onChange?.(name);
        await refresh();
        if (closeAfter) closeModal();
    }

    async function chooseProject(name) {
        if (!name) return;
        if (name === currentName()) {
            closeModal();
            return;
        }
        await setProject(name, true);
    }

    async function createProject() {
        const typed = nameInput.value.trim();
        if (!typed) {
            showCreateError("先写个名字。");
            nameInput.focus();
            return;
        }
        createBtn.disabled = true;
        cancelCreateBtn.disabled = true;
        showCreateError("");
        try {
            const res = await api.fetchApi("/h3_lvm/project", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project: typed, scope }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                showCreateError(data.error || `建立失败（HTTP ${res.status}）`);
                return;
            }
            await setProject(data.name || typed, true);
        } catch (error) {
            console.warn("[H3 LVM] create project failed:", error);
            showCreateError("建立失败：连不上后台服务。");
        } finally {
            syncCreateButtons();
        }
    }

    async function commitRename(oldName, value, error, saveButton) {
        const typed = value.trim();
        if (!typed) {
            error.textContent = "先写个名字。";
            return;
        }
        if (typed === oldName) {
            editingName = "";
            renderGrid();
            return;
        }
        saveButton.disabled = true;
        error.textContent = "";
        try {
            const res = await api.fetchApi("/h3_lvm/project/rename", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project: oldName, new_name: typed }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                error.textContent = data.error || `重命名失败（HTTP ${res.status}）`;
                return;
            }
            const newName = data.name || typed;
            const wasCurrent = currentName() === oldName;
            editingName = "";
            if (wasCurrent) await setProject(newName, false);
            else await refresh();
        } catch (err) {
            console.warn("[H3 LVM] rename project failed:", err);
            error.textContent = "重命名失败：连不上后台服务。";
        } finally {
            saveButton.disabled = false;
        }
    }

    function nextProjectAfter(name) {
        const remaining = bins.map(item => item.name).filter(item => item && item !== name);
        if (remaining.includes(DEFAULT_PROJECT)) return DEFAULT_PROJECT;
        return remaining[0] || DEFAULT_PROJECT;
    }

    async function deleteProject() {
        const name = pendingDelete;
        if (!name) return;
        deleteBtn.disabled = true;
        deleteError.textContent = "";
        try {
            const res = await api.fetchApi("/h3_lvm/project/delete", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project: name, confirm: name, scope }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                deleteError.textContent = data.error || `删除失败（HTTP ${res.status}）`;
                return;
            }
            const wasCurrent = currentName() === name;
            pendingDelete = "";
            deleteRow.hidden = true;
            if (wasCurrent) await setProject(nextProjectAfter(name), true);
            else await refresh();
        } catch (error) {
            console.warn("[H3 LVM] delete project failed:", error);
            deleteError.textContent = "删除失败：连不上后台服务。";
        } finally {
            deleteBtn.disabled = false;
        }
    }

    signal.addEventListener("abort", () => {
        overlay.remove();
        if (openMenuClose === closeModal) openMenuClose = null;
    }, { once: true });

    syncSortUi();
    applyColumns();
    syncCreateButtons();
    paintCurrent();
    void refresh();

    return { element: root, refresh, name: currentName, countText: projectCount };
}
