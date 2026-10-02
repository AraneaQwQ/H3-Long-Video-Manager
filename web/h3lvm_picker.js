// Modified by RAFOLIE 2026-09-28: Nodes 2.0 DOM layout and lifecycle.
import { addDeleteButton } from "./delete_button.js";
import { addPanel } from "./dom_panel.js";
/**
 * H3 Long Video Manager — Segment Picker Frontend (Phase B2)
 *
 * Adds a card-based thumbnail gallery to the "H3 Segment Picker" node.
 * - Fetches segment list from /h3_lvm/segments API
 * - Renders cards with thumbnails, frame count, duration
 * - Click card → sets segment_id widget
 * - Refresh button
 * - Zoom controls (+/− 100%~400%)
 * - Optional mp4 preview (click ▶ on card if available)
 *
 * Namespace: H3.LVM.*  (no conflict with clipstream MiniMaxH3.*)
 * CSS prefix: .h3lvm-* (no conflict with clipstream .minimax-clip-*)
 *
 * BULLETPROOF: All UI code is wrapped in try/catch.
 * If the UI fails, the node still works (just without the card gallery).
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// --- Inject CSS ---
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
} catch (e) {
    console.warn("[H3 LVM] CSS injection failed:", e);
}

// --- Register extension ---
app.registerExtension({
    name: "H3.LVM.SegmentPicker",

    async beforeRegisterNodeDef(nodeType, nodeData, appInstance) {
        if (nodeData.name !== "H3 Segment Picker") return;

        // Prevent node from shrinking below usable size
        nodeType.prototype.min_size = [320, 200];

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            this.imgs = null;
            // Enforce minimum size so cards are visible
            if (this.size[0] < 320 || this.size[1] < 200) {
                this.setSize([Math.max(this.size[0], 320), Math.max(this.size[1], 200)]);
            }
            try {
                setupPickerUI(this);
                // Initial size only; workflow configure restores saved user sizing.
                this.setSize([Math.max(this.size[0], 620), Math.max(this.size[1], 460)]);
            } catch (e) {
                console.warn("[H3 LVM] UI setup failed (node still functional):", e);
            }
            return r;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            this.imgs = null;
            this._h3lvmRefresh?.();
            return r;
        };

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const r = onExecuted ? onExecuted.apply(this, arguments) : undefined;
            this.imgs = null;
            this._h3lvmRefresh?.();
            return r;
        };

        // Prevent auto-resize for image previews
        nodeType.prototype.setSizeForImage = function () {};
    }
});

// --- Main UI setup ---
function setupPickerUI(node) {
    const projectWidget = node.widgets?.find(w => w.name === "project_name");
    const segmentWidget = node.widgets?.find(w => w.name === "segment_id");

    // The widget names are internal field names, so the node body would otherwise show
    // English snake_case above a Chinese panel. label is display-only; saved workflows
    // still carry project_name / segment_id, so nothing breaks on load.
    try {
        if (projectWidget) projectWidget.label = "项目素材库";
        if (segmentWidget) segmentWidget.label = "片段编号";
    } catch (e) {
        console.warn("[H3 LVM] widget label translation failed:", e);
    }

    // --- DOM structure ---
    const container = document.createElement("div");
    container.className = "h3lvm-container";

    // Row 1 - which bin to read is the first decision in this workflow, so it gets a
    // full-width labelled row of its own instead of a tag next to a panel title.
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

    projectRow.appendChild(projectLabel);
    projectRow.appendChild(projectSelect);
    projectRow.appendChild(projectCount);
    container.appendChild(projectRow);

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
    createRow.appendChild(nameInput);
    createRow.appendChild(createBtn);
    createRow.appendChild(cancelCreateBtn);
    createRow.appendChild(createError);
    container.appendChild(createRow);

    // Deleting a bin is the mirror of creating one, so it opens in the same place. It
    // takes the whole story with it, so the confirm button repeats the name.
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
    deleteRow.appendChild(deleteText);
    deleteRow.appendChild(deleteBtn);
    deleteRow.appendChild(cancelDeleteBtn);
    deleteRow.appendChild(deleteError);
    container.appendChild(deleteRow);

    // Row 2 - the tools and the current selection, kept quieter than the project row
    // so the cards stay the focus.
    const toolbar = document.createElement("div");
    toolbar.className = "h3lvm-toolbar";

    const refreshBtn = document.createElement("button");
    refreshBtn.className = "h3lvm-refresh-btn";
    refreshBtn.textContent = "🔄 刷新";
    refreshBtn.title = "重新读取当前项目的片段列表";

    const toolSep = document.createElement("span");
    toolSep.className = "h3lvm-tool-sep";

    const toolLabel = document.createElement("span");
    toolLabel.className = "h3lvm-tool-label";
    toolLabel.textContent = "卡片大小";

    const zoomLabel = document.createElement("span");
    zoomLabel.className = "h3lvm-zoom-label";
    zoomLabel.textContent = "100%";

    const btnZoomIn = document.createElement("button");
    btnZoomIn.className = "h3lvm-refresh-btn";
    btnZoomIn.textContent = "+";
    btnZoomIn.title = "放大卡片";

    const btnZoomOut = document.createElement("button");
    btnZoomOut.className = "h3lvm-refresh-btn";
    btnZoomOut.textContent = "−";
    btnZoomOut.title = "缩小卡片";

    const spacer = document.createElement("span");
    spacer.className = "h3lvm-spacer";

    const statusText = document.createElement("span");
    statusText.className = "h3lvm-status";
    statusText.textContent = `当前选中：片段 ${segmentWidget?.value || 1}`;

    toolbar.appendChild(refreshBtn);
    toolbar.appendChild(toolSep);
    toolbar.appendChild(toolLabel);
    toolbar.appendChild(btnZoomOut);
    toolbar.appendChild(zoomLabel);
    toolbar.appendChild(btnZoomIn);
    toolbar.appendChild(spacer);
    toolbar.appendChild(statusText);
    container.appendChild(toolbar);

    // --- Card Zoom State ---
    const ZOOM_STEPS = [1, 1.5, 2, 3, 4]; // 100%, 150%, 200%, 300%, 400%
    let zoomIdx = 0;
    const BASE_CARD_MIN = 130; // px
    const BASE_THUMB_H = 75;   // px

    function applyCardZoom() {
        const z = ZOOM_STEPS[zoomIdx];
        const cardMin = Math.round(BASE_CARD_MIN * z);
        const thumbH = Math.round(BASE_THUMB_H * z);
        container.style.setProperty("--card-min", cardMin + "px");
        container.style.setProperty("--thumb-h", thumbH + "px");
        zoomLabel.textContent = Math.round(z * 100) + "%";
        requestAnimationFrame(fitToContent);
    }

    btnZoomIn.onclick = (e) => {
        e.stopPropagation();
        if (zoomIdx < ZOOM_STEPS.length - 1) { zoomIdx++; applyCardZoom(); }
    };
    btnZoomOut.onclick = (e) => {
        e.stopPropagation();
        if (zoomIdx > 0) { zoomIdx--; applyCardZoom(); }
    };

    // Card deck
    const deck = document.createElement("div");
    deck.className = "h3lvm-deck";
    container.appendChild(deck);

    // Footer - one legend line, nothing the user has to read twice.
    const footer = document.createElement("div");
    footer.className = "h3lvm-footer";
    const hintText = document.createElement("span");
    hintText.className = "h3lvm-hint";
    hintText.textContent = "👉 点卡片＝选片段 · ▶＝预览 · 🗑＝永久删除";
    footer.appendChild(hintText);
    container.appendChild(footer);

    // Add as DOM widget
    const { signal } = addPanel(node, "h3lvm_gallery", container);

    node.imgs = null;

    // Minimum width
    if (node.size[0] < 420) node.setSize([420, node.size[1]]);

    // --- Project menu ---
    // The menu lists every bin on disk with how much it holds; an empty bin is still
    // a valid place to save the next shot.
    const NEW_PROJECT = "__new__";
    const DELETE_PROJECT = "__delete__";
    let projectBins = [];

    async function loadProjects() {
        let bins = [];
        try {
            const res = await api.fetchApi("/h3_lvm/projects", { cache: "no-store" });
            if (res.ok) {
                bins = (await res.json()).projects || [];
            }
        } catch (e) {
            console.warn("[H3 LVM] projects lookup failed:", e);
        }
        if (signal.aborted) return;
        const active = projectWidget?.value || "H3_LVM";
        if (!bins.some(bin => bin.name === active)) {
            bins.unshift({ name: active, segments: 0 });
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
        // Keep the counts so the confirm step can say what is about to be lost.
        projectBins = bins;
    }

    // --- Load segments ---
    let requestId = 0;
    async function loadSegments(deletedId = null) {
        if (signal.aborted) return;
        const currentRequest = ++requestId;
        await loadProjects();
        if (signal.aborted || currentRequest !== requestId) return;
        const project = projectWidget?.value || "H3_LVM";
        statusText.textContent = `当前选中：片段 ${segmentWidget?.value || 1}`;
        projectCount.textContent = "读取中…";

        try {
            const res = await api.fetchApi(`/h3_lvm/segments?project=${encodeURIComponent(project)}`, { cache: "no-store" });
            if (signal.aborted || currentRequest !== requestId) return;
            if (!res.ok) {
                projectCount.textContent = "读取失败";
                deck.innerHTML = `<div class="h3lvm-empty">接口读取失败（HTTP ${res.status}）</div>`;
                return;
            }
            const data = await res.json();
            if (signal.aborted || currentRequest !== requestId) return;
            const segments = data.segments || [];
            projectCount.textContent = segments.length ? `共 ${segments.length} 段` : "空库";
            if (deletedId != null && Number(segmentWidget?.value) === Number(deletedId)) {
                segmentWidget.value = segments[0]?.segment_id || 1;
                statusText.textContent = segments.length ? `当前选中：片段 ${segmentWidget.value}` : "该库暂无片段";
                node.setDirtyCanvas?.(true, true);
            }
            if (segments.length && !segments.some(seg => seg.segment_id === Number(segmentWidget?.value))) {
                statusText.textContent = `片段 ${segmentWidget?.value} 已不存在，请重新选择`;
            }

            if (segments.length === 0) {
                statusText.textContent = "该库暂无片段";
                projectCount.textContent = "空库";
                deck.innerHTML = `<div class="h3lvm-empty">
                    <div>📭 「${project}」还没有已保存片段</div>
                    <div class="h3lvm-empty-hint">先在「H3 Long Video Manager」节点裁切并保存，或用上方菜单新建项目</div>
                </div>`;
                return;
            }

            // Render cards
            deck.innerHTML = "";
            const currentSel = parseInt(segmentWidget?.value || 1);

            for (const seg of segments) {
                const card = document.createElement("div");
                card.className = `h3lvm-card ${seg.segment_id === currentSel ? "active" : ""}`;
                card.dataset.segId = seg.segment_id;

                // Thumbnail
                const thumbWrap = document.createElement("div");
                thumbWrap.className = "h3lvm-thumb-wrap";

                if (seg.thumbnail_url) {
                    const img = document.createElement("img");
                    img.className = "h3lvm-thumb";
                    img.src = seg.thumbnail_url;
                    img.loading = "lazy";
                    thumbWrap.appendChild(img);
                } else {
                    thumbWrap.innerHTML = `<div class="h3lvm-thumb-placeholder">🎬</div>`;
                }

                // Active badge
                if (seg.segment_id === currentSel) {
                    const badge = document.createElement("div");
                    badge.className = "h3lvm-active-badge";
                    badge.textContent = "已选中";
                    thumbWrap.appendChild(badge);
                }

                // MP4 play button
                if (seg.has_mp4 && seg.mp4_url) {
                    const playBtn = document.createElement("button");
                    playBtn.className = "h3lvm-play-btn";
                    playBtn.textContent = "▶";
                    playBtn.title = "预览视频";
                    playBtn.onclick = (e) => {
                        e.stopPropagation();
                        openPreview(seg, project);
                    };
                    thumbWrap.appendChild(playBtn);
                }

                card.appendChild(thumbWrap);

                // Meta
                const meta = document.createElement("div");
                meta.className = "h3lvm-meta";
                const dur = seg.duration_sec != null ? `${seg.duration_sec.toFixed(1)} 秒` : "";
                const res = `${seg.width}×${seg.height}`;
                meta.innerHTML = `
                    <div class="h3lvm-seg-label">片段 ${seg.segment_id}</div>
                    <div class="h3lvm-seg-info">${seg.frames} 帧 · ${dur} · ${res}</div>
                `;
                addDeleteButton(meta, {
                    description: `项目「${project}」的片段 ${seg.segment_id}`,
                    signal,
                    onDelete: async () => {
                        document.getElementById("h3lvm-preview-overlay")?._h3Close?.();
                        const response = await api.fetchApi("/h3_lvm/delete", {
                            method: "POST", headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ project, segment_id: seg.segment_id }),
                        });
                        if (!response.ok) {
                            const error = await response.json().catch(() => ({}));
                            throw new Error(error.error || `删除失败 (${response.status})；请确认已重启 ComfyUI。`);
                        }
                        if (!signal.aborted && (projectWidget?.value || "H3_LVM") === project) {
                            await loadSegments(seg.segment_id);
                        }
                    },
                });
                card.appendChild(meta);

                // Click to select
                card.onclick = () => {
                    if (segmentWidget) {
                        segmentWidget.value = seg.segment_id;
                        segmentWidget.callback?.(seg.segment_id);
                    }
                    deck.querySelectorAll(".h3lvm-card").forEach(c => c.classList.remove("active"));
                    deck.querySelectorAll(".h3lvm-active-badge").forEach(b => b.remove());
                    card.classList.add("active");
                    const badge = document.createElement("div");
                    badge.className = "h3lvm-active-badge";
                    badge.textContent = "已选中";
                    card.querySelector(".h3lvm-thumb-wrap").appendChild(badge);
                    statusText.textContent = `当前选中：片段 ${seg.segment_id}`;
                };

                deck.appendChild(card);
            }

            // Fit node height
            fitToContent();

        } catch (e) {
            if (signal.aborted || currentRequest !== requestId) return;
            console.warn("[H3 LVM] Failed to load segments:", e);
            projectCount.textContent = "读取失败";
            deck.innerHTML = `<div class="h3lvm-empty">读取失败：${e.message}</div>`;
        }
    }

    // --- Fit node to content ---
    function fitToContent() {
        // Layout is owned by ComfyUI; refreshing cards must not shrink the node.
        node.setDirtyCanvas?.(true, true);
    }

    // --- MP4 Preview Modal ---
    function openPreview(seg, project) {
        const existing = document.getElementById("h3lvm-preview-overlay");
        if (existing) existing._h3Close?.();

        const overlay = document.createElement("div");
        overlay.id = "h3lvm-preview-overlay";
        overlay.className = "h3lvm-overlay";

        const modal = document.createElement("div");
        modal.className = "h3lvm-modal";

        const video = document.createElement("video");
        video.src = seg.mp4_url;
        video.controls = true;
        video.autoplay = true;
        video.playsInline = true;
        video.className = "h3lvm-preview-video";

        const info = document.createElement("div");
        info.className = "h3lvm-preview-info";
        info.textContent = `片段 ${seg.segment_id} · ${seg.frames} 帧 · ${seg.duration_sec?.toFixed(1)} 秒 · ${seg.width}×${seg.height}`;

        const closeBtn = document.createElement("button");
        closeBtn.className = "h3lvm-modal-close";
        closeBtn.textContent = "✕ 关闭";

        modal.appendChild(video);
        modal.appendChild(info);
        modal.appendChild(closeBtn);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        function close() {
            video.pause();
            video.removeAttribute("src");
            video.load();
            overlay.remove();
            window.removeEventListener("keydown", onKey);
            signal.removeEventListener("abort", close);
        }
        overlay._h3Close = close;
        signal.addEventListener("abort", close, { once: true });
        function onKey(e) { if (e.key === "Escape") close(); }
        closeBtn.onclick = close;
        overlay.onclick = (e) => { if (e.target === overlay) close(); };
        window.addEventListener("keydown", onKey);
    }

    // --- Wire up events ---
    refreshBtn.onclick = () => loadSegments();

    // Switching bins goes through the widget so the graph and the deck stay in step.
    function setProject(name) {
        closeCreateRow();
        closeDeleteRow();
        if (!projectWidget) {
            loadSegments();
            return;
        }
        projectWidget.value = name;
        projectWidget.callback?.(name);
        node.setDirtyCanvas?.(true, true);
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
            closeCreateRow();
            setProject(data.name || typed);
        } catch (e) {
            console.warn("[H3 LVM] create project failed:", e);
            createError.textContent = "建立失败：连不上后台服务。";
        } finally {
            createBtn.disabled = false;
        }
    }

    projectSelect.onchange = () => {
        const chosen = projectSelect.value;
        if (chosen === NEW_PROJECT) {
            projectSelect.value = projectWidget?.value || "H3_LVM";
            openCreateRow();
            return;
        }
        if (chosen === DELETE_PROJECT) {
            projectSelect.value = projectWidget?.value || "H3_LVM";
            openDeleteRow();
            return;
        }
        if (chosen && chosen !== (projectWidget?.value || "")) setProject(chosen);
    };
    createBtn.onclick = (e) => {
        e.stopPropagation();
        createProject();
    };
    cancelCreateBtn.onclick = (e) => {
        e.stopPropagation();
        closeCreateRow();
    };
    nameInput.onkeydown = (e) => {
        e.stopPropagation();
        if (e.key === "Enter") createProject();
        if (e.key === "Escape") closeCreateRow();
    };

    function openDeleteRow() {
        const name = projectWidget?.value || "H3_LVM";
        const bin = projectBins.find(item => item.name === name) || { segments: 0 };
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
        const remaining = projectBins.map(item => item.name).filter(item => item && item !== name);
        if (remaining.includes("H3_LVM")) return "H3_LVM";
        return remaining[0] || "H3_LVM";
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
            closeDeleteRow();
            setProject(nextProjectAfter(name));
        } catch (e) {
            console.warn("[H3 LVM] delete project failed:", e);
            deleteError.textContent = "删除失败：连不上后台服务。";
        } finally {
            deleteBtn.disabled = false;
        }
    }

    deleteBtn.onclick = (e) => {
        e.stopPropagation();
        deleteProject();
    };
    cancelDeleteBtn.onclick = (e) => {
        e.stopPropagation();
        closeDeleteRow();
    };

    // Reload when project name changes
    if (projectWidget) {
        const origCallback = projectWidget.callback;
        projectWidget.callback = (val) => {
            origCallback?.call(projectWidget, val);
            loadSegments();
        };
    }

    if (segmentWidget) {
        const original = segmentWidget.callback;
        segmentWidget.callback = function () {
            const result = original?.apply(this, arguments);
            loadSegments();
            return result;
        };
    }

    const onDeleted = event => {
        if (event.detail?.project === (projectWidget?.value || "H3_LVM")) {
            loadSegments(event.detail.deleted_id);
        }
    };
    api.addEventListener("h3_lvm/changed", onDeleted);
    signal.addEventListener("abort", () => api.removeEventListener("h3_lvm/changed", onDeleted), { once: true });
    node._h3lvmRefresh = loadSegments;
    signal.addEventListener("abort", () => { delete node._h3lvmRefresh; }, { once: true });
    const onExecuted = () => loadSegments();
    api.addEventListener("execution_success", onExecuted);
    signal.addEventListener("abort", () => api.removeEventListener("execution_success", onExecuted), { once: true });
    loadSegments();
}
