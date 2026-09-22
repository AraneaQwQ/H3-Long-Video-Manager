/**
 * H3 Long Video Manager — Segment Picker Frontend (Phase B2)
 *
 * Adds a card-based thumbnail gallery to the "H3 Segment Picker" node.
 * - Fetches segment list from /h3_lvm/segments API
 * - Renders cards with thumbnails, frame count, duration
 * - Click card → sets segment_id widget
 * - Refresh button
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

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            try {
                setupPickerUI(this);
            } catch (e) {
                console.warn("[H3 LVM] UI setup failed (node still functional):", e);
            }
            return r;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            this._h3lvm_gallery = null;
            return r;
        };
    }
});

// --- Main UI setup ---
function setupPickerUI(node) {
    const projectWidget = node.widgets?.find(w => w.name === "project_name");
    const segmentWidget = node.widgets?.find(w => w.name === "segment_id");

    // --- DOM structure ---
    const container = document.createElement("div");
    container.className = "h3lvm-container";

    // Header
    const header = document.createElement("div");
    header.className = "h3lvm-header";

    const titleSpan = document.createElement("span");
    titleSpan.className = "h3lvm-title";
    titleSpan.textContent = "📦 H3 Segment Bin";

    const projectTag = document.createElement("span");
    projectTag.className = "h3lvm-project-tag";
    projectTag.textContent = projectWidget?.value || "H3_LVM";

    const refreshBtn = document.createElement("button");
    refreshBtn.className = "h3lvm-refresh-btn";
    refreshBtn.textContent = "🔄";
    refreshBtn.title = "刷新列表";

    header.appendChild(titleSpan);
    header.appendChild(projectTag);
    header.appendChild(refreshBtn);
    container.appendChild(header);

    // Card deck
    const deck = document.createElement("div");
    deck.className = "h3lvm-deck";
    container.appendChild(deck);

    // Footer
    const footer = document.createElement("div");
    footer.className = "h3lvm-footer";
    const selectedInfo = document.createElement("span");
    selectedInfo.className = "h3lvm-selected";
    selectedInfo.textContent = `选中: #${segmentWidget?.value || 1}`;
    footer.appendChild(selectedInfo);
    container.appendChild(footer);

    // Add as DOM widget
    node.addDOMWidget("h3lvm_gallery", "gallery", container, {
        serialize: false,
        hideOnZoom: false,
    });

    // Minimum width
    if (node.size[0] < 420) node.setSize([420, node.size[1]]);

    // --- Load segments ---
    async function loadSegments() {
        const project = projectWidget?.value || "H3_LVM";
        projectTag.textContent = project;

        try {
            const cacheBust = Date.now();
            const res = await api.fetchApi(`/h3_lvm/segments?project=${encodeURIComponent(project)}&_t=${cacheBust}`);
            if (!res.ok) {
                deck.innerHTML = `<div class="h3lvm-empty">API 错误: ${res.status}</div>`;
                return;
            }
            const data = await res.json();
            const segments = data.segments || [];

            if (segments.length === 0) {
                deck.innerHTML = `<div class="h3lvm-empty">
                    <div>📭 该库暂无已保存片段</div>
                    <div class="h3lvm-empty-hint">先用 H3 Long Video Manager 节点裁切并保存</div>
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
                    // Add cache-buster so new content shows after re-save
                    const sep = seg.thumbnail_url.includes("?") ? "&" : "?";
                    img.src = seg.thumbnail_url + sep + "_t=" + Date.now();
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
                const dur = seg.duration_sec != null ? `${seg.duration_sec.toFixed(1)}s` : "";
                const res = `${seg.width}×${seg.height}`;
                meta.innerHTML = `
                    <div class="h3lvm-seg-label">Seg #${seg.segment_id}</div>
                    <div class="h3lvm-seg-info">${seg.frames}帧 | ${dur} | ${res}</div>
                `;
                card.appendChild(meta);

                // Click to select
                card.onclick = () => {
                    if (segmentWidget) {
                        segmentWidget.value = seg.segment_id;
                        segmentWidget.callback?.(seg.segment_id);
                    }
                    // Update active state
                    deck.querySelectorAll(".h3lvm-card").forEach(c => c.classList.remove("active"));
                    deck.querySelectorAll(".h3lvm-active-badge").forEach(b => b.remove());
                    card.classList.add("active");
                    const badge = document.createElement("div");
                    badge.className = "h3lvm-active-badge";
                    badge.textContent = "已选中";
                    card.querySelector(".h3lvm-thumb-wrap").appendChild(badge);
                    selectedInfo.textContent = `选中: #${seg.segment_id}`;
                };

                deck.appendChild(card);
            }

            // Fit node height
            fitToContent();

        } catch (e) {
            console.warn("[H3 LVM] Failed to load segments:", e);
            deck.innerHTML = `<div class="h3lvm-empty">加载失败: ${e.message}</div>`;
        }
    }

    // --- Fit node to content ---
    function fitToContent() {
        requestAnimationFrame(() => {
            const deckH = Math.min(deck.scrollHeight || 0, 280);
            if (deckH === 0) return;
            const stdW = (node.widgets || []).filter(w => w.type !== "custom");
            const stdH = stdW.length * 28;
            const CHROME = 130;
            const target = Math.max(stdH + deckH + CHROME, 160);
            if (Math.abs(node.size[1] - target) > 5) {
                node.setSize([node.size[0], target]);
            }
        });
    }

    // --- MP4 Preview Modal ---
    function openPreview(seg, project) {
        // Remove existing
        const existing = document.getElementById("h3lvm-preview-overlay");
        if (existing) existing.remove();

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
        info.textContent = `Seg #${seg.segment_id} | ${seg.frames}帧 | ${seg.duration_sec?.toFixed(1)}s | ${seg.width}×${seg.height}`;

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
            video.src = "";
            overlay.remove();
            window.removeEventListener("keydown", onKey);
        }
        function onKey(e) { if (e.key === "Escape") close(); }
        closeBtn.onclick = close;
        overlay.onclick = (e) => { if (e.target === overlay) close(); };
        window.addEventListener("keydown", onKey);
    }

    // --- Wire up events ---
    refreshBtn.onclick = () => loadSegments();

    // Reload when project name changes
    if (projectWidget) {
        const origCallback = projectWidget.callback;
        projectWidget.callback = (val) => {
            origCallback?.(val);
            loadSegments();
        };
    }

    // Initial load
    loadSegments();
}
