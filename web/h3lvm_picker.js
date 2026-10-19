// Modified by RAFOLIE 2026-09-28: Nodes 2.0 DOM layout and lifecycle.
// Modified by RAFOLIE 2026-10-19: one node, two libraries. The panel has two mode
// buttons: 裁切片段 (the original cut-segment library, unchanged behaviour) and
// 投放视频 (whole videos the user brings in, stored as they are). The graph truth is
// still project_name / segment_id / source_mode; node.properties only carries the
// *other* mode's project and selection so switching back restores it.
//
// Adds a card-based thumbnail gallery to the "H3 Segment Picker" node.
// - Cut mode: /h3_lvm/segments cards, click to set segment_id, preview, delete
// - Upload mode: /h3_lvm/uploads cards, drag-and-drop or file-picker import, cover,
//   original file name, duration, resolution, source fps -> 24fps note, audio
// - Refresh, zoom (100%-400%), preview modal, delete - shared by both modes
//
// Namespace: H3.LVM.*  (no conflict with clipstream MiniMaxH3.*)
// CSS prefix: .h3lvm-* (no conflict with clipstream .minimax-clip-*)
//
// BULLETPROOF: All UI code is wrapped in try/catch.
// If the UI fails, the node still works (just without the card gallery).

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addDeleteButton } from "./delete_button.js";
import { createCardZoom } from "./card_zoom.js";
import { addPanel } from "./dom_panel.js";
import { openPreview } from "./preview_overlay.js";
import { createProjectMenu } from "./project_menu.js";
import { appendThumbnail } from "./thumb_fit.js";
import {
    DEFAULT_PROJECT,
    MODE_LABELS,
    MODE_ORDER,
    MODE_SEGMENTS,
    MODE_UPLOADS,
    browserPreviewHint,
    canBrowserPreview,
    entryForMode,
    formatDuration,
    modeFromValue,
    moveIds,
    readModeState,
    renumberedId,
    saveModeState,
    seedState,
    uploadInfoLines,
    writeModeState,
} from "./picker_mode_state.js";
// Where a dragged card would land is the same geometry the reference loaders
// already use: a pure function over card rects, so it is shared, not copied.
import { insertPosition } from "./ref_state.js";

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
    const modeWidget = node.widgets?.find(w => w.name === "source_mode");
    const sizeWidget = node.widgets?.find(w => w.name === "output_size");
    const customSizeWidget = node.widgets?.find(w => w.name === "custom_max_side");

    // The widget names are internal field names, so the node body would otherwise show
    // English snake_case above a Chinese panel. label is display-only; saved workflows
    // still carry project_name / segment_id / source_mode, so nothing breaks on load.
    try {
        if (projectWidget) projectWidget.label = "项目素材库";
        if (segmentWidget) segmentWidget.label = "片段编号";
        if (modeWidget) {
            modeWidget.label = "素材来源模式";
            modeWidget.title = "面板顶部两个按钮写的就是这个值：它决定节点读哪一个库";
        }
        if (sizeWidget) {
            sizeWidget.label = "输出分辨率";
            sizeWidget.title = "只作用于投放视频：执行时把画面等比缩小到该最长边，磁盘上的原文件不变。"
                + "4K/2K 素材建议选 1920 或 1280，交给 MiniMax 的压力会小很多；选「自定义」时用下面的「自定义最长边」填像素数。";
        }
        if (customSizeWidget) {
            customSizeWidget.title = "只在「输出分辨率」选择自定义时生效：解码时把画面等比缩小到这个最长边（像素）。"
                + "等比缩放、对齐偶数、不会放大，磁盘上的原文件不变。";
        }
    } catch (e) {
        console.warn("[H3 LVM] widget label translation failed:", e);
    }

    // --- DOM structure ---
    const container = document.createElement("div");
    container.className = "h3lvm-container";

    // Row 0 - which library this node reads. An empty card list is almost always the
    // wrong mode rather than a missing file, so this row is always visible and the
    // current mode is always lit.
    const modeRow = document.createElement("div");
    modeRow.className = "h3lvm-mode-row";
    const modeButtons = new Map();
    for (const mode of MODE_ORDER) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "h3lvm-mode-btn";
        button.dataset.mode = mode;
        button.textContent = MODE_LABELS[mode].button;
        button.title = MODE_LABELS[mode].title;
        button.addEventListener("click", (event) => {
            event.stopPropagation();
            switchMode(mode);
        });
        modeButtons.set(mode, button);
        modeRow.appendChild(button);
    }
    const modeHint = document.createElement("span");
    modeHint.className = "h3lvm-mode-hint";
    modeRow.appendChild(modeHint);
    container.appendChild(modeRow);

    // Row 1 - the project menu is shared with the Manager panel so both nodes look
    // and behave the same. It is rebuilt when the mode changes because it reads,
    // creates and deletes a different library, and it owns an AbortController so a
    // switch cannot leave a second menu or a second set of listeners behind.
    const menuSlot = document.createElement("div");
    menuSlot.className = "h3lvm-menu-slot";
    container.appendChild(menuSlot);
    let menu = null;
    let menuLifetime = null;
    let projectCount = null;
    // Row 2 - the tools and the current selection, kept quieter than the rows above
    // so the cards stay the focus.
    const toolbar = document.createElement("div");
    toolbar.className = "h3lvm-toolbar";

    const refreshBtn = document.createElement("button");
    refreshBtn.className = "h3lvm-refresh-btn";
    refreshBtn.textContent = "🔄 刷新";
    refreshBtn.title = "重新读取当前项目的片段列表";

    const uploadBtn = document.createElement("button");
    uploadBtn.className = "h3lvm-refresh-btn h3lvm-upload-btn";
    uploadBtn.textContent = "＋ 载入视频";
    uploadBtn.title = "选择视频文件导入当前项目；导入不需要运行工作流";
    uploadBtn.hidden = true;

    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.multiple = true;
    // The accept list is only a hint for the browser dialog; the backend still probes
    // every file, so a renamed non-video is rejected instead of becoming a card.
    fileInput.accept = "video/*,.mp4,.mov,.mkv,.webm,.avi";
    fileInput.className = "h3lvm-file-input";
    container.appendChild(fileInput);

    const spacer = document.createElement("span");
    spacer.className = "h3lvm-spacer";

    const statusText = document.createElement("span");
    statusText.className = "h3lvm-status";
    statusText.textContent = `当前选中：片段 ${segmentWidget?.value || 1}`;

    toolbar.appendChild(refreshBtn);
    toolbar.appendChild(uploadBtn);
    createCardZoom({ container, node }).mount(toolbar);
    toolbar.appendChild(spacer);
    toolbar.appendChild(statusText);
    container.appendChild(toolbar);

    // Card deck
    const deck = document.createElement("div");
    deck.className = "h3lvm-deck";
    container.appendChild(deck);

    // Footer - one legend line, nothing the user has to read twice.
    const footer = document.createElement("div");
    footer.className = "h3lvm-footer";
    const hintText = document.createElement("span");
    hintText.className = "h3lvm-hint";
    footer.appendChild(hintText);
    container.appendChild(footer);

    // Add as DOM widget
    const { signal } = addPanel(node, "h3lvm_gallery", container);
    signal.addEventListener("abort", () => menuLifetime?.abort(), { once: true });

    node.imgs = null;

    // Minimum width
    if (node.size[0] < 420) node.setSize([420, node.size[1]]);

    // --- Two modes, one set of real widgets ---
    // project_name / segment_id always describe the mode the node will run with, so a
    // saved workflow needs no new fields. node.properties holds the other mode's pair,
    // which is UI recovery information, not a second source of truth.
    let modeState = readModeState(node.properties);
    let builtMode = null;
    let generation = 0;
    let importing = false;
    // A reorder reloads the deck itself, so the matching event must not reload it twice.
    let reordering = false;

    function graphMode() {
        return modeFromValue(modeWidget?.value);
    }

    function currentProject() {
        return projectWidget?.value || DEFAULT_PROJECT;
    }

    // The card labels have to match what the node will decode, so the panel sends this
    // value to the API and lets the server plan the size. An old workflow has no such
    // widget, and "" means the same thing there as on the backend: decode as-is.
    function currentOutputSize() {
        return sizeWidget?.value ?? "";
    }

    // Only read by the server when the combo says 自定义, so an old workflow without this
    // widget behaves exactly as before.
    function currentCustomMaxSide() {
        return customSizeWidget?.value ?? "";
    }

    // The number only means something while the combo points at 自定义, so the label states
    // whether it is live rather than hiding a field the user may be mid-way through typing.
    function syncCustomSizeLabel() {
        if (!customSizeWidget) return;
        if (builtMode !== MODE_UPLOADS) {
            customSizeWidget.label = "自定义最长边（裁切不用）";
        } else if (String(currentOutputSize()).indexOf("自定义") >= 0) {
            customSizeWidget.label = "自定义最长边（生效中）";
        } else {
            customSizeWidget.label = "自定义最长边（选自定义后可用）";
        }
    }

    function persist() {
        modeState = saveModeState(modeState, builtMode ?? graphMode(), {
            project_name: projectWidget?.value,
            segment_id: segmentWidget?.value,
        });
        writeModeState(node.properties, modeState);
    }

    // Wire the panel for one mode: its own project menu, its own copy, its own tools.
    function buildForMode(mode) {
        menuLifetime?.abort();
        menuLifetime = new AbortController();
        menuSlot.innerHTML = "";
        menu = createProjectMenu({
            node,
            widget: projectWidget,
            signal: menuLifetime.signal,
            scope: mode,
        });
        projectCount = menu.countText;
        menuSlot.appendChild(menu.element);

        builtMode = mode;
        for (const [id, button] of modeButtons) {
            button.classList.toggle("active", id === mode);
            button.setAttribute("aria-pressed", id === mode ? "true" : "false");
        }
        modeHint.textContent = MODE_LABELS[mode].hint;
        hintText.textContent = MODE_LABELS[mode].footer;
        uploadBtn.hidden = mode !== MODE_UPLOADS;
        deck.classList.toggle("h3lvm-drop-zone", mode === MODE_UPLOADS);
        refreshBtn.title = mode === MODE_UPLOADS
            ? "重新读取当前项目的投放视频列表"
            : "重新读取当前项目的片段列表";
        if (projectWidget) projectWidget.label = mode === MODE_UPLOADS ? "项目视频库" : "项目素材库";
        if (segmentWidget) segmentWidget.label = mode === MODE_UPLOADS ? "视频编号" : "片段编号";
        // The control only ever applies to the upload library; saying so on the widget is
        // clearer than hiding it, because hiding would also make it look broken.
        if (sizeWidget) sizeWidget.label = mode === MODE_UPLOADS ? "输出分辨率" : "输出分辨率（裁切不用）";
        syncCustomSizeLabel();
    }
    function switchMode(next) {
        const target = modeFromValue(next);
        if (target === builtMode && target === graphMode()) {
            void loadDeck();
            return;
        }
        // Leave the current mode: keep what is on screen, then restore the target.
        persist();
        if (modeWidget) modeWidget.value = target; // graph truth; no callback, no loop
        const entry = entryForMode(modeState, target);
        if (projectWidget) projectWidget.value = entry.project_name;
        if (segmentWidget) segmentWidget.value = entry.segment_id;
        buildForMode(target);
        persist();
        node.setDirtyCanvas?.(true, true);
        void loadDeck();
    }

    // A loaded workflow is the truth for the current mode. An old workflow has no
    // source_mode and no stored state, and must open exactly as it did before - the
    // other mode's defaults never overwrite it.
    function syncFromGraph() {
        const wanted = graphMode();
        if (wanted !== builtMode) buildForMode(wanted);
        modeState = seedState(modeState, wanted, {
            project_name: projectWidget?.value,
            segment_id: segmentWidget?.value,
        });
        writeModeState(node.properties, modeState);
    }

    // Every request is bound to mode + project + generation, so a late reply from the
    // previous mode cannot paint over the current one.
    function isStale(request, mode, project) {
        return signal.aborted || request !== generation || builtMode !== mode
            || currentProject() !== project;
    }

    // --- Load the current mode's cards ---
    async function loadDeck(deletedId = null) {
        if (signal.aborted) return;
        const request = ++generation;
        const mode = builtMode;
        await menu.refresh();
        if (isStale(request, mode, currentProject())) return;
        const project = currentProject();
        if (mode === MODE_UPLOADS) {
            await loadUploads(request, mode, project, deletedId);
        } else {
            await loadSegments(request, mode, project, deletedId);
        }
    }

    // --- Cut segments (the original behaviour) ---
    async function loadSegments(request, mode, project, deletedId = null) {
        statusText.textContent = `当前选中：片段 ${segmentWidget?.value || 1}`;
        projectCount.textContent = "读取中…";

        try {
            const res = await api.fetchApi(`/h3_lvm/segments?project=${encodeURIComponent(project)}`, { cache: "no-store" });
            if (isStale(request, mode, project)) return;
            if (!res.ok) {
                projectCount.textContent = "读取失败";
                deck.innerHTML = `<div class="h3lvm-empty">接口读取失败（HTTP ${res.status}）</div>`;
                return;
            }
            const data = await res.json();
            if (isStale(request, mode, project)) return;
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
                    <div>📭 「${project}」${MODE_LABELS[MODE_SEGMENTS].emptyTitle}</div>
                    <div class="h3lvm-empty-hint">${MODE_LABELS[MODE_SEGMENTS].emptyHint}</div>
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

                appendThumbnail(thumbWrap, seg);

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
                        openPreview(seg, signal);
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
                        if (!signal.aborted && builtMode === MODE_SEGMENTS && currentProject() === project) {
                            await loadDeck(seg.segment_id);
                        }
                    },
                });
                card.appendChild(meta);

                // Click to select
                card.onclick = () => selectCard(card, seg.segment_id, "片段");

                deck.appendChild(card);
            }

            // Fit node height
            fitToContent();

        } catch (e) {
            if (isStale(request, mode, project)) return;
            console.warn("[H3 LVM] Failed to load segments:", e);
            projectCount.textContent = "读取失败";
            deck.innerHTML = `<div class="h3lvm-empty">读取失败：${e.message}</div>`;
        }
    }
    // --- Uploaded videos (the second library) ---
    async function loadUploads(request, mode, project, deletedId = null) {
        statusText.textContent = `当前选中：视频 ${segmentWidget?.value || 1}`;
        projectCount.textContent = "读取中…";

        try {
            const url = `/h3_lvm/uploads?project=${encodeURIComponent(project)}`
                + `&output_size=${encodeURIComponent(currentOutputSize())}`
                + `&custom_max_side=${encodeURIComponent(currentCustomMaxSide())}`;
            const res = await api.fetchApi(url, { cache: "no-store" });
            if (isStale(request, mode, project)) return;
            if (!res.ok) {
                projectCount.textContent = "读取失败";
                deck.innerHTML = `<div class="h3lvm-empty">接口读取失败（HTTP ${res.status}）；请确认已重启 ComfyUI。</div>`;
                return;
            }
            const data = await res.json();
            if (isStale(request, mode, project)) return;
            const videos = Array.isArray(data.videos) ? data.videos : [];
            projectCount.textContent = videos.length ? `共 ${videos.length} 个视频` : "空视频库";

            if (deletedId != null && Number(segmentWidget?.value) === Number(deletedId)) {
                segmentWidget.value = videos[0]?.segment_id || 1;
                statusText.textContent = videos.length ? `当前选中：视频 ${segmentWidget.value}` : "该视频库暂无视频";
                node.setDirtyCanvas?.(true, true);
            }
            if (videos.length && !videos.some(v => Number(v.segment_id) === Number(segmentWidget?.value))) {
                statusText.textContent = `视频 ${segmentWidget?.value} 已不存在，请重新选择`;
            }

            if (videos.length === 0) {
                statusText.textContent = "该视频库暂无视频";
                projectCount.textContent = "空视频库";
                deck.innerHTML = `<div class="h3lvm-empty">
                    <div>📥 ${MODE_LABELS[MODE_UPLOADS].emptyTitle}</div>
                    <div class="h3lvm-empty-hint">「${project}」是空的。${MODE_LABELS[MODE_UPLOADS].emptyHint}</div>
                </div>`;
                return;
            }

            deck.innerHTML = "";
            const currentSel = parseInt(segmentWidget?.value || 1);
            videos.forEach((video, index) => {
                renderUploadCard(video, project, currentSel, index);
            });
            fitToContent();

        } catch (e) {
            if (isStale(request, mode, project)) return;
            console.warn("[H3 LVM] Failed to load uploaded videos:", e);
            projectCount.textContent = "读取失败";
            deck.innerHTML = `<div class="h3lvm-empty">读取失败：${e.message}</div>`;
        }
    }

    function renderUploadCard(video, project, currentSel, orderIndex) {
        const card = document.createElement("div");
        card.className = `h3lvm-card ${Number(video.segment_id) === currentSel ? "active" : ""}`;
        card.dataset.uploadId = String(video.segment_id);
        // The deck order is the library order, and the card is draggable because that
        // order is what the user is arranging: the first card is the one numbered 1.
        card.draggable = true;
        card.dataset.orderIndex = String(orderIndex);

        const thumbWrap = document.createElement("div");
        thumbWrap.className = "h3lvm-thumb-wrap";
        // The thumbnail renderer only needs a url and the frame size, so the upload
        // record is mapped onto that shape instead of forking the portrait handling.
        appendThumbnail(thumbWrap, {
            thumbnail_url: video.cover_url,
            width: video.width,
            height: video.height,
        });

        if (Number(video.segment_id) === currentSel) {
            const badge = document.createElement("div");
            badge.className = "h3lvm-active-badge";
            badge.textContent = "已选中";
            thumbWrap.appendChild(badge);
        }
        if (video.missing_file) {
            const missing = document.createElement("div");
            missing.className = "h3lvm-missing-badge";
            missing.textContent = "文件已丢失";
            missing.title = "索引里还有这张卡片，但磁盘上的视频文件不见了。删除卡片或重新导入。";
            thumbWrap.appendChild(missing);
        }

        const playBtn = document.createElement("button");
        playBtn.className = "h3lvm-play-btn";
        playBtn.textContent = "▶";
        playBtn.title = canBrowserPreview(video) ? "在浏览器里预览原视频" : "这个封装浏览器不能直接播放";
        playBtn.onclick = (e) => {
            e.stopPropagation();
            if (!canBrowserPreview(video)) {
                window.alert(browserPreviewHint(video));
                return;
            }
            openPreview({ ...video, mp4_url: video.video_url }, signal, uploadPreviewText(video));
        };
        thumbWrap.appendChild(playBtn);
        card.appendChild(thumbWrap);

        const meta = document.createElement("div");
        meta.className = "h3lvm-meta";
        const label = document.createElement("div");
        label.className = "h3lvm-seg-label";
        label.textContent = `视频 ${video.segment_id}`;
        const name = document.createElement("div");
        name.className = "h3lvm-seg-name";
        name.textContent = video.original_name || video.storage_name || "(无文件名)";
        name.title = name.textContent;
        meta.append(label, name);
        for (const line of uploadInfoLines(video)) {
            const info = document.createElement("div");
            info.className = "h3lvm-seg-info";
            info.textContent = line;
            meta.appendChild(info);
        }
        addDeleteButton(meta, {
            description: `投放视频库「${project}」的视频 ${video.segment_id}（${video.original_name || video.storage_name}）`,
            signal,
            onDelete: async () => {
                document.getElementById("h3lvm-preview-overlay")?._h3Close?.();
                const response = await api.fetchApi("/h3_lvm/uploads/delete", {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ project, segment_id: video.segment_id }),
                });
                if (!response.ok) {
                    const error = await response.json().catch(() => ({}));
                    throw new Error(error.error || `删除失败 (${response.status})；请确认已重启 ComfyUI。`);
                }
                if (!signal.aborted && builtMode === MODE_UPLOADS && currentProject() === project) {
                    await loadDeck(video.segment_id);
                }
            },
        });
        card.appendChild(meta);

        card.onclick = () => selectCard(card, Number(video.segment_id), "视频");
        deck.appendChild(card);
    }

    function uploadPreviewText(video) {
        return `视频 ${video.segment_id} · ${video.original_name || video.storage_name || ""} · `
            + `${formatDuration(video.duration_sec)} · ${video.width}×${video.height}`;
    }

    // One selection path for both modes: the clicked card becomes the node's
    // segment_id, and the stored state follows the mode that is on screen.
    function selectCard(card, assetId, noun) {
        if (segmentWidget) {
            segmentWidget.value = assetId;
            segmentWidget.callback?.(assetId);
        }
        deck.querySelectorAll(".h3lvm-card").forEach(c => c.classList.remove("active"));
        deck.querySelectorAll(".h3lvm-active-badge").forEach(b => b.remove());
        card.classList.add("active");
        const badge = document.createElement("div");
        badge.className = "h3lvm-active-badge";
        badge.textContent = "已选中";
        card.querySelector(".h3lvm-thumb-wrap")?.appendChild(badge);
        statusText.textContent = `当前选中：${noun} ${assetId}`;
        persist();
    }

    // --- Fit node to content ---
    function fitToContent() {
        // Layout is owned by ComfyUI; refreshing cards must not shrink the node.
        node.setDirtyCanvas?.(true, true);
    }
    // --- Import videos (upload mode only) ---
    // One file at a time so a failure names the file. A card only appears once the
    // server has probed the bytes, so a failed upload leaves nothing behind and can be
    // retried by picking the file again.
    async function importFiles(fileList) {
        const files = Array.from(fileList ?? []);
        if (!files.length || signal.aborted) return;
        const project = currentProject();
        importing = true;
        uploadBtn.disabled = true;
        let done = 0;
        const failed = [];
        for (const file of files) {
            if (signal.aborted) break;
            statusText.textContent = `上传中（${done + failed.length + 1}/${files.length}）：${file.name}`;
            try {
                const form = new FormData();
                // Order matters: the server reads the "project" field before the file.
                form.append("project", project);
                form.append("file", file, file.name);
                const res = await api.fetchApi("/h3_lvm/uploads/import", { method: "POST", body: form });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.error || `上传失败（HTTP ${res.status}）`);
                done++;
            } catch (error) {
                failed.push(`${file.name}：${error.message || "上传失败"}`);
            }
        }
        uploadBtn.disabled = false;
        importing = false;
        if (signal.aborted) return;
        if (failed.length) {
            statusText.textContent = `已导入 ${done} 个，失败 ${failed.length} 个：${failed[0]}`;
        } else {
            statusText.textContent = done ? `已导入 ${done} 个视频` : "没有导入任何视频";
        }
        if (builtMode === MODE_UPLOADS && currentProject() === project) {
            await loadDeck();
        }
    }

    // --- Wire up events ---
    refreshBtn.onclick = () => loadDeck();
    uploadBtn.onclick = (event) => {
        event.stopPropagation();
        fileInput.click();
    };
    fileInput.onchange = () => {
        const files = Array.from(fileInput.files ?? []);
        fileInput.value = "";
        void importFiles(files);
    };

    // --- Two different things can be dragged over this panel ---
    //   1. a file from outside ComfyUI -> upload it and append a card (upload mode only)
    //   2. one of our own cards        -> change the order of the video library
    // They are told apart by the drag payload: an external file drag always reports
    // "Files", a card drag carries our own mime type instead. ComfyUI also listens for
    // file drops on the document and would create a node from the same file, so both
    // handlers stop here.
    //
    // A card drag is accepted anywhere in the panel and the landing spot comes from
    // insertPosition() over every card rect, not from the card under the pointer: a gap
    // between two cards, a pointer over the toolbar, or a few pixels outside the grid all
    // still mean something. Aiming only at the card under the pointer is what made the
    // reference loaders feel broken, so the picker does not repeat it.
    const CARD_MIME = "application/x-h3lvm-card";
    const SCROLL_EDGE = 28;
    let dragIndex = -1;
    let heldIndex = -1;
    let pointerY = 0;
    let scrollFrame = 0;

    function dragTypes(event) {
        return Array.from(event.dataTransfer?.types ?? []);
    }

    function isFileDrag(event) {
        return dragTypes(event).includes("Files");
    }

    function insideDeck(event) {
        const rect = deck.getBoundingClientRect();
        return event.clientX >= rect.left && event.clientX <= rect.right
            && event.clientY >= rect.top && event.clientY <= rect.bottom;
    }

    function acceptsFileDrop(event) {
        return builtMode === MODE_UPLOADS
            && isFileDrag(event)
            && insideDeck(event);
    }

    function cardRects() {
        const rects = [];
        for (const card of deck.querySelectorAll(".h3lvm-card[data-order-index]")) {
            const rect = card.getBoundingClientRect();
            rects.push({
                index: Number(card.dataset.orderIndex),
                left: rect.left,
                top: rect.top,
                right: rect.right,
                bottom: rect.bottom,
            });
        }
        return rects;
    }

    // The position in the deck as it is drawn now, or -1 when this drop changes nothing.
    function insertAt(event, from) {
        return insertPosition(cardRects(), event.clientX, event.clientY, from);
    }

    function clearOrderHints() {
        deck.classList.remove("h3lvm-order-drop");
        for (const card of deck.querySelectorAll(".h3lvm-drop-before, .h3lvm-drop-after")) {
            card.classList.remove("h3lvm-drop-before", "h3lvm-drop-after");
        }
    }

    function showInsertHint(at) {
        clearOrderHints();
        if (at < 0) return;
        const last = deck.querySelectorAll(".h3lvm-card[data-order-index]").length - 1;
        if (at > last) {
            deck.querySelector(`.h3lvm-card[data-order-index="${last}"]`)?.classList.add("h3lvm-drop-after");
            return;
        }
        deck.querySelector(`.h3lvm-card[data-order-index="${at}"]`)?.classList.add("h3lvm-drop-before");
    }

    // The deck scrolls, so a row that is out of view has to stay reachable while the
    // pointer is held near its top or bottom edge.
    function startAutoScroll() {
        if (scrollFrame) return;
        const step = () => {
            scrollFrame = requestAnimationFrame(step);
            if (dragIndex < 0 || !pointerY) return;
            const rect = deck.getBoundingClientRect();
            if (pointerY < rect.top + SCROLL_EDGE) deck.scrollTop -= 12;
            else if (pointerY > rect.bottom - SCROLL_EDGE) deck.scrollTop += 12;
        };
        scrollFrame = requestAnimationFrame(step);
    }

    function stopAutoScroll() {
        if (!scrollFrame) return;
        cancelAnimationFrame(scrollFrame);
        scrollFrame = 0;
        pointerY = 0;
    }

    function heldCard(event) {
        const card = event.target?.closest?.(".h3lvm-card[data-order-index]");
        return card && deck.contains(card) ? card : null;
    }
    // Insurance: a drag can start on a child that swallows dragstart. The pointerdown
    // that began it already knows which card is held.
    container.addEventListener("pointerdown", (event) => {
        const card = heldCard(event);
        heldIndex = card ? Number(card.dataset.orderIndex) : -1;
    }, { signal });

    container.addEventListener("dragstart", (event) => {
        const card = heldCard(event);
        if (!card || builtMode !== MODE_UPLOADS) return;
        dragIndex = Number(card.dataset.orderIndex);
        if (!Number.isInteger(dragIndex) || dragIndex < 0) return;
        heldIndex = dragIndex;
        event.dataTransfer.setData(CARD_MIME, String(dragIndex));
        event.dataTransfer.setData("text/plain", String(dragIndex));
        event.dataTransfer.effectAllowed = "move";
        card.classList.add("h3lvm-dragging");
        startAutoScroll();
    }, { signal });

    container.addEventListener("dragover", (event) => {
        if (isFileDrag(event)) {
            if (!acceptsFileDrop(event)) return;
            event.preventDefault();
            event.stopPropagation();
            event.dataTransfer.dropEffect = "copy";
            deck.classList.add("h3lvm-drop-in");
            return;
        }
        if (builtMode !== MODE_UPLOADS) return;
        if (dragIndex < 0 && dragTypes(event).includes(CARD_MIME)) dragIndex = heldIndex;
        if (dragIndex < 0) return;
        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = "move";
        pointerY = event.clientY;
        const at = insertAt(event, dragIndex);
        // Aiming at the dragged card's own slot is not a move, so it gets no hint.
        showInsertHint(at === dragIndex || at === dragIndex + 1 ? -1 : at);
    }, { signal });

    container.addEventListener("dragleave", (event) => {
        if (container.contains(event.relatedTarget)) return;
        deck.classList.remove("h3lvm-drop-in");
        clearOrderHints();
    }, { signal });

    container.addEventListener("drop", (event) => {
        if (isFileDrag(event)) {
            if (!acceptsFileDrop(event)) return;
            event.preventDefault();
            event.stopPropagation();
            deck.classList.remove("h3lvm-drop-in");
            void importFiles(event.dataTransfer?.files);
            return;
        }
        if (builtMode !== MODE_UPLOADS) return;
        if (dragIndex < 0 && dragTypes(event).includes(CARD_MIME)) dragIndex = heldIndex;
        const from = dragIndex;
        dragIndex = -1;
        if (from < 0) return;
        event.preventDefault();
        event.stopPropagation();
        clearOrderHints();
        const at = insertAt(event, from);
        if (at < 0) return;
        // Dropping in front of a card that sits after the dragged one means the gap left
        // behind already moved that target one place to the left.
        const ids = currentCardIds();
        const order = moveIds(ids, from, at > from ? at - 1 : at);
        if (!order) return;
        void commitOrder(order, ids[from]);
    }, { signal });

    container.addEventListener("dragend", () => {
        dragIndex = -1;
        heldIndex = -1;
        stopAutoScroll();
        for (const card of deck.querySelectorAll(".h3lvm-dragging")) {
            card.classList.remove("h3lvm-dragging");
        }
        clearOrderHints();
        deck.classList.remove("h3lvm-drop-in");
    }, { signal });

    // The ids exactly as the deck draws them, top left to bottom right.
    function currentCardIds() {
        return Array.from(deck.querySelectorAll(".h3lvm-card[data-upload-id]"))
            .map((card) => Number(card.dataset.uploadId));
    }

    // Ask the library to renumber itself, then reload and follow the dragged video to its
    // new number: the selection stays on the video the user moved, not on the number.
    async function commitOrder(order, draggedId) {
        const project = currentProject();
        reordering = true;
        try {
            const res = await api.fetchApi("/h3_lvm/uploads/reorder", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project, order }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.error || `排序失败（HTTP ${res.status}）`);
            const nextId = renumberedId(order, draggedId);
            if (nextId && segmentWidget) {
                segmentWidget.value = nextId;
                persist();
            }
            if (!signal.aborted && builtMode === MODE_UPLOADS && currentProject() === project) {
                await loadDeck();
            }
        } catch (error) {
            statusText.textContent = `排序没有保存：${error.message || "未知错误"}`;
            if (!signal.aborted && builtMode === MODE_UPLOADS) await loadDeck();
        } finally {
            reordering = false;
        }
    }

    // Reload when the project name changes; the bin belongs to this mode only.
    if (projectWidget) {
        const origCallback = projectWidget.callback;
        projectWidget.callback = (val) => {
            origCallback?.call(projectWidget, val);
            persist();
            loadDeck();
        };
    }

    if (segmentWidget) {
        const original = segmentWidget.callback;
        segmentWidget.callback = function () {
            const result = original?.apply(this, arguments);
            persist();
            loadDeck();
            return result;
        };
    }

    // The canvas combo is the same control as the two buttons, so changing it by hand
    // rebuilds the panel the same way. switchMode writes .value without calling the
    // callback, so this cannot loop.
    // A different decode size is a different card label, so the deck is re-read. The
    // stored videos are untouched; only the plan shown on the card changes.
    if (sizeWidget) {
        const original = sizeWidget.callback;
        sizeWidget.callback = function (val) {
            const result = original?.apply(this, arguments);
            syncCustomSizeLabel();
            if (builtMode === MODE_UPLOADS) void loadDeck();
            return result;
        };
    }

    if (customSizeWidget) {
        const original = customSizeWidget.callback;
        customSizeWidget.callback = function (val) {
            const result = original?.apply(this, arguments);
            if (builtMode === MODE_UPLOADS) void loadDeck();
            return result;
        };
    }

    if (modeWidget) {
        const original = modeWidget.callback;
        modeWidget.callback = function (val) {
            const result = original?.apply(this, arguments);
            switchMode(val);
            return result;
        };
    }

    const onSegmentsChanged = event => {
        if (builtMode !== MODE_SEGMENTS) return;
        if (event.detail?.project === currentProject()) {
            loadDeck(event.detail.deleted_id);
        }
    };
    api.addEventListener("h3_lvm/changed", onSegmentsChanged);
    signal.addEventListener("abort", () => api.removeEventListener("h3_lvm/changed", onSegmentsChanged), { once: true });

    const onUploadsChanged = event => {
        // This panel reloads after its own upload; the event is for other tabs and for
        // changes made elsewhere.
        if (importing || reordering || builtMode !== MODE_UPLOADS) return;
        if (event.detail?.project === currentProject()) loadDeck();
    };
    api.addEventListener("h3_lvm/uploads_changed", onUploadsChanged);
    signal.addEventListener("abort", () => api.removeEventListener("h3_lvm/uploads_changed", onUploadsChanged), { once: true });

    node._h3lvmRefresh = () => {
        syncFromGraph();
        return loadDeck();
    };
    signal.addEventListener("abort", () => { delete node._h3lvmRefresh; }, { once: true });
    const onExecuted = () => loadDeck();
    api.addEventListener("execution_success", onExecuted);
    signal.addEventListener("abort", () => api.removeEventListener("execution_success", onExecuted), { once: true });

    // First paint: the graph wins, so an old workflow opens in cut mode with its own
    // project and segment, exactly as before this change.
    buildForMode(graphMode());
    modeState = seedState(modeState, graphMode(), {
        project_name: projectWidget?.value,
        segment_id: segmentWidget?.value,
    });
    writeModeState(node.properties, modeState);
    loadDeck();
}