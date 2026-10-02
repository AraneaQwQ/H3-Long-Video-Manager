// RAFOLIE 2026-10-03: the visual panel of the H3 Long Video Manager node.
//
// What it is for: the node saves every segment it cuts into a project bin, and the
// user picks from that bin. So the deck shows the whole bin in segment order - the
// cards that already exist are the ones worth seeing, not only the last run - with
// the segments from this node's last run marked 本次. Clicking a card sets 输出片段编号.
//
// It reuses the Segment Picker look on purpose (same container, project row,
// toolbar, card grid, footer) — one plugin, one visual language. The shared pieces
// are project_menu.js, preview_overlay.js and h3lvm_picker.css.
//
// Display only. No new node inputs and no new saved workflow fields.

import { api } from "../../scripts/api.js";
import { addPanel } from "./dom_panel.js";
import { openPreview } from "./preview_overlay.js";
import { createProjectMenu } from "./project_menu.js";
import { appendThumbnail } from "./thumb_fit.js";
import { createCardZoom } from "./card_zoom.js";

const PROJECT_FIELD = "project_name";
const SEGMENT_FIELD = "segment_id";

// Panel height in canvas pixels: project menu + tool row + one card row + the legend.
// The deck is always visible, so this doubles as the widget's minimum height. LiteGraph
// adds it to the parameter rows and grows any node too short to show a card, which is
// also why there is no expand/collapse button and no manual resizing here.
const PANEL_H = 320;

export function installManagerPanel(node) {
    const lifetime = node._h3lvmManagerLifetime ?? new AbortController();
    node._h3lvmManagerLifetime = lifetime;
    const signal = lifetime.signal;

    const container = document.createElement("div");
    container.className = "h3lvm-container";

    function widgetFor(name) {
        return node.widgets?.find(item => item.name === name);
    }

    // --- Project menu (same row as the Picker) ---
    const menu = createProjectMenu({
        node,
        widget: widgetFor(PROJECT_FIELD),
        signal,
        onChange: () => void render(),
    });
    container.appendChild(menu.element);
    node._h3lvmRefreshProjects = menu.refresh;

    // --- Tool row: reload, card size, and what this run made ---
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
    toolLabel.textContent = "🎬 素材库";

    const runText = document.createElement("span");
    runText.className = "h3lvm-status";
    runText.textContent = "读取中…";

    const spacer = document.createElement("span");
    spacer.className = "h3lvm-spacer";

    toolbar.append(refreshBtn);
    createCardZoom({ container, node }).mount(toolbar);
    toolbar.append(toolSep, toolLabel, runText, spacer);
    container.appendChild(toolbar);

    // --- Card grid ---
    const deck = document.createElement("div");
    deck.className = "h3lvm-deck";
    container.appendChild(deck);

    // --- Footer legend ---
    const footer = document.createElement("div");
    footer.className = "h3lvm-footer";
    const hintText = document.createElement("span");
    hintText.className = "h3lvm-hint";
    hintText.textContent = "👉 点卡片＝切换输出片段编号 · ▶＝预览 · 删除片段与卡片大小在「H3 Segment Picker」";
    footer.appendChild(hintText);
    container.appendChild(footer);

    addPanel(node, "h3lvm_manager_panel", container, PANEL_H);

    // Which ids this node produced in its last run; used for a badge, not for
    // filtering the deck.
    let runIds = new Set();
    let rendering = false;
    let pendingRender = false;

    function currentProject() {
        const raw = widgetFor(PROJECT_FIELD)?.value;
        return typeof raw === "string" ? raw.trim() : "";
    }

    function selectedSegment() {
        return Number(widgetFor(SEGMENT_FIELD)?.value);
    }

    refreshBtn.onclick = (event) => {
        event.stopPropagation();
        void menu.refresh();
        void render();
    };

    function formatIds(ids) {
        const sorted = [...ids].sort((a, b) => a - b);
        const parts = [];
        let index = 0;
        while (index < sorted.length) {
            let last = index;
            while (last + 1 < sorted.length && sorted[last + 1] === sorted[last] + 1) last++;
            parts.push(index === last ? String(sorted[index]) : sorted[index] + "–" + sorted[last]);
            index = last + 1;
        }
        return parts.join(", ");
    }

    function updateStatus(text) {
        runText.textContent = text;
    }

    async function render() {
        // Two triggers can land at once (a run plus a project switch); one redraw
        // at a time keeps the last one authoritative.
        if (rendering) {
            pendingRender = true;
            return;
        }
        rendering = true;
        try {
            do {
                pendingRender = false;
                await renderOnce();
            } while (pendingRender && !signal.aborted);
        } finally {
            rendering = false;
        }
    }

    async function renderOnce() {
        if (signal.aborted) return;
        const project = currentProject();
        if (!project) return;

        let segments = [];
        try {
            const res = await api.fetchApi(`/h3_lvm/segments?project=${encodeURIComponent(project)}`, { cache: "no-store" });
            if (!res.ok) return;
            const data = await res.json();
            segments = data.segments || [];
        } catch (error) {
            if (!signal.aborted) console.warn("[H3 LVM] run panel could not load segments:", error);
            return;
        }
        if (signal.aborted) return;

        const ordered = [...segments]
            .map(seg => ({ seg, id: Number(seg.segment_id) }))
            .filter(item => Number.isFinite(item.id))
            .sort((a, b) => a.id - b.id);
        const present = new Set(ordered.map(item => item.id));
        // Cards deleted in the Picker must lose their 本次 badge as well.
        runIds = new Set([...runIds].filter(id => present.has(id)));

        if (!ordered.length) {
            deck.innerHTML = '<div class="h3lvm-empty">这个素材库还没有片段。运行本节点即可写入；删除片段请在「H3 Segment Picker」里做。</div>';
            updateStatus("空库");
            return;
        }

        const currentSel = selectedSegment();
        deck.innerHTML = "";
        for (const item of ordered) {
            deck.appendChild(makeCard(item.seg, item.id === currentSel, runIds.has(item.id)));
        }
        const runNote = runIds.size
            ? ` · 本次生成 ${runIds.size} 段（片段 ${formatIds([...runIds])}）`
            : "";
        updateStatus(`库内 ${ordered.length} 段${runNote}`);
    }

    function makeCard(seg, active, fromRun) {
        const card = document.createElement("div");
        card.className = active ? "h3lvm-card active" : "h3lvm-card";
        card.dataset.segId = String(seg.segment_id);
        card.title = "把片段 " + seg.segment_id + " 输出到下游";

        const thumbWrap = document.createElement("div");
        thumbWrap.className = "h3lvm-thumb-wrap";
        appendThumbnail(thumbWrap, seg);
        if (fromRun) {
            const badge = document.createElement("span");
            badge.className = "h3lvm-badge";
            badge.textContent = "本次";
            badge.title = "这个片段是本节点上一次运行保存的";
            thumbWrap.appendChild(badge);
        }
        if (seg.has_mp4 && seg.mp4_url) {
            const playBtn = document.createElement("button");
            playBtn.className = "h3lvm-play-btn";
            playBtn.textContent = "▶";
            playBtn.title = "预览视频";
            playBtn.onclick = (event) => {
                event.stopPropagation();
                openPreview(seg, signal);
            };
            thumbWrap.appendChild(playBtn);
        }
        card.appendChild(thumbWrap);

        const meta = document.createElement("div");
        meta.className = "h3lvm-meta";
        const seconds = seg.duration_sec != null ? seg.duration_sec.toFixed(2) + " 秒 · " : "";
        const labelEl = document.createElement("div");
        labelEl.className = "h3lvm-seg-label";
        labelEl.textContent = "片段 " + seg.segment_id;
        const infoEl = document.createElement("div");
        infoEl.className = "h3lvm-seg-info";
        infoEl.textContent = seg.frames + " 帧 · " + seconds + seg.width + "×" + seg.height;
        meta.append(labelEl, infoEl);
        card.appendChild(meta);

        card.onclick = () => {
            const widget = widgetFor(SEGMENT_FIELD);
            if (widget) {
                widget.value = seg.segment_id;
                widget.callback?.(seg.segment_id);
            }
            // Reflect the choice locally; no refetch, the cards are already correct.
            deck.querySelectorAll(".h3lvm-card").forEach(item => item.classList.remove("active"));
            card.classList.add("active");
            updateStatus(`已选片段 ${seg.segment_id}`);
            node.setDirtyCanvas?.(true, true);
        };
        return card;
    }

    function onChanged(event) {
        const data = event.detail || {};
        const project = currentProject();
        if (!project || data.project !== project) return;
        if (Array.isArray(data.segments) && data.segments.length) {
            runIds = new Set(data.segments.map(Number).filter(Number.isFinite));
        }
        void render();
    }

    api.addEventListener("h3_lvm/changed", onChanged);
    signal.addEventListener("abort", () => api.removeEventListener("h3_lvm/changed", onChanged), { once: true });

    // The deck belongs to the bin, not to this page visit: opening the workflow again
    // shows the cards right away. The project name is only restored in configure(),
    // which runs after onNodeCreated, so h3lvm_manager.js calls this hook once the
    // widgets hold their saved values.
    node._h3lvmDeckRefresh = render;

    void render();
}
