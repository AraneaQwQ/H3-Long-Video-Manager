// RAFOLIE 2026-10-10: the card panel for the two reference loaders.
//
// What these nodes are: the official MiniMaxH3ReferenceToVideo takes nine
// ref_image_0..8 and three ref_audio_0..2 ports, so a workflow that wants to feed
// references needs a wall of LoadImage/LoadAudio nodes plus resize nodes. These two
// nodes keep the media as cards and the numbered ports permanent; the panel below
// only edits the ordered list that lives in the hidden media_files widget.
//
// UI rules this panel follows, because the other visual nodes already learned them:
//   - the panel has a fixed height and never resizes the node, so pressing
//     刷新 / 卡片大小 / ←→ can never collapse the node to its minimum;
//   - the deck is a wrapping grid, and card size is the shared 100%-400% control;
//   - portrait media is displayed whole (blurred side fill), same card size;
//   - a card can be parked with 跳过: it stays in the list, moves to a second block
//     at the back of the deck, and holds no slot - the node filters it out, so the
//     numbered ports are only the cards still in the slot block;
//   - the top row is the shared project menu (web/project_menu.js), so "which
//     project" reads the same on every visual node. The two preset buttons next to
//     "add" read and write <project>/h3lvm_references.json, which holds paths only:
//     a preset costs a few hundred bytes however big the images are, and loading one
//     never uploads or copies a file. What a preset stores is the arrangement, not
//     just the files: the order of the cards and which of them were parked are saved
//     and restored, because that is the combination the user actually built.
//   - the output size on an image card is asked from the server
//     (GET /h3_lvm/ref_plan), which is the same planner the node runs - a copy of
//     that algorithm in JavaScript is how a card starts lying about its tensor. The
//     request carries the target MP and the upscale switch, because both decide it.
//
// Field names and saved workflow values are unchanged: media_files stays a string
// widget, only its label is Chinese and it is hidden once the panel is running.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addPanel } from "./dom_panel.js";
import { createCardZoom } from "./card_zoom.js";
import { appendThumbnail } from "./thumb_fit.js";
import { createProjectMenu } from "./project_menu.js";
import {
    MAX_REF_AUDIOS, MAX_REF_IMAGES, addEntries, applyPreset, audioInfoLine, countActive,
    insertPosition, isSkipped, mediaKey, mediaKind, moveActive, parseMedia, pickPresetEntries, removeEntry,
    replaceEntry, resolveTrim, restoreAll, restoreAt, serializeMedia, sizeLine, skipAt, slotName,
    slotRangeText, slotTitle, splitEntries, trimRange,
} from "./ref_state.js";

try {
    const sheets = [
        ["h3lvm-styles", "./h3lvm_picker.css"],
        ["h3ref-styles", "./ref_loader.css"],
    ];
    for (const [styleId, path] of sheets) {
        if (document.getElementById(styleId)) continue;
        const link = document.createElement("link");
        link.id = styleId;
        link.rel = "stylesheet";
        link.type = "text/css";
        link.href = new URL(path, import.meta.url).href;
        document.head.appendChild(link);
    }
} catch (error) {
    console.warn("[H3 Ref Loader] CSS injection failed:", error);
}

const IMAGE_NODE = "H3 Image Reference Loader";
const AUDIO_NODE = "H3 Audio Reference Loader";
const MEDIA_FIELD = "media_files";
const MP_FIELD = "target_megapixels";
const RESAMPLE_FIELD = "resampling_method";
const UPSCALE_FIELD = "upscale_small_images";
const PROJECT_FIELD = "project_name";

// Fixed on purpose: no collapse button, no self-resizing. The deck scrolls inside.
const SPECS = {
    [IMAGE_NODE]: {
        kind: "image",
        max: MAX_REF_IMAGES,
        // The panel grew once, at creation, for the project row and the preset buttons.
        // It is a constant: pressing 刷新 / 卡片大小 still never resizes the node.
        panelH: 440,
        accept: "image/png,image/jpeg,image/webp,image/bmp,image/gif",
        addLabel: "＋ 添加参考图",
        deckLabel: "🖼 参考图槽位",
        emptyText: "还没有参考图。点「添加参考图」，或把图片直接拖到这里。",
        dropHint: "拖放图片到这里加入；卡片顺序就是 ref_image_0..8 的槽位顺序。",
    },
    [AUDIO_NODE]: {
        kind: "audio",
        max: MAX_REF_AUDIOS,
        panelH: 360,
        accept: "audio/*,.wav,.mp3,.m4a,.flac,.ogg,.opus",
        addLabel: "＋ 添加参考音频",
        deckLabel: "🎧 参考音频槽位",
        emptyText: "还没有参考音频。点「添加参考音频」，或把音频文件直接拖到这里。",
        dropHint: "音频原样传给 H3：不重采样、不截断、不混音。空槽输出 None。",
    },
};

// Field names stay English inside the workflow; only the label on the node changes.
const LABELS = {
    media_files: "🎞 参考素材列表",
    target_megapixels: "🎯 目标像素量 (MP)",
    resampling_method: "🔍 重采样算法",
    upscale_small_images: "↕ 放大小图至目标 MP",
    project_name: "📦 项目素材库",
};

const TOOLTIPS = {
    media_files: "由下方卡片面板写入的 JSON 列表；卡片顺序就是 ref_image_0..8 / ref_audio_0..2 的槽位顺序。手写 API 时也可以直接填文件名列表。",
    target_megapixels: "每张图的目标像素量（百万像素）。每张图按自己的比例算尺寸并对齐 32 像素网格，不裁切；卡片上显示真实输出尺寸和真实 MP。改这个数会立刻重算卡片上的尺寸。",
    resampling_method: "缩放用的重采样算法：Lanczos 质量最好、缩小首选（较慢）；Bicubic 质量与速度折中；Bilinear 更快更柔和；Nearest 保留像素硬边，适合像素风素材。界面选哪个，后端就用哪个。",
    upscale_small_images: "关闭时，小图不会被放大到目标 MP，但仍会调整到 32 的倍数，以满足 H3 输入尺寸要求；最终尺寸可能略有变化。开启时，小于目标面积的图也按目标面积放大。",
    project_name: "「存为项目预设 / 载入项目预设」读写哪个项目文件夹。预设里只有参考素材的路径与排列（含哪些卡片被跳过），不复制文件；这个字段不影响本节点输出的像素。",
};

app.registerExtension({
    name: "H3.LVM.RefLoaders",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        const spec = SPECS[nodeData.name];
        if (!spec) return;

        const originalCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = originalCreated ? originalCreated.apply(this, arguments) : undefined;
            try {
                translateWidgets(this);
                installRefPanel(this, spec);
            } catch (error) {
                console.warn("[H3 Ref Loader] panel setup failed (node still works):", error);
            }
            return r;
        };

        const originalConfigure = nodeType.prototype.configure;
        nodeType.prototype.configure = function (info) {
            const r = originalConfigure ? originalConfigure.apply(this, arguments) : undefined;
            // The cards belong to the saved graph, not to this page visit: reopening
            // the workflow shows them again without a refresh click.
            this._h3lvmRefRefresh?.();
            return r;
        };

        const originalRemoved = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            this._h3lvmRefLifetime?.abort();
            return originalRemoved ? originalRemoved.apply(this, arguments) : undefined;
        };
    },
});

function translateWidgets(node) {
    for (const widget of node.widgets ?? []) {
        const label = LABELS[widget.name];
        if (label) widget.label = label;
        const tooltip = TOOLTIPS[widget.name];
        if (tooltip) widget.tooltip = tooltip;
    }
}

// --- The panel ---
function installRefPanel(node, spec) {
    const lifetime = node._h3lvmRefLifetime ?? new AbortController();
    node._h3lvmRefLifetime = lifetime;
    const signal = lifetime.signal;

    function widgetFor(name) {
        return node.widgets?.find(item => item.name === name);
    }

    let entries = readEntries();
    // mediaKey -> { width, height } or { error }; `${mediaKey}|${mp}` -> plan.
    const sourceCache = new Map();
    const planCache = new Map();
    const audioCache = new Map();
    // Bumped on every render so a slow response cannot write into an old card.
    let generation = 0;

    const container = document.createElement("div");
    container.className = "h3lvm-container";

    // --- Row 1: the project bin ---
    // Same component as the Segment Picker and the Manager, so the menu, the 新建 and
    // the 删除 all behave the same here. On these two nodes the bin decides which
    // reference preset the buttons below read and write.
    const menu = createProjectMenu({
        node,
        widget: widgetFor(PROJECT_FIELD),
        signal,
        // This node reads and writes its own kind's reference library, so the menu
        // lists that library and counts its cards - the video bins and the other
        // kind's presets are different material in different folders.
        scope: spec.kind,
        onChange: () => { void refreshPreset(); },
    });
    container.appendChild(menu.element);

    // --- Tool row: same shell as the deck panels, so the two look like one family ---
    const toolbar = document.createElement("div");
    toolbar.className = "h3lvm-toolbar";

    const refreshBtn = document.createElement("button");
    refreshBtn.className = "h3lvm-refresh-btn";
    refreshBtn.textContent = "🔄 刷新";
    refreshBtn.title = "重新读取卡片尺寸与音频信息";

    const toolSep = document.createElement("span");
    toolSep.className = "h3lvm-tool-sep";

    const toolText = document.createElement("span");
    toolText.className = "h3lvm-tool-label";
    toolText.textContent = spec.deckLabel;

    const statusText = document.createElement("span");
    statusText.className = "h3lvm-status";

    const spacer = document.createElement("span");
    spacer.className = "h3lvm-spacer";

    toolbar.append(refreshBtn);
    createCardZoom({ container, node }).mount(toolbar);
    toolbar.append(toolSep, toolText, statusText, spacer);
    container.appendChild(toolbar);

    // --- Add row ---
    const addRow = document.createElement("div");
    addRow.className = "h3ref-add-row";

    const addBtn = document.createElement("button");
    addBtn.className = "h3lvm-refresh-btn h3ref-add";
    addBtn.textContent = spec.addLabel;
    addBtn.title = "选择文件并加入列表末尾";

    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.multiple = true;
    fileInput.accept = spec.accept;
    fileInput.style.display = "none";

    // Only shown while something is parked, so the add row never grows a second row.
    const restoreBtn = document.createElement("button");
    restoreBtn.className = "h3lvm-refresh-btn h3ref-restore";
    restoreBtn.textContent = "↺ 全部放回";
    restoreBtn.title = "把后排已跳过的卡片全部放回序列；槽位不够的留在后排";
    restoreBtn.style.display = "none";
    restoreBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        const result = restoreAll(entries, spec.max);
        if (!result.restored) {
            updateStatus("没有可放回的卡片");
            return;
        }
        entries = result.entries;
        commit();
        render();
        if (result.blocked) updateStatus(`槽位已满（${spec.max}），仍有 ${result.blocked} 张留在后排`);
    });

    // Presets are why the project row is here. 存为 keeps the cards as paths in the
    // project bin, 载入 puts them back into this or any other node of the same kind.
    const loadPresetBtn = document.createElement("button");
    loadPresetBtn.className = "h3lvm-refresh-btn";
    loadPresetBtn.textContent = "📥 载入项目预设";
    loadPresetBtn.title = "按保存时的排列顺序和跳过状态恢复参考卡片，预设外的卡片会被移除；只读取路径，不复制文件";
    loadPresetBtn.disabled = true;

    const savePresetBtn = document.createElement("button");
    savePresetBtn.className = "h3lvm-refresh-btn";
    savePresetBtn.textContent = "📤 存为项目预设";
    savePresetBtn.title = "把当前卡片保存为当前项目的预设，含排列顺序与跳过状态；只保存路径，不复制文件";

    loadPresetBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        void loadPreset();
    });
    savePresetBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        void savePreset();
    });

    const addHint = document.createElement("span");
    addHint.className = "h3ref-hint";
    addHint.textContent = spec.dropHint;

    addRow.append(addBtn, loadPresetBtn, savePresetBtn, restoreBtn, fileInput, addHint);
    container.appendChild(addRow);

    // --- Card grid ---
    const deck = document.createElement("div");
    // One grid for both kinds. The audio deck used to widen its columns so a native
    // player bar would fit, and that is exactly what made the two panels read as
    // different products; the card box is shared now, and a waveform fits whatever
    // width the 卡片大小 control asks for.
    deck.className = "h3lvm-deck h3ref-deck";
    container.appendChild(deck);

    // --- Footer ---
    const footer = document.createElement("div");
    footer.className = "h3lvm-footer";
    for (const line of footerLines(spec)) {
        const hint = document.createElement("span");
        hint.className = "h3lvm-hint";
        hint.textContent = line;
        footer.appendChild(hint);
    }
    container.appendChild(footer);

    addPanel(node, "h3ref_panel", container, spec.panelH);

    function readEntries() {
        try {
            return parseMedia(widgetFor(MEDIA_FIELD)?.value, spec.max).entries;
        } catch (error) {
            console.warn("[H3 Ref Loader] media list is not readable:", error);
            return [];
        }
    }

    function commit() {
        const widget = widgetFor(MEDIA_FIELD);
        if (!widget) return;
        widget.value = serializeMedia(entries);
        widget.callback?.(widget.value);
        node.setDirtyCanvas?.(true, true);
        node.graph?.setChanged?.();
    }

    function updateStatus(extra = "") {
        const { active, parked } = splitEntries(entries);
        let base = slotRangeText(spec.kind, active.length, spec.max);
        if (parked.length) base += ` · 已跳过 ${parked.length}（不占槽位）`;
        // Saying what the project already holds is what makes 载入 predictable: the
        // button is disabled when the preset is empty, and the count is visible.
        if (preset) {
            // The parked half is named because it is the part a preset carries that a
            // plain file list would not, and the user has to know it came back.
            const saved = presetEntries();
            if (!saved.length) {
                base += ' · 项目预设 空';
            } else {
                const parkedSaved = saved.filter(isSkipped).length;
                base += ` · 项目预设 ${saved.length}` + (parkedSaved ? `（含 ${parkedSaved} 张已跳过）` : '');
            }
        }
        loadPresetBtn.disabled = presetEntries().length === 0;
        statusText.textContent = extra ? `${base} · ${extra}` : base;
    }

    // --- Project reference presets ---
    //
    // A preset is the card list of one project, stored by path in the project bin.
    // The panel keeps the last reply so the 载入 button can be honest before it is
    // clicked, and re-reads it whenever the project changes or 刷新 is pressed.
    let preset = null;

    function presetEntries() {
        return pickPresetEntries(preset);
}

    async function refreshPreset() {
        const project = menu.name();
        try {
            const res = await api.fetchApi(
                `/h3_lvm/ref_presets?project=${encodeURIComponent(project)}&kind=${spec.kind}`,
                { cache: 'no-store' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (signal.aborted) return;
            preset = data;
        } catch (error) {
            if (!signal.aborted) console.warn('[H3 Ref Loader] preset read failed:', error);
            preset = null;
        }
        updateStatus();
    }

    // Loading replaces the list with the preset (applyPreset), so the saved order and
    // the saved skip/active state come back as they were and nothing else is left in
    // the panel. addEntries() is the wrong tool here: it appends, which would turn a
    // saved arrangement into "the same files in whatever order the panel already had",
    // and it would put a parked card into the slot block.
    async function loadPreset() {
        const incoming = presetEntries();
        if (!incoming.length) {
            updateStatus('当前项目还没有保存过预设');
            return;
        }
        const before = serializeMedia(entries);
        const result = applyPreset(entries, incoming, spec.max);
        entries = result.entries;
        if (serializeMedia(entries) === before) {
            updateStatus('卡片已经和该预设一致');
            return;
        }
        commit();
        render();
        const notes = [`已按保存的顺序载入 ${result.restored} 张`];
        if (result.parked) notes.push(`其中 ${result.parked} 张保持跳过`);
        if (result.dropped) notes.push(`移除了 ${result.dropped} 张预设外的卡片`);
        if (result.truncated) notes.push(`超出 ${spec.max} 个槽位，未载入 ${result.truncated} 张`);
        if (result.ignored) notes.push(`${result.ignored} 张无法读取`);
        updateStatus(notes.join(' · '));
    }

    // Saving sends the whole list, parked cards included, so a preset restores a
    // project's references exactly as they were arranged.
    async function savePreset() {
        if (!entries.length) {
            updateStatus('没有卡片可保存');
            return;
        }
        const project = menu.name();
        savePresetBtn.disabled = true;
        try {
            const res = await api.fetchApi('/h3_lvm/ref_presets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ project, kind: spec.kind, entries: serializeMedia(entries) }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                updateStatus(data.error || `保存失败（HTTP ${res.status}）`);
                return;
            }
            await refreshPreset();
            updateStatus(`已保存到项目「${data.name || project}」的预设（${data.saved} 个，只存路径）`);
        } catch (error) {
            if (!signal.aborted) console.warn('[H3 Ref Loader] preset save failed:', error);
            updateStatus('保存失败：连不上后台服务。');
        } finally {
            savePresetBtn.disabled = false;
        }
    }

    function currentMegapixels() {
        const raw = Number(widgetFor(MP_FIELD)?.value);
        return Number.isFinite(raw) ? raw : 0.25;
    }

    function currentUpscale() {
        // The node default is off, and the card must show the same plan the node runs.
        const value = widgetFor(UPSCALE_FIELD)?.value;
        return value === undefined ? false : Boolean(value);
    }

    // --- Rendering ---
    function render() {
        generation++;
        // Re-rendering throws the cards away, so the players and the resize watchers
        // that belonged to them have to go with them - otherwise a clip keeps playing
        // from a card that no longer exists.
        stopPlayers();
        deck.innerHTML = "";
        const { active, parked } = splitEntries(entries);
        restoreBtn.style.display = parked.length ? "" : "none";
        if (!entries.length) {
            deck.innerHTML = '<div class="h3lvm-empty">' + spec.emptyText + "</div>";
            updateStatus();
            return;
        }
        // Slot cards first, then a labelled row and the parked cards. That is the
        // canonical order of the list itself, so a card's deck position is its index
        // in "entries" - which is what removeEntry() and the fill requests use.
        for (const [slot, entry] of active.entries()) {
            deck.appendChild(makeCard(entry, slot, slot));
        }
        if (parked.length) {
            deck.appendChild(sectionRow(parked.length));
            for (const [parkedIndex, entry] of parked.entries()) {
                deck.appendChild(makeCard(entry, active.length + parkedIndex, -1, parkedIndex));
            }
        }
        updateStatus();
        for (const [deckIndex, entry] of entries.entries()) {
            void fillCard(entry, deckIndex);
        }
    }

    function sectionRow(count) {
        const row = document.createElement("div");
        row.className = "h3ref-deck-sep";
        row.textContent = `⊘ 已跳过 ${count} 张 · 不输出、不占槽位（不能拖动）`;
        return row;
    }

    function cardFor(entry, index) {
        return deck.querySelector(`[data-ref-index="${index}"]`);
    }

    // The info block on a card is a fixed two lines (see .h3ref-deck .h3lvm-seg-info),
    // so anything past that is not cut with an ellipsis but readable in the tooltip.
    function setInfo(entry, index, text, tip = text) {
        const card = cardFor(entry, index);
        if (!card) return false;
        const line = card.querySelector(".h3lvm-seg-info");
        if (!line) return false;
        line.textContent = text;
        card.title = `${card.dataset.tipBase}\n${entry.filename}\n${tip}`;
        return true;
    }

    function makeCard(entry, deckIndex, slot, parkedIndex = -1) {
        const parked = slot < 0;
        const card = document.createElement("div");
        card.className = parked ? "h3lvm-card h3ref-skipped" : "h3lvm-card";
        card.dataset.refIndex = String(deckIndex);
        // The drag target is the slot number, so a parked card reports -1 and can be
        // neither a dragged card nor a drop target.
        card.dataset.activeIndex = String(slot);
        card.dataset.mediaKey = mediaKey(entry);
        // Dragging the card is how the slot order changes; the buttons below
        // are the only clicks a card needs.
        card.draggable = !parked;
        const tipBase = parked
            ? "已跳过 · 不占槽位"
            : `${slotTitle(spec.kind, slot)} → ${slotName(spec.kind, slot)}`;
        card.dataset.tipBase = tipBase;
        card.title = `${tipBase}\n${entry.filename}`;

        const thumbWrap = document.createElement("div");
        thumbWrap.className = "h3lvm-thumb-wrap";
        if (spec.kind === "image") {
            const known = sourceCache.get(mediaKey(entry));
            appendThumbnail(thumbWrap, {
                thumbnail_url: viewUrl(entry),
                width: known?.width,
                height: known?.height,
            });
        } else {
            makeWaveform(thumbWrap, entry);
        }
        card.appendChild(thumbWrap);

        const meta = document.createElement("div");
        meta.className = "h3lvm-meta";
        const labelEl = document.createElement("div");
        labelEl.className = "h3lvm-seg-label";
        labelEl.textContent = parked
            ? "⊘ 已跳过 · 不占槽位"
            : `${slotTitle(spec.kind, slot)} → ${slotName(spec.kind, slot)}`;
        const infoEl = document.createElement("div");
        infoEl.className = "h3lvm-seg-info";
        infoEl.textContent = spec.kind === "image" ? "读取尺寸中…" : "读取音频信息中…";
        meta.append(labelEl, infoEl);
        card.appendChild(meta);

        // A parked card keeps its window (so 放回 brings back the same clip) but has no
        // slot to trim, so the inputs only appear on cards that output something.
        if (spec.kind === "audio") {
            // A parked card keeps its window (so 放回 brings back the same clip), but the
            // inputs are disabled. The row stays so both blocks keep the same card height
            // and the grid does not reflow when a card moves out and back in.
            card.appendChild(trimRow(entry, deckIndex, parked));
        }

        const acts = document.createElement("div");
        acts.className = "h3ref-acts";
        if (parked) {
            acts.append(
                actionButton("↩", "放回序列（占用下一个空槽位）", () => bringBack(parkedIndex)),
                actionButton("✕", "移除这张卡片（不再保留这个文件）", () => drop(deckIndex)),
            );
        } else {
            acts.append(
                actionButton("↻", "替换成新文件（槽位不变）", () => pickReplacement(deckIndex)),
                actionButton("⊘", "跳过：不输出、不占槽位，卡片移到后排", () => park(slot)),
                actionButton("✕", "移除这张卡片（槽位变空，输出 None）", () => drop(deckIndex)),
            );
        }
        card.appendChild(acts);
        return card;
    }

    function actionButton(text, title, onClick, disabled) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "h3ref-act";
        button.textContent = text;
        button.title = title;
        button.disabled = Boolean(disabled);
        button.addEventListener("click", event => {
            event.stopPropagation();
            onClick();
        });
        return button;
    }

    // --- Audio cards: waveform, a play button, and the trim window ---
    //
    // The card is the same box as an image card (same grid, same --thumb-h). A native
    // <audio controls> bar was the one thing that broke that, and it cannot show where
    // the trimmed window is - the waveform can, in one colour.
    const players = new Set();
    const observers = new Set();

    function stopPlayers() {
        for (const player of players) {
            try {
                player.pause();
            } catch (error) {
                // the card is going away anyway
            }
        }
        players.clear();
        for (const observer of observers) {
            observer.disconnect?.();
        }
        observers.clear();
    }

    // 96 buckets is enough to read a clip at card width, and it is a few hundred
    // numbers rather than the samples themselves.
    function waveformPeaks(buffer, buckets = 96) {
        try {
            const data = buffer.getChannelData(0);
            if (!data?.length) return null;
            const step = Math.max(1, Math.floor(data.length / buckets));
            const peaks = [];
            for (let start = 0; start < data.length; start += step) {
                let peak = 0;
                for (let i = start; i < Math.min(data.length, start + step); i++) {
                    const value = Math.abs(data[i]);
                    if (value > peak) peak = value;
                }
                peaks.push(peak);
            }
            return peaks;
        } catch (error) {
            return null;
        }
    }

    // The window is drawn, not described: blue bars are what H3 receives, grey bars are
    // what it does not. With no peaks yet the shape is a flat line, so the card still
    // says "audio" while the decode is on its way.
    function drawWave(canvas, peaks, win, total) {
        const box = canvas.getBoundingClientRect();
        if (!box.width || !box.height) return;
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.round(box.width * ratio);
        canvas.height = Math.round(box.height * ratio);
        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        const from = total > 0 ? (win?.first ?? 0) / total : 0;
        const to = total > 0 ? (win?.last ?? total) / total : 1;
        const bars = Math.max(14, Math.min(72, Math.floor(box.width / 4)));
        const barWidth = canvas.width / bars;
        const middle = canvas.height / 2;

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        for (let index = 0; index < bars; index++) {
            const at = (index + 0.5) / bars;
            const peak = peaks?.length
                ? Math.max(0.03, Math.min(1, peaks[Math.min(peaks.length - 1, Math.floor(at * peaks.length))] || 0))
                : 0.05;
            const height = Math.max(2, peak * middle * 1.7);
            ctx.fillStyle = at >= from && at <= to ? "#60a5fa" : "#4b5563";
            ctx.fillRect(index * barWidth + 1, middle - height / 2, Math.max(1, barWidth - 2), height);
        }
    }

    function windowFor(player, entry) {
        const trim = trimRange(entry);
        const total = Number.isFinite(player.duration) ? player.duration : 0;
        return resolveTrim(total, trim.start, trim.duration) || { first: 0, last: total, empty: false };
    }

    function makeWaveform(thumbWrap, entry) {
        const canvas = document.createElement("canvas");
        canvas.className = "h3ref-wave";
        thumbWrap.appendChild(canvas);

        const play = document.createElement("button");
        play.type = "button";
        play.className = "h3ref-play";
        play.textContent = "▶";
        play.title = "试听：只播放会被输出的那一段";
        thumbWrap.appendChild(play);

        const player = new Audio();
        player.preload = "none";
        player.src = viewUrl(entry);
        players.add(player);

        const redraw = () => {
            const meta = audioCache.get(mediaKey(entry));
            drawWave(canvas, meta?.peaks, windowFor(player, entry), meta?.duration || 0);
        };
        if (typeof ResizeObserver !== "undefined") {
            // The 卡片大小 control changes the card width; the waveform has to follow it
            // without waiting for a re-render.
            const observer = new ResizeObserver(() => redraw());
            observer.observe(canvas);
            observers.add(observer);
        }

        play.addEventListener("click", (event) => {
            event.stopPropagation();
            const win = windowFor(player, entry);
            if (player.paused) {
                for (const other of players) {
                    if (other !== player) other.pause();
                }
                if (!(player.currentTime >= win.first && player.currentTime < win.last)) {
                    player.currentTime = win.first;
                }
                player.play?.().catch(() => {
                    // the browser blocked it, or the file is gone - the card stays usable
                });
                play.textContent = "⏸";
            } else {
                player.pause();
                play.textContent = "▶";
            }
        });
        player.addEventListener("timeupdate", () => {
            const win = windowFor(player, entry);
            if (!player.paused && player.currentTime >= win.last) {
                player.pause();
                play.textContent = "▶";
            }
            redraw();
        });
        player.addEventListener("ended", () => {
            play.textContent = "▶";
        });
        player.addEventListener("loadedmetadata", () => redraw());
        canvas.addEventListener("click", (event) => {
            event.stopPropagation();
            const win = windowFor(player, entry);
            const box = canvas.getBoundingClientRect();
            const ratio = Math.min(Math.max((event.clientX - box.left) / Math.max(1, box.width), 0), 1);
            player.currentTime = win.first + ratio * Math.max(0, win.last - win.first);
        });
        canvas.addEventListener("dblclick", event => event.stopPropagation());
    }

    // The two numbers a card needs: where the clip starts and how long it is. Seconds,
    // because that is what every other audio node in ComfyUI asks for.
    function numberField(captionText, title, value, onCommit, disabled = false) {
        const field = document.createElement("label");
        field.className = "h3ref-trim-field";
        const caption = document.createElement("span");
        caption.textContent = captionText;
        const input = document.createElement("input");
        input.className = "h3ref-num";
        input.type = "number";
        input.step = "0.1";
        input.value = String(value || 0);
        input.title = title;
        input.disabled = Boolean(disabled);
        input.draggable = false;
        // The whole card is a drag handle, so the inputs have to say "this is a field".
        input.addEventListener("click", event => event.stopPropagation());
        input.addEventListener("mousedown", event => event.stopPropagation());
        input.addEventListener("dragstart", event => {
            event.preventDefault();
            event.stopPropagation();
        });
        input.addEventListener("change", () => onCommit(input.value));
        field.append(caption, input);
        return field;
    }

    function trimRow(entry, deckIndex, disabled = false) {
        const trim = trimRange(entry);
        const row = document.createElement("div");
        row.className = "h3ref-trim";
        row.append(
            numberField("开始", "开始时间（秒）。负数从片尾往前算；0 = 从最前面开始。", trim.start,
                value => setTrim(deckIndex, value, null), disabled),
            numberField("时长", "时长（秒）。0 = 一直到片尾。", trim.duration,
                value => setTrim(deckIndex, null, value), disabled),
            actionButton("↺", "清除裁切：输出整段音频", () => setTrim(deckIndex, 0, 0), disabled),
        );
        return row;
    }

    // One edit through replaceEntry, which is also what validates it: a bad number is a
    // message in the status line and the card goes back to the numbers it had.
    function setTrim(deckIndex, startValue, durationValue) {
        const current = entries[deckIndex];
        if (!current) return;
        const trim = trimRange(current);
        try {
            entries = replaceEntry(entries, deckIndex, {
                ...current,
                start: startValue === null ? trim.start : startValue,
                duration: durationValue === null ? trim.duration : durationValue,
            });
        } catch (error) {
            updateStatus(`裁切无效：${error.message}`);
            render();
            return;
        }
        commit();
        render();
    }

    function footerLines(spec) {
        if (spec.kind === "image") {
            return [
                "卡片顺序 = ref_image_0..8 的槽位顺序；空槽输出 None，H3 会跳过。",
                "所有图片按比例整体缩放到 32 像素网格，不裁切、不补边；卡片上显示的就是节点真实产出的尺寸。",
            "关闭「放大小图」时，小图只对齐 32 网格、不放大到目标 MP，卡片会标「未放大，仅对齐网格」。",
            "拖动卡片调换槽位顺序；↻ 替换文件，⊘ 跳过（移到后排、不占槽位），↩ 放回，✕ 移除。",
            ];
        }
        return [
            "卡片顺序 = ref_audio_0..2 的槽位顺序；空槽输出 None，H3 会跳过。",
            "每张卡片都能填开始时间与时长（秒）：只有这一段交给 H3。开始时间填负数是从片尾往前算，时长填 0 表示一直到片尾。",
            "波形里的蓝色区间就是会被输出的部分，灰色不会；▶ 只试听这一段，点波形可以定位。不重采样、不混音，采样率与声道原样交给 H3。",
            "拖动卡片调换槽位顺序；↻ 替换文件，⊘ 跳过（移到后排、不占槽位），↩ 放回，✕ 移除。",
        ];
    }

    // --- Edits ---

    function drop(index) {
        entries = removeEntry(entries, index);
        commit();
        render();
    }

    // 跳过 keeps the file in the list, so bringing it back needs no re-upload and no
    // re-picking; 移除 is the one that forgets it.
    function park(slot) {
        entries = skipAt(entries, slot);
        commit();
        render();
    }

    function bringBack(parkedIndex) {
        const result = restoreAt(entries, parkedIndex, spec.max);
        if (!result.restored) {
            updateStatus(`槽位已满（${spec.max}），请先移除或跳过一张再放回`);
            return;
        }
        entries = result.entries;
        commit();
        render();
    }

    // One hidden picker reused for every card: cancelling must not leave a stray
    // input behind, so the pending index is state, not a DOM node.
    let replaceIndex = -1;
    const replaceInput = document.createElement("input");
    replaceInput.type = "file";
    replaceInput.accept = spec.accept;
    replaceInput.style.display = "none";
    replaceInput.addEventListener("change", () => {
        const files = [...(replaceInput.files ?? [])];
        replaceInput.value = "";
        const index = replaceIndex;
        replaceIndex = -1;
        if (index < 0 || !files.length) return;
        void replaceWith(index, files[0]);
    });
    container.appendChild(replaceInput);

    function pickReplacement(index) {
        replaceIndex = index;
        replaceInput.click();
    }

    async function replaceWith(index, file) {
        try {
            const uploaded = await uploadFile(file);
            entries = replaceEntry(entries, index, uploaded);
            commit();
            render();
        } catch (error) {
            updateStatus(error.message || "替换失败");
        }
    }

    async function addFiles(fileList) {
        const files = [...(fileList ?? [])];
        if (!files.length) return;
        const usable = files.filter(file => mediaKind(file.name) === spec.kind);
        const wrong = files.length - usable.length;
        if (!usable.length) {
            updateStatus(`只能添加${spec.kind === "image" ? "图片" : "音频"}文件`);
            return;
        }
        updateStatus(`上传中 0/${usable.length}`);
        const incoming = [];
        const failed = [];
        for (const [position, file] of usable.entries()) {
            try {
                incoming.push(await uploadFile(file));
            } catch (error) {
                failed.push(file.name);
            }
            updateStatus(`上传中 ${position + 1}/${usable.length}`);
        }
        const result = addEntries(entries, incoming, spec.max);
        entries = result.entries;
        commit();
        render();
        const notes = [];
        if (result.skipped) notes.push(`跳过 ${result.skipped} 个（重复或超出 ${spec.max} 个槽位）`);
        if (wrong) notes.push(`忽略 ${wrong} 个非${spec.kind === "image" ? "图片" : "音频"}文件`);
        if (failed.length) notes.push(`上传失败 ${failed.length} 个`);
        if (notes.length) updateStatus(notes.join(" · "));
    }

    async function uploadFile(file) {
        const form = new FormData();
        form.append("image", file);
        form.append("subfolder", "");
        form.append("type", "input");
        const res = await api.fetchApi("/upload/image", { method: "POST", body: form });
        if (res.status !== 200) {
            throw new Error(`上传失败：${res.status} ${res.statusText}`);
        }
        const data = await res.json().catch(() => ({}));
        if (!data.name) throw new Error("上传失败：服务器没有返回文件名");
        return { filename: data.name, subfolder: data.subfolder || "", type: data.type || "input" };
    }

    // --- Card details, asked from the same code the node runs ---
    function viewUrl(entry) {
        const path = `/view?filename=${encodeURIComponent(entry.filename)}`
            + `&subfolder=${encodeURIComponent(entry.subfolder || "")}`
            + `&type=${encodeURIComponent(entry.type || "input")}`;
        if (typeof api.apiURL === "function") return api.apiURL(path);
        if (typeof api.getFileUrl === "function") return api.getFileUrl(path);
        return path;
    }


    async function fillCard(entry, index) {
        if (spec.kind === "image") {
            await fillImageCard(entry, index);
        } else {
            await fillAudioCard(entry, index);
        }
    }

    async function loadImageSource(entry) {
        const key = mediaKey(entry);
        if (sourceCache.has(key)) return sourceCache.get(key);
        const result = await new Promise((resolve) => {
            const image = new Image();
            image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight });
            image.onerror = () => resolve({ error: "图片读取失败" });
            image.src = viewUrl(entry);
        });
        sourceCache.set(key, result);
        return result;
    }

    async function loadPlan(source, megapixels, upscale) {
        const key = `${source.width}x${source.height}|${megapixels}|${upscale ? 1 : 0}`;
        if (planCache.has(key)) return planCache.get(key);
        const res = await api.fetchApi(
            `/h3_lvm/ref_plan?w=${encodeURIComponent(source.width)}&h=${encodeURIComponent(source.height)}&mp=${encodeURIComponent(megapixels)}&upscale=${upscale ? 1 : 0}`,
            { cache: "no-store" },
        );
        const plan = res.ok ? await res.json().catch(() => null) : { error: "尺寸计算失败" };
        planCache.set(key, plan);
        return plan;
    }

    async function fillImageCard(entry, index) {
        const at = generation;
        const source = await loadImageSource(entry);
        if (at !== generation) return;
        if (source.error) {
            setInfo(entry, index, source.error);
            return;
        }
        const plan = await loadPlan(source, currentMegapixels(), currentUpscale());
        if (at !== generation) return;
        if (plan?.error) {
            setInfo(entry, index, plan.error);
            return;
        }
        setInfo(entry, index, sizeLine({ source, plan }), sizeLine({ source, plan, full: true }));
    }

    async function fillAudioCard(entry, index) {
        const at = generation;
        const key = mediaKey(entry);
        let meta = audioCache.get(key);
        if (!meta) {
            meta = await readAudioMeta(viewUrl(entry));
            audioCache.set(key, meta);
        }
        if (at !== generation) return;
        const trim = trimRange(entry);
        const text = audioInfoLine({ ...meta, trimStart: trim.start, trimLength: trim.duration });
        setInfo(entry, index, text);
        const card = cardFor(entry, index);
        const canvas = card?.querySelector(".h3ref-wave");
        if (canvas) {
            drawWave(canvas, meta.peaks, resolveTrim(meta.duration, trim.start, trim.duration), meta.duration || 0);
        }
    }

    async function readAudioMeta(url) {
        // The <audio> element gives the duration for free; sample rate and channel
        // count need a decode, so only do that for files small enough to be safe.
        try {
            const res = await fetch(url);
            const buffer = await res.arrayBuffer();
            if (buffer.byteLength <= 40 * 1024 * 1024) {
                const Ctor = window.AudioContext || window.webkitAudioContext;
                if (Ctor) {
                    const context = new Ctor();
                    try {
                        const decoded = await context.decodeAudioData(buffer.slice(0));
                        return {
                            duration: decoded.duration,
                            sampleRate: decoded.sampleRate,
                            channels: decoded.numberOfChannels,
                            peaks: waveformPeaks(decoded),
                        };
                    } finally {
                        context.close?.();
                    }
                }
            }
        } catch (error) {
            // fall through to the element metadata
        }
        const duration = await new Promise((resolve) => {
            const probe = new Audio();
            probe.preload = "metadata";
            probe.onloadedmetadata = () => resolve(probe.duration);
            probe.onerror = () => resolve(0);
            probe.src = url;
        });
        return { duration };
    }

    // --- Wiring ---
    refreshBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        sourceCache.clear();
        planCache.clear();
        audioCache.clear();
        entries = readEntries();
        void refreshPreset();
        render();
    });

    addBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        fileInput.click();
    });
    fileInput.addEventListener("change", () => {
        const files = [...(fileInput.files ?? [])];
        fileInput.value = "";
        void addFiles(files);
    });

    // --- Two different things can land on this panel ---
    //   1. a file from outside ComfyUI -> upload it and append a card. Only the grid
    //      takes files; a file dropped on the toolbar should do nothing. ComfyUI also
    //      listens for file drops on the document and would create a LoadImage node
    //      from the same file, so the drag events stop here.
    //   2. one of our own cards        -> change the slot order.
    // They are told apart by the drag payload: an external file drag always reports
    // "Files", a card drag carries our own mime type instead.
    //
    // A card drag is accepted anywhere in the panel, and the landing spot comes from
    // insertPosition() over every card rect. Aiming only at the card under the pointer
    // is what made it feel broken: a gap between two cards jumped the card to the end,
    // and a pointer over the toolbar or a few pixels outside the grid did nothing.
    const CARD_MIME = "application/x-h3ref-card";
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

    function clearDropHints() {
        deck.classList.remove("h3ref-drop");
        for (const card of deck.querySelectorAll(".h3ref-drop-before, .h3ref-drop-after")) {
            card.classList.remove("h3ref-drop-before", "h3ref-drop-after");
        }
    }

    function cardRects() {
        const rects = [];
        // Parked cards are not drop targets: they hold no slot, so a position among
        // them would mean nothing.
        for (const card of deck.querySelectorAll(".h3lvm-card:not(.h3ref-skipped)")) {
            const rect = card.getBoundingClientRect();
            rects.push({
                index: Number(card.dataset.activeIndex),
                left: rect.left,
                top: rect.top,
                right: rect.right,
                bottom: rect.bottom,
            });
        }
        return rects;
    }

    // The position in the list as it is drawn now, or -1 when this drop would change
    // nothing (the pointer is on the dragged card itself).
    function insertAt(event, from) {
        return insertPosition(cardRects(), event.clientX, event.clientY, from);
    }

    function showInsertHint(at) {
        clearDropHints();
        if (at < 0) return;
        const last = countActive(entries) - 1;
        if (at > last) {
            deck.querySelector(`[data-active-index="${last}"]`)?.classList.add("h3ref-drop-after");
            return;
        }
        deck.querySelector(`[data-active-index="${at}"]`)?.classList.add("h3ref-drop-before");
    }

    // The grid scrolls, so a row that is out of view has to be reachable while the
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

    // Insurance: a drag can start inside a DOM widget without a usable dragstart.
    // The pointerdown that began it already knows which card was held.
    container.addEventListener("pointerdown", (event) => {
        const card = event.target?.closest?.(".h3lvm-card");
        heldIndex = card ? Number(card.dataset.activeIndex) : -1;
    }, { signal });

    container.addEventListener("dragstart", (event) => {
        const card = event.target?.closest?.(".h3lvm-card");
        if (!card || !deck.contains(card)) return;
        dragIndex = Number(card.dataset.activeIndex);
        if (dragIndex < 0) return; // a parked card has no slot to move
        heldIndex = dragIndex;
        event.dataTransfer.setData(CARD_MIME, String(dragIndex));
        event.dataTransfer.setData("text/plain", String(dragIndex));
        event.dataTransfer.effectAllowed = "move";
        card.classList.add("h3ref-dragging");
        startAutoScroll();
    }, { signal });

    container.addEventListener("dragover", (event) => {
        if (isFileDrag(event)) {
            if (!insideDeck(event)) return;
            event.preventDefault();
            event.stopPropagation();
            event.dataTransfer.dropEffect = "copy";
            deck.classList.add("h3ref-drop");
            return;
        }
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
        clearDropHints();
    }, { signal });

    container.addEventListener("drop", (event) => {
        if (isFileDrag(event) && !insideDeck(event)) return;
        event.preventDefault();
        event.stopPropagation();
        clearDropHints();
        if (dragIndex < 0 && dragTypes(event).includes(CARD_MIME)) dragIndex = heldIndex;
        const from = dragIndex;
        dragIndex = -1;
        if (from < 0) {
            void addFiles(event.dataTransfer?.files);
            return;
        }
        const at = insertAt(event, from);
        if (at < 0) return;
        // Dropping in front of a card that sits after the dragged one means the gap
        // left behind already moved the target one place to the left.
        const to = at > from ? at - 1 : at;
        if (to === from) return;
        entries = moveActive(entries, from, to - from);
        commit();
        render();
    }, { signal });

    container.addEventListener("dragend", () => {
        dragIndex = -1;
        heldIndex = -1;
        stopAutoScroll();
        for (const card of deck.querySelectorAll(".h3ref-dragging")) {
            card.classList.remove("h3ref-dragging");
        }
        clearDropHints();
    }, { signal });

    // Changing the target megapixels or the upscale switch must re-plan the cards, not
    // just the tensor. The resampling filter is deliberately not here: it changes the
    // pixels, never the size, so the card text would not change.
    for (const field of [MP_FIELD, UPSCALE_FIELD]) {
        const widget = widgetFor(field);
        if (!widget) continue;
        const originalCallback = widget.callback;
        widget.callback = function (value) {
            const r = originalCallback?.apply(this, arguments);
            planCache.clear();
            for (const [index] of entries.entries()) void fillCard(entries[index], index);
            return r;
        };
    }

    // The panel is the only editor of the media list, so the canvas widget steps
    // aside - but only once the panel is really running.
    const mediaWidget = widgetFor(MEDIA_FIELD);
    if (mediaWidget?.options) mediaWidget.options.hidden = true;
    // The menu is the only editor of the bin now; the value is still serialised by
    // position, so graphs saved before this keep their project.
    const projectWidget = widgetFor(PROJECT_FIELD);
    if (projectWidget?.options) projectWidget.options.hidden = true;

    node._h3lvmRefRefresh = () => {
        entries = readEntries();
        render();
        void refreshPreset();
    };

    render();
    void refreshPreset();
}







