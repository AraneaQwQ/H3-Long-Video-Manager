// RAFOLIE 2026-10-09: the card deck shared by the Manager and the Smart Split panel.
//
// Both nodes write into the SAME project bin, so both show the same deck: every
// segment in the bin in segment order, with the ones from this node's last run
// marked 本次. Clicking a card sets 输出片段编号. One implementation on purpose -
// a second copy of this code is how two panels start to look different.
//
// The deck belongs to the bin, not to the node that filled it: a bin written by the
// Manager shows the same cards in the Smart Split panel and vice versa.
//
// Display only. No new node inputs and no new saved workflow fields.

import { api } from "../../scripts/api.js";
import { openPreview } from "./preview_overlay.js";
import { appendThumbnail } from "./thumb_fit.js";
import { createCardZoom } from "./card_zoom.js";

export function createDeck({
    node,
    signal,
    container,
    projectField = "project_name",
    segmentField = "segment_id",
    toolLabel = "🎬 素材库",
    emptyText = "这个素材库还没有片段。运行本节点即可写入；删除片段请在「H3 Segment Picker」里做。",
    footerLines = [],
    onRefresh = null,
}) {
    // --- Tool row: reload, card size, and what this bin holds ---
    const toolbar = document.createElement("div");
    toolbar.className = "h3lvm-toolbar";

    const refreshBtn = document.createElement("button");
    refreshBtn.className = "h3lvm-refresh-btn";
    refreshBtn.textContent = "🔄 刷新";
    refreshBtn.title = "重新读取当前项目的片段列表";

    // Merge mode: pick adjacent cards, then join them into one segment. It uses
    // the same button shell as 刷新 so the tool row stays exactly one line tall.
    const mergeBtn = document.createElement("button");
    mergeBtn.className = "h3lvm-refresh-btn h3lvm-merge-btn";
    mergeBtn.textContent = "🔗 合并模式";
    mergeBtn.title = "点选相邻的卡片，再把它们合并成一个片段";

    const mergeOkBtn = document.createElement("button");
    mergeOkBtn.className = "h3lvm-refresh-btn h3lvm-merge-ok";
    mergeOkBtn.textContent = "✅ 确认合并";
    mergeOkBtn.title = "把选中的相邻片段合并成一个片段，编号沿用其中最小的一个";
    mergeOkBtn.disabled = true;
    mergeOkBtn.style.display = "none";

    const toolSep = document.createElement("span");
    toolSep.className = "h3lvm-tool-sep";

    const toolText = document.createElement("span");
    toolText.className = "h3lvm-tool-label";
    toolText.textContent = toolLabel;

    const runText = document.createElement("span");
    runText.className = "h3lvm-status";
    runText.textContent = "读取中…";

    const spacer = document.createElement("span");
    spacer.className = "h3lvm-spacer";

    toolbar.append(refreshBtn, mergeBtn, mergeOkBtn);
    createCardZoom({ container, node }).mount(toolbar);
    toolbar.append(toolSep, toolText, runText, spacer);
    container.appendChild(toolbar);

    // --- Card grid ---
    const deck = document.createElement("div");
    deck.className = "h3lvm-deck";
    container.appendChild(deck);

    // --- Footer legend (caller decides the wording) ---
    const footer = document.createElement("div");
    footer.className = "h3lvm-footer";
    for (const line of footerLines) {
        const hint = document.createElement("span");
        hint.className = "h3lvm-hint";
        hint.textContent = line;
        footer.appendChild(hint);
    }
    container.appendChild(footer);

    // Which ids this node produced in its last run; used for a badge, not for
    // filtering the deck.
    let runIds = new Set();
    // Merge mode is a UI mode, not a saved field: leaving the page drops it.
    let mergeMode = false;
    let picked = new Set();
    let merging = false;
    let rendering = false;
    let pendingRender = false;

    function widgetFor(name) {
        return node.widgets?.find(item => item.name === name);
    }

    function currentProject() {
        const raw = widgetFor(projectField)?.value;
        return typeof raw === "string" ? raw.trim() : "";
    }

    function selectedSegment() {
        return Number(widgetFor(segmentField)?.value);
    }

    refreshBtn.onclick = (event) => {
        event.stopPropagation();
        if (onRefresh) {
            try {
                onRefresh();
            } catch (error) {
                console.warn("[H3 LVM] deck refresh hook failed:", error);
            }
        }
        void render();
    };

    function pickedIds() {
        return [...picked].sort((a, b) => a - b);
    }

    // Button state only; the status line is written by the callers that know why.
    function updateMergeUi() {
        mergeBtn.classList.toggle("on", mergeMode);
        mergeOkBtn.style.display = mergeMode ? "" : "none";
        mergeOkBtn.disabled = !(mergeMode && picked.size >= 2 && !merging);
        mergeOkBtn.textContent = merging ? "⏳ 合并中…" : "✅ 确认合并";
    }

    function setMergeMode(on) {
        mergeMode = on;
        if (!on) picked.clear();
        updateMergeUi();
        deck.querySelectorAll(".h3lvm-card.picked").forEach(item => item.classList.remove("picked"));
    }

    function togglePick(id) {
        if (picked.has(id)) {
            picked.delete(id);
        } else if (!picked.size) {
            picked.add(id);
        } else {
            const ids = pickedIds();
            // Only a contiguous block can become one clip, so a card that does not
            // touch the current block starts a new selection instead of a gap.
            if (id === ids[ids.length - 1] + 1 || id === ids[0] - 1) {
                picked.add(id);
            } else {
                picked.clear();
                picked.add(id);
            }
        }
        deck.querySelectorAll(".h3lvm-card").forEach(item => {
            item.classList.toggle("picked", picked.has(Number(item.dataset.segId)));
        });
        updateMergeUi();
        updateStatus(picked.size
            ? `合并模式：已选 ${picked.size} 段（片段 ${formatIds(pickedIds())}）`
            : "合并模式：请点选相邻的卡片（至少两段）");
    }

    mergeBtn.onclick = (event) => {
        event.stopPropagation();
        setMergeMode(!mergeMode);
        updateStatus(mergeMode
            ? "合并模式：点选相邻卡片后按「确认合并」"
            : "已退出合并模式");
    };

    mergeOkBtn.onclick = async (event) => {
        event.stopPropagation();
        const ids = pickedIds();
        const project = currentProject();
        if (ids.length < 2 || !project || merging) return;
        merging = true;
        updateMergeUi();
        try {
            const res = await api.fetchApi("/h3_lvm/merge", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ project, segment_ids: ids }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                updateStatus("合并失败：" + (data.error || res.status));
                return;
            }
            // 输出片段编号 must keep pointing at something that still exists:
            // a merged id follows the merge, a later id follows the renumbering.
            const widget = widgetFor(segmentField);
            const current = selectedSegment();
            if (widget && Number.isFinite(current)) {
                let next = current;
                if (current >= ids[0] && current <= ids[ids.length - 1]) next = ids[0];
                else if (current > ids[ids.length - 1]) next = current - (ids.length - 1);
                if (next !== current) {
                    widget.value = next;
                    widget.callback?.(next);
                }
            }
            setMergeMode(false);
            updateStatus(`已合并片段 ${formatIds(ids)} → 片段 ${data.merged_id}（去掉 ${data.dropped_overlap_frames || 0} 帧重叠）`);
            void render();
        } catch (error) {
            updateStatus("合并失败：" + (error?.message || error));
        } finally {
            merging = false;
            updateMergeUi();
        }
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
            if (!signal.aborted) console.warn("[H3 LVM] deck panel could not load segments:", error);
            return;
        }
        if (signal.aborted) return;

        const ordered = [...segments]
            .map(seg => ({ seg, id: Number(seg.segment_id) }))
            .filter(item => Number.isFinite(item.id))
            .sort((a, b) => a.id - b.id);
        const present = new Set(ordered.map(item => item.id));
        // Cards deleted in the Picker must lose their badge as well.
        runIds = new Set([...runIds].filter(id => present.has(id)));
        // A merge or a delete elsewhere can take a picked card away; drop it rather
        // than offer a merge the server would refuse.
        picked = new Set([...picked].filter(id => present.has(id)));
        mergeBtn.disabled = ordered.length < 2;
        mergeBtn.title = ordered.length < 2
            ? "至少需要两段才能合并"
            : "点选相邻的卡片，再把它们合并成一个片段";
        if (ordered.length < 2 && mergeMode) setMergeMode(false);
        updateMergeUi();

        if (!ordered.length) {
            deck.innerHTML = '<div class="h3lvm-empty">' + emptyText + "</div>";
            updateStatus("空库");
            return;
        }

        const currentSel = selectedSegment();
        deck.innerHTML = "";
        for (const item of ordered) {
            deck.appendChild(makeCard(item.seg, item.id === currentSel, runIds.has(item.id), picked.has(item.id)));
        }
        const runNote = runIds.size
            ? ` · 本次生成 ${runIds.size} 段（片段 ${formatIds([...runIds])}）`
            : "";
        const mergeNote = mergeMode ? ` · 合并模式已选 ${picked.size} 段` : "";
        updateStatus(`库内 ${ordered.length} 段${runNote}${mergeNote}`);
    }

    function makeCard(seg, active, fromRun, isPicked) {
        const card = document.createElement("div");
        const classes = ["h3lvm-card"];
        if (active) classes.push("active");
        if (isPicked) classes.push("picked");
        card.className = classes.join(" ");
        card.dataset.segId = String(seg.segment_id);
        card.title = mergeMode
            ? "把片段 " + seg.segment_id + " 加入/移出合并选择"
            : "把片段 " + seg.segment_id + " 输出到下游";

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
        if (isPicked) {
            const pickBadge = document.createElement("span");
            pickBadge.className = "h3lvm-pick-badge";
            pickBadge.textContent = "已选";
            pickBadge.title = "已加入本次合并选择";
            thumbWrap.appendChild(pickBadge);
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
            if (mergeMode) {
                togglePick(Number(seg.segment_id));
                return;
            }
            const widget = widgetFor(segmentField);
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

    return { render, toolbar, deck, footer };
}