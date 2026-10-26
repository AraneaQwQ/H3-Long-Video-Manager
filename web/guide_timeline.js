// RAFOLIE 2026-10-22: the Guide Timeline editor.
//
// What this file is: the panel for the one node that replaces a chain of native
// MiniMaxH3AddGuide nodes. Every rule (what may run, what is out of range, what
// overlaps, what the quotas are) lives in web/guide_state.js, which mirrors
// core/guide_timeline.py, so a card can never disagree with the node. This file is
// only DOM, media and input handling.
//
// UI rules this plugin already learned, restated here because they are the reason the
// file is shaped the way it is:
//   - the node body is a fixed-height summary strip: 刷新 / 缩放 / 展开 must never
//     resize the node, which is the bug class that keeps coming back;
//   - the editor is a floating panel on document.body, so it cannot change the node
//     size either, and closing it never clears data;
//   - the card pool is the shared .h3lvm-deck grid with the shared 100%-400% card
//     zoom and portrait-aware thumbnails, so it looks like every other panel here;
//   - one coordinate transform (createScale) for the ruler, both lanes, the image
//     markers and the audio clips. The prototype put images at 4%-96% and audio at
//     0%-100%, which is exactly what must not ship;
//   - a drag moves the elements that move. Rebuilding the pool on every pointermove
//     loses input focus and costs a frame per pixel.
//
// frame_index stays the authority and seconds are only an input and a label; audio
// trim stays in sample points. Nothing here re-derives those rules.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addPanel } from "./dom_panel.js";
import { createCardZoom } from "./card_zoom.js";
import { appendThumbnail } from "./thumb_fit.js";
import { insertPosition } from "./ref_state.js";
import {
    alignFrameCount, AUDIO_DECODING, AUDIO_FAILED, AUDIO_KIND, AUDIO_METADATA_ONLY, AUDIO_READY, DEFAULT_DOCUMENT, DEFAULT_FPS, IMAGE_KIND, KINDS,
    MAX_GUIDE_AUDIOS, MAX_GUIDE_IMAGES, MAX_GUIDE_TOTAL, STRENGTH_OFF,
    TRACK_PADDING, addGuides, audioSpans, audioStatus, clampScroll, countRunnable, createScale, guideStatusCounts,
    declutterMarkers, duplicateGuide, formatSeconds, frameFromLanePointer, frameToSeconds, guideFramesFor, mediaKind, mediaKeyOf,
    moveGuide, nextFreeFrame, panBy, panWindow, parseDocument, patchGuide, pendingAudioCount, ensureLabels, removeGuide,
    scrollForPanThumb, scrollForPointerPan, scrollToFrame, secondsToFrame,
    squareMarkerPlan, stripCardPlan, stripLaneHeights, stripMarkerPlan, stripRoom, DEFAULT_LANE_HEIGHTS,
    hasStripMarkerSide, stepStripMarkerSide, stripMarkerSide,
    STRENGTH_MAX, STRENGTH_MIN, STRENGTH_STEP, isMutedImage, normalizeStrength, strengthOf,
    MARKER_INSET, MARKER_SIDE_HARD_MAX, clampLaneHeight, laneHeights, stepLaneHeight,
    serializeDocument, summaryOf, tickMarks, trimFromSeconds, trimWindow, validateGuides, validateGuidesV2, validationState, zoomStepAt,
    DRAG_START_PX, passedDragThreshold, resolveDropTarget, resolveTimelineRange,
} from "./guide_state.js";

try {
    // The deck/card styling is the picker's; only the timeline and the editor shell
    // are new. Loading the picker sheet is what makes the two panels one family.
    const sheets = [
        ["h3lvm-styles", "./h3lvm_picker.css"],
        ["h3guide-styles", "./guide_timeline.css"],
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
    console.warn("[H3 Guide Timeline] CSS injection failed:", error);
}

const GUIDE_NODE = "H3 Guide Timeline";
const GUIDE_NODE_V2 = "H3 Guide Timeline v2";
// The stable node and the strength node share this one file. The panel difference is a
// single control, so it is one flag below rather than a second copy of 3000 lines.
const GUIDE_NODES = new Set([GUIDE_NODE, GUIDE_NODE_V2]);
const GUIDES_FIELD = "guides";

// A constant, not a measured value: pressing 刷新 or 打开编辑器 must not resize the
// node, and a self-sizing panel is how that bug starts.
const NODE_PANEL_H = 112;
const SCROLL_EDGE = 28;
const PAN_THUMB_MIN_PX = 28;
const MAX_DECODE_BYTES = 40 * 1024 * 1024;
const SECOND_STEP = 1 / DEFAULT_FPS;

const LABELS = {
    guides: "🎬 Guide 列表 (JSON)",
    length_seconds: "⏱ 时间轴长度（秒）",
};
const TOOLTIPS = {
    length_seconds: "只给编辑器的时间尺用：填目标时间轴长度（秒），面板按 秒 × 24fps 换算成帧并向上对齐到 H3 的 17n+5"
        + "（10 秒 → 240 → 243 帧）。0 表示不设置，此时时间尺用上一次运行得到的真实帧数。"
        + "这个值不参与执行，也不会改变输出。",
    guides: "由「打开 Guide 编辑器」的面板读写的 JSON 列表。frame_index 是权威时间位置，"
        + "秒数只是显示与输入；音频的 source_start_sample / source_end_sample 是采样点边界。"
        + "enabled=false 是停用，frame_index 为 null 是待放置，两者都保留但不执行。"
        + "resolved_frame_count 与 view_state 只是面板状态，不参与执行。",
};

app.registerExtension({
    name: "H3.LVM.GuideTimeline",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!GUIDE_NODES.has(nodeData.name)) return;

        const originalCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = originalCreated ? originalCreated.apply(this, arguments) : undefined;
            try {
                translateWidgets(this);
                hideGuidesWidget(this);
                installGuideNode(this);
            } catch (error) {
                console.warn("[H3 Guide Timeline] panel setup failed (the node still runs):", error);
            }
            return r;
        };

        const originalConfigure = nodeType.prototype.configure;
        nodeType.prototype.configure = function (info) {
            const r = originalConfigure ? originalConfigure.apply(this, arguments) : undefined;
            // The guides belong to the saved graph, not to this page visit: reopening a
            // workflow shows the cards and the timeline again without a refresh click.
            this._h3guideReload?.();
            return r;
        };

        const originalExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const r = originalExecuted ? originalExecuted.apply(this, arguments) : undefined;
            // execution.py sends the node's ui dict as the executed message's output, so
            // this is where the real latent length arrives. The ruler uses it from then on.
            const entry = message?.h3_guide_timeline?.[0] ?? message?.ui?.h3_guide_timeline?.[0];
            const frames = Math.trunc(Number(entry?.frame_count) || 0);
            if (frames > 0) this._h3guideResolved?.(frames);
            return r;
        };

        const originalRemoved = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            // Closing the node must take the floating editor, its players and its
            // ResizeObserver with it.
            this._h3guideDispose?.();
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

// The panel is the only editor for this list, so the raw JSON box is noise on the
// node and its tooltip only competes with the panel. options.hidden is what the
// frontend layout filters on; the value is still serialised by position, so saved
// graphs and the panel's read/write keep working exactly as before.
function hideGuidesWidget(node) {
    const widget = node.widgets?.find((item) => item.name === GUIDES_FIELD);
    if (!widget) return;
    widget.options = widget.options || {};
    widget.options.hidden = true;
}

// --- The node body and the editor it opens: one closure, one state source ---
// doc is the only copy of the guide list. Cards, markers, clips, the detail fields and
// the serialized widget value are all derived from it, so there is nothing to keep in
// sync by hand.
function installGuideNode(node) {
    const lifetime = node._h3guideLifetime ?? new AbortController();
    node._h3guideLifetime = lifetime;
    const signal = lifetime.signal;

    const widgetFor = (name) => node.widgets?.find((item) => item.name === name);
    // v2 only: per-image guide strength. Everything else is the same panel, so this flag is
    // the whole difference. It is read from the node type, not from the document, because a
    // v1 node must not grow the control just because a v2 document was pasted into it.
    const perImageStrength = String(node.type || "").trim() === GUIDE_NODE_V2;

    // Declared before the first readDoc() call: readDoc writes it, so a let below that
    // call would be in the temporal dead zone and the whole panel would fail to build.
    // Why an unreadable list is kept rather than replaced is explained above readDoc().
    let parseError = null;

    let doc = readDoc();
    // mediaKey -> {duration, sampleRate, sampleCount, peaks} | {error}. Waveforms are
    // CPU work; one decode per file, not per render.
    const audioCache = new Map();
    // Bumped on every pool render so a slow decode cannot write into an old card.
    let generation = 0;

    function make(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = text;
        return element;
    }

    // ---------- the node body: a summary strip and one button ----------
    const container = document.createElement("div");
    container.className = "h3lvm-container";

    const toolbar = document.createElement("div");
    toolbar.className = "h3lvm-toolbar";

    const openBtn = document.createElement("button");
    openBtn.className = "h3lvm-refresh-btn h3lvm-primary";
    openBtn.textContent = "🎬 打开 Guide 编辑器";
    openBtn.title = "在时间轴上排列图片与音频 Guide；关闭编辑器不会清空数据，也不影响执行";

    const refreshBtn = document.createElement("button");
    refreshBtn.className = "h3lvm-refresh-btn";
    refreshBtn.textContent = "🔄 刷新";
    refreshBtn.title = "重新读取列表、素材信息与视频总帧数";

    // The timeline inside the node is an optional helper view, not the main editor. It is
    // closed by default and only this button opens it, so the default node stays compact and
    // nothing about loading media can change the node size.
    const stripBtn = make("button", "h3lvm-refresh-btn");
    stripBtn.textContent = "📈 显示节点时间轴";
    stripBtn.title = "节点内的时间轴只是辅助视图；缩放、卡片池与详情在 Guide 编辑器里";

    const statusText = document.createElement("span");
    statusText.className = "h3lvm-status";

    toolbar.append(openBtn, stripBtn, refreshBtn, statusText);

    const nodeFooter = document.createElement("div");
    nodeFooter.className = "h3lvm-footer";
    for (const line of [
        "连接 positive / latent / 视频 VAE / 音频 VAE；只有图片 Guide 时可以不连音频 VAE，反之亦然。",
        "没有任何启用且已放置的 Guide 时，positive 原样透传。",
    ]) {
        nodeFooter.appendChild(make("span", "h3lvm-hint", line));
    }

    // ---------- the timeline inside the node ----------
    // addPanel hands this panel every pixel the user drags the node taller, so the
    // leftover space is ours to use rather than leave blank. This is the same renderer
    // as the editor's, on a second surface: fit to width, no zoom, but the markers,
    // clips and dragging are real, so a guide can be placed here too. It never writes
    // node.size; when the panel is too short for it, it hides itself instead.
    let nodeSurface = null;
    let stripOn = false;
    let stripFrame = 0;
    // What the strip is drawing right now, which is not always what the document asked for:
    // the panel owns its height, so stripLaneHeights may clamp the two lanes.
    let stripHeights = { ...DEFAULT_LANE_HEIGHTS };

    const strip = make("div", "h3guide-strip h3guide-strip-off");
    const stripHead = make("div", "h3guide-strip-head");
    const stripLaneSize = (label) => {
        const shrink = make("button", "h3guide-secondary", label + " −");
        const grow = make("button", "h3guide-secondary", "＋");
        const px = make("span", "h3guide-lane-count h3guide-lane-px");
        shrink.title = "把节点内这条轨道变矮；独立设置的图片卡片尺寸不变";
        return { shrink, grow, px };
    };
    const stripImageSize = stripLaneSize("图片轨");
    const stripAudioSize = stripLaneSize("音频轨");
    const stripCardSize = {
        shrink: make("button", "h3guide-secondary", "卡片 −"),
        grow: make("button", "h3guide-secondary", "＋"),
        px: make("span", "h3guide-lane-count h3guide-lane-px h3guide-card-px"),
    };
    stripImageSize.grow.title = "只把节点内的图片轨道变高";
    stripAudioSize.grow.title = "把这条轨道变高，波形更清楚";
    const stripHint = make("span", "h3guide-strip-hint", "整段视频按宽度铺满 · 缩放与卡片池在「打开 Guide 编辑器」");
    stripHead.append(
        make("span", "h3guide-strip-title", "节点时间轴"),
        stripCardSize.shrink, stripCardSize.px, stripCardSize.grow,
        stripImageSize.shrink, stripImageSize.px, stripImageSize.grow,
        stripAudioSize.shrink, stripAudioSize.px, stripAudioSize.grow,
        stripHint,
    );
    const stripBody = make("div", "h3guide-strip-body h3guide-strip-body-off");
    const stripRuler = make("div", "h3guide-ruler");
    const stripRulerRow = make("div", "h3guide-row h3guide-strip-row");
    stripRulerRow.append(make("span", "h3guide-lane-label", "时间尺"), stripRuler);
    const stripImageTrack = make("div", "h3guide-track");
    const stripImageRow = make("div", "h3guide-row h3guide-strip-row h3guide-strip-row-track h3guide-strip-row-image");
    stripImageRow.append(make("span", "h3guide-lane-label", "图片轨"), stripImageTrack);
    const stripAudioTrack = make("div", "h3guide-track h3guide-track-audio");
    const stripAudioRow = make("div", "h3guide-row h3guide-strip-row h3guide-strip-row-track");
    stripAudioRow.append(make("span", "h3guide-lane-label", "音频轨"), stripAudioTrack);
    stripBody.append(stripRulerRow, stripImageRow, stripAudioRow);
    strip.append(stripHead, stripBody);
    nodeSurface = createSurface({
        ruler: stripRuler,
        trackImage: stripImageTrack,
        trackAudio: stripAudioTrack,
        fitWidth: true,
        // Only a starting value: renderSurface() re-plans the padding from the lane every time.
        padding: MARKER_SIDE_HARD_MAX / 2 + 4,
        tickGapPx: 64,
    });

    container.append(toolbar, nodeFooter, strip);
    addPanel(node, "h3guide_panel", container, NODE_PANEL_H);


    function readDoc() {
        try {
            parseError = null;
            return parseDocument(widgetFor(GUIDES_FIELD)?.value);
        } catch (error) {
            parseError = String(error?.message || error);
            console.warn("[H3 Guide Timeline] the guide list is not readable:", error);
            return parseDocument("");
        }
    }

    function resetDocumentToEmpty() {
        const widget = widgetFor(GUIDES_FIELD);
        if (!widget) return;
        widget.value = DEFAULT_DOCUMENT;
        widget.callback?.(widget.value);
        node.setDirtyCanvas?.(true, true);
        node.graph?.setChanged?.();
        doc = readDoc();
        renderSummary();
        if (root) renderAll();
    }

    // dirty=false is for view_state only (which card is selected, the zoom, the
    // scroll): those must not mark the workflow modified and must not re-encode.
    function writeDoc({ dirty = true } = {}) {
        const widget = widgetFor(GUIDES_FIELD);
        if (!widget) return;
        if (parseError) {
            // Unreadable original text: keep it until the user chooses to replace it.
            console.warn("[H3 Guide Timeline] not writing the guide list while it is unreadable");
            return;
        }
        try {
            widget.value = serializeDocument(doc);
        } catch (error) {
            console.warn("[H3 Guide Timeline] could not serialize the guide list:", error);
            return;
        }
        widget.callback?.(widget.value);
        node.setDirtyCanvas?.(true, true);
        if (dirty) node.graph?.setChanged?.();
    }

    // ---------- how long the video is ----------
    // resolveTimelineRange in web/guide_state.js owns the order: a number typed in this
    // node's own duration box (seconds, because that is how a person plans a shot), then the
    // frame count from the last real run, then a guess read from the upstream generator's
    // length widget - that one really is frames, so it is read as-is. The alignment to 17n+5
    // is the native node's own (comfy_extras/nodes_minimax_h3.py: align_frame_count), so the
    // ruler the panel draws is the length the run will produce.
    function upstreamLength() {
        try {
            const input = node.inputs?.find((item) => item.name === "latent");
            const link = input?.link != null ? node.graph?.links?.[input.link] : null;
            const source = link ? node.graph?.getNodeById?.(link.origin_id) : null;
            if (!source) return null;
            const widget = source.widgets?.find((item) => item.name === "length");
            const raw = Number(widget?.value);
            if (!Number.isFinite(raw) || raw <= 0) return null;
            return { frames: alignFrameCount(raw), label: String(source.title || source.type || "上游节点") };
        } catch (error) {
            return null;
        }
    }

    // The seconds this node is told the video should be. A typed number is what the ruler is
    // drawn from even when an earlier run left a different frame count behind - that is the only
    // way the box is usable before anything has been run.
    //
    // A Float input also gets a socket, so the same value can be wired in instead of typed (a Float
    // primitive, or a duration computed elsewhere in the workflow). The widget is hidden and stays
    // at its old value when a link is connected, so reading only the widget would leave the ruler
    // empty for a wired duration - follow one link, the same way upstreamLength() does. If the
    // source cannot be read, return 0: no ruler is better than a made-up one.
    function ownSecondsRaw() {
        const input = node.inputs?.find((item) => item.name === "length_seconds");
        const link = input?.link != null ? node.graph?.links?.[input.link] : null;
        const source = link ? node.graph?.getNodeById?.(link.origin_id) : null;
        if (source) {
            const widget = source.widgets?.find((item) => Number(item.value) > 0);
            const wired = Number(widget?.value);
            return Number.isFinite(wired) && wired > 0 ? wired : 0;
        }
        const raw = Number(widgetFor("length_seconds")?.value);
        return Number.isFinite(raw) && raw > 0 ? raw : 0;
    }

    // frames 0 means "nothing to draw yet"; the panel says so instead of inventing a
    // ruler, because a made-up length is how a guide ends up out of range.
    function timelineRange() {
        return resolveTimelineRange({
            resolvedFrameCount: doc.resolved_frame_count,
            resolvedSource: doc.resolved_source,
            ownSeconds: ownSecondsRaw(),
            fps: doc.fps,
            upstream: upstreamLength(),
        });
    }

    // ---------- media metadata, cached by file ----------
    function audioMetaFor(guide) {
        return audioCache.get(mediaKeyOf(guide)) || null;
    }

    function audioMetaById() {
        const map = {};
        for (const guide of doc.guides) {
            if (guide.kind !== AUDIO_KIND) continue;
            const meta = audioMetaFor(guide);
            // Only a confirmed sample rate and sample count can produce a real span. A file
            // whose duration is known but whose samples are not stays out, and the footer says
            // the overlap check is incomplete instead of pretending it passed.
            if (!meta || !meta.sampleRate || !meta.sampleCount) continue;
            map[guide.id] = { sample_rate: meta.sampleRate, sample_count: meta.sampleCount };
        }
        return map;
    }

    // A guide image is always one still frame here (_decode_image_frames returns
    // [1,H,W,3]), so the held length is guideFramesFor(1) = 1. Kept explicit rather
    // than implied so the check matches the node.
    function imageFramesById() {
        const map = {};
        for (const guide of doc.guides) {
            if (guide.kind === IMAGE_KIND) map[guide.id] = 1;
        }
        return map;
    }

    function currentSpans() {
        return audioSpans(doc.guides, audioMetaById());
    }

    function currentProblems() {
        const range = timelineRange();
        // v2: a 0.00 card is not part of the run, so its placement is not a problem either.
        const check = perImageStrength ? validateGuidesV2 : validateGuides;
        return check(doc.guides, range.frames, {
            spans: currentSpans(),
            imageFrames: imageFramesById(),
            fps: doc.fps,
        });
    }

    function guideById(id) {
        return doc.guides.find((guide) => guide.id === id) || null;
    }

    function selectedGuide() {
        return doc.view_state.selected_id ? guideById(doc.view_state.selected_id) : null;
    }

    function viewUrl(asset) {
        const path = `/view?filename=${encodeURIComponent(asset?.filename ?? "")}`
            + `&subfolder=${encodeURIComponent(asset?.subfolder || "")}`
            + `&type=${encodeURIComponent(asset?.type || "input")}`;
        if (typeof api.apiURL === "function") return api.apiURL(path);
        if (typeof api.getFileUrl === "function") return api.getFileUrl(path);
        return path;
    }

    // Evidence for a drag a human reports as broken. The panel does not log on its own: a probe
    // sets window.__h3guideDebug and the handlers report what they actually saw. That is the only
    // way to tell "the handler never ran" from "the handler ran and returned early", which is the
    // difference between two different fixes.
    function debugEvent(name, fields = {}) {
        const sink = typeof window === "undefined" ? null : window.__h3guideDebug;
        if (typeof sink !== "function") return;
        try {
            sink({ node: node.id, event: name, at: Date.now(), ...fields });
        } catch {
            // a probe must never break a drag
        }
    }

    function describeTarget(el) {
        if (!(el instanceof Element)) return null;
        return { tag: el.tagName, cls: String(el.className || "").slice(0, 80), id: el.id || null };
    }

    function describePoint(x, y) {
        try {
            return describeTarget(document.elementFromPoint(x, y));
        } catch {
            return null;
        }
    }

    // ---------- the floating editor ----------
    // It lives on document.body, never inside the node: a self-sizing panel is how the
    // "the node grew again" bug starts. Closing it stops the players and the observers
    // but never clears data, so reopening shows the same timeline.
    let root = null;
    let scope = null;          // listeners for the open editor only
    let els = null;            // editor DOM by role
    let cardEls = new Map();   // guide.id -> card element
    let observer = null;
    // One renderer, two surfaces. The editor's zoomed timeline and the node's
    // fit-to-width timeline can be on screen at the same time, and each needs its own
    // pixels-per-frame, scroll offset and lane items; sharing one scale between the two
    // is what would make them disagree about where a frame is.
    let editorSurface = null;
    let measureFrame = 0;
    // Set while a pool card is held: the preview lives on document.body, so removing the editor
    // would leave it on screen.
    let poolDragCleanup = null;
    const players = new Set();

    function openEditor() {
        if (root) return;
        buildEditor();
        renderAll();
        openBtn.classList.add("on");
        openBtn.textContent = "🎬 Guide 编辑器已打开";
    }

    function closeEditor() {
        if (!root) return;
        for (const player of players) {
            player.onended = null;
            player.pause();
            player.src = "";
        }
        players.clear();
        detailPlayer = null;
        observer?.disconnect();
        observer = null;
        if (measureFrame) cancelAnimationFrame(measureFrame);
        measureFrame = 0;
        poolDragCleanup?.();
        endAllDragSessions();
        scope?.abort();
        scope = null;
        root.remove();
        root = null;
        els = null;
        editorSurface = null;
        cardEls.clear();
        openBtn.classList.remove("on");
        openBtn.textContent = "🎬 打开 Guide 编辑器";
    }

    // Sections A-G of the plan, in that order: bar, ruler, image lane, audio lane,
    // card pool, selected detail, validation footer.
    function buildEditor() {
        scope = new AbortController();
        const signal = scope.signal;
        root = make("div", "h3guide-root");

        const head = make("div", "h3guide-bar");
        const headSub = make("span", "h3guide-sub");
        const zoomOut = make("button", "h3guide-primary", "−");
        zoomOut.title = "缩小时间轴";
        const zoomIn = make("button", "h3guide-primary", "+");
        zoomIn.title = "放大时间轴";
        const fitBtn = make("button", "h3guide-primary", "全部");
        fitBtn.title = "让整段视频刚好占满时间轴";
        const closeBtn = make("button", "h3guide-primary", "✕ 关闭");
        closeBtn.title = "关闭编辑器不会清空数据，也不会影响执行";
        head.append(
            make("strong", null, "🎬 Guide 编排"),
            headSub,
            make("span", "h3guide-spacer"),
            make("span", "h3guide-sub", "时间轴缩放"),
            zoomOut,
            zoomIn,
            fitBtn,
            closeBtn,
        );

        const ruler = make("div", "h3guide-ruler");
        const trackImage = make("div", "h3guide-track");
        const trackAudio = make("div", "h3guide-track h3guide-track-audio");
        // The pan slider is a fourth row so it lines up with the lanes: same label column,
        // same width. It hides itself while the whole video fits.
        const panBar = make("div", "h3guide-pan");
        const panThumb = make("div", "h3guide-pan-thumb");
        panBar.appendChild(panThumb);

        // Each lane owns a header. The lane name is the tab that decides which cards the pool
        // below shows, adding material is a secondary button under it, and the height control
        // sits on the same line. They used to be one flat row of identical buttons above the
        // pool, which read as four unrelated actions - "图片卡片" is not the same kind of
        // control as "＋ 添加图片".
        const laneHead = (title, addLabel, addTitle) => {
            const head = make("div", "h3guide-lane-head");
            const tab = make("button", "h3guide-lane-tab", title);
            tab.title = "卡片池切换到" + title;
            const count = make("span", "h3guide-lane-count");
            const add = make("button", "h3guide-secondary", addLabel);
            add.title = addTitle;
            const px = make("span", "h3guide-lane-count h3guide-lane-px");
            const shrink = make("button", "h3guide-secondary", "− 高度");
            shrink.title = "把这条轨道变矮，卡片随之变小";
            const grow = make("button", "h3guide-secondary", "＋ 高度");
            grow.title = "把这条轨道变高，卡片随之变大（竖屏素材更清楚）";
            head.append(tab, count, add, make("span", "h3guide-spacer"), px, shrink, grow);
            return { head, tab, add, count, px, shrink, grow };
        };
        const imageLane = laneHead("图片卡片", "＋ 添加图片", "选择图片加入卡片池");
        const audioLane = laneHead("音频卡片", "＋ 添加音频", "选择音频加入卡片池");
        const tabImage = imageLane.tab;
        const tabAudio = audioLane.tab;
        const addImage = imageLane.add;
        const addAudio = audioLane.add;
        const imageResize = make("div", "h3guide-lane-resize");
        imageResize.title = "上下拖动改变图片轨高度";
        const audioResize = make("div", "h3guide-lane-resize");
        audioResize.title = "上下拖动改变音频轨高度";

        const timeline = make("div", "h3guide-timeline");
        const laneRows = {};
        for (const [row, label, track, head, grip] of [
            ["ruler", "时间尺", ruler, null, null],
            ["image", "", trackImage, imageLane.head, imageResize],
            ["audio", "", trackAudio, audioLane.head, audioResize],
            ["pan", "平移", panBar, null, null],
        ]) {
            if (head) timeline.appendChild(head);
            const line = make("div", "h3guide-row");
            if (row === "pan") line.classList.add("h3guide-pan-row");
            // The label column stays - it is what aligns the ruler, both lanes and the pan
            // slider - but the lane name now lives in the header, so it is not printed twice.
            line.append(make("span", "h3guide-lane-label", label), track);
            laneRows[row] = line;
            timeline.appendChild(line);
            if (grip) timeline.appendChild(grip);
        }


        const pool = make("div", "h3guide-pool");
        const poolBar = make("div", "h3guide-bar");
        const poolKind = make("span", "h3guide-sub");
        const poolCounts = make("span", "h3guide-sub");
        poolBar.append(make("strong", null, "卡片池"), poolKind, make("span", "h3guide-spacer"), poolCounts);
        // The plan asks for ~220-260px cards here: a guide card carries two number
        // fields and a row of buttons, so the picker's 130px base is too small to stay usable.
        createCardZoom({ container: pool, node, baseCardMin: 240, baseThumbH: 150 }).mount(poolBar);
        const deck = make("div", "h3lvm-deck");
        const imageInput = make("input", "h3guide-file-input");
        imageInput.type = "file";
        imageInput.accept = "image/*";
        imageInput.multiple = true;
        const audioInput = make("input", "h3guide-file-input");
        audioInput.type = "file";
        audioInput.accept = "audio/*";
        audioInput.multiple = true;
        pool.append(poolBar, deck, imageInput, audioInput);

        const detail = make("div", "h3guide-detail");
        const foot = make("div", "h3guide-foot");

        els = {
            head, headSub, ruler, trackImage, trackAudio, panBar, panThumb, pool, deck, poolKind, poolCounts,
            detail, foot, tabImage, tabAudio, countImage: imageLane.count, countAudio: audioLane.count,
            pxImage: imageLane.px, pxAudio: audioLane.px, imageInput, audioInput,
            // The row is the drop target for a card coming from the pool: the lane plus its
            // label column, and nothing else. The header above it and the grip below it are
            // siblings, so they are not part of the hit area.
            rowImage: laneRows.image, rowAudio: laneRows.audio,
        };
        editorSurface = createSurface({ ruler, trackImage, trackAudio });
        // The detail area sits between the tracks and the card pool: selecting a card on a lane
        // puts its fields right under the lane it came from, and the pool stays the section that
        // grows with the panel.
        root.append(head, timeline, detail, pool, foot);
        document.body.appendChild(root);

        closeBtn.onclick = (event) => {
            event.stopPropagation();
            closeEditor();
        };
        zoomOut.onclick = (event) => {
            event.stopPropagation();
            setZoom(zoomStepAt(doc.view_state.zoom, -1));
        };
        zoomIn.onclick = (event) => {
            event.stopPropagation();
            setZoom(zoomStepAt(doc.view_state.zoom, 1));
        };
        fitBtn.onclick = (event) => {
            event.stopPropagation();
            setZoom(1);
        };
        tabImage.onclick = (event) => {
            event.stopPropagation();
            setTab(IMAGE_KIND);
        };
        tabAudio.onclick = (event) => {
            event.stopPropagation();
            setTab(AUDIO_KIND);
        };
        addImage.onclick = (event) => {
            event.stopPropagation();
            imageInput.click();
        };
        addAudio.onclick = (event) => {
            event.stopPropagation();
            audioInput.click();
        };
        // The two height steps and the grip under the lane are the same control; both are
        // view state, so neither marks the workflow dirty.
        const stepHeight = (kind, delta) => {
            if (!setLaneHeight(kind, stepLaneHeight(kind, laneHeights(doc.view_state)[kind], delta))) return;
            writeDoc({ dirty: false });
            renderTimeline();
        };
        imageLane.shrink.onclick = (event) => {
            event.stopPropagation();
            stepHeight(IMAGE_KIND, -1);
        };
        imageLane.grow.onclick = (event) => {
            event.stopPropagation();
            stepHeight(IMAGE_KIND, 1);
        };
        audioLane.shrink.onclick = (event) => {
            event.stopPropagation();
            stepHeight(AUDIO_KIND, -1);
        };
        audioLane.grow.onclick = (event) => {
            event.stopPropagation();
            stepHeight(AUDIO_KIND, 1);
        };
        attachLaneResize(imageResize, IMAGE_KIND, signal);
        attachLaneResize(audioResize, AUDIO_KIND, signal);
        applyLaneHeights();
        for (const [input, kind] of [[imageInput, IMAGE_KIND], [audioInput, AUDIO_KIND]]) {
            input.addEventListener("change", () => {
                const files = [...(input.files ?? [])];
                input.value = "";
                void importFiles(files, kind);
            }, { signal });
        }

        dragTitleBar(signal);
        timelinePanning(signal);
        laneKeyboard(signal);
        poolFileDrop(signal);
        poolPointerDrag(signal);

        if (typeof ResizeObserver !== "undefined") {
            // The user resizes the editor with the CSS corner; the lanes follow the new
            // width instead of keeping the transform they were built with.
            observer = new ResizeObserver(() => scheduleMeasure());
            observer.observe(root);
        }
    }

    // The editor has no title bar of its own beyond section A, so that bar doubles as
    // the handle. Moving it is view state only.
    function dragTitleBar(signal) {
        els.head.addEventListener("pointerdown", (event) => {
            if (event.target?.closest?.("button")) return;
            const startX = event.clientX;
            const startY = event.clientY;
            // The panel opens centred: left/top 50% plus translate(-50%, -50%). offsetLeft is
            // that 50% value, not the painted corner, so dropping the transform moves the
            // panel by half its own size - a small drag lands it off to the bottom right.
            // Read the painted rect and switch to left/top in one style batch: no jump, and
            // the pointer keeps holding the same point of the panel.
            const rect = root.getBoundingClientRect();
            const startLeft = rect.left;
            const startTop = rect.top;
            root.style.transform = "none";
            root.style.left = `${startLeft}px`;
            root.style.top = `${startTop}px`;
            try {
                els.head.setPointerCapture(event.pointerId);
            } catch (error) {
                // no pointer capture; a fast drag that leaves the bar still stops here
            }
            const onMove = (moveEvent) => {
                const left = startLeft + (moveEvent.clientX - startX);
                const top = startTop + (moveEvent.clientY - startY);
                root.style.left = `${Math.max(4, Math.min(window.innerWidth - 60, left))}px`;
                root.style.top = `${Math.max(4, Math.min(window.innerHeight - 40, top))}px`;
            };
            const onUp = (endEvent) => {
                try {
                    els.head.releasePointerCapture?.(endEvent.pointerId);
                } catch (error) {
                    // already released
                }
                els.head.removeEventListener("pointermove", onMove);
                els.head.removeEventListener("pointerup", onUp);
                els.head.removeEventListener("pointercancel", onUp);
            };
            els.head.addEventListener("pointermove", onMove);
            els.head.addEventListener("pointerup", onUp);
            els.head.addEventListener("pointercancel", onUp);
            event.preventDefault();
        }, { signal });
    }
    // ---------- one coordinate transform per surface ----------
    // Zoom 1 means the whole video fits; above that the content is wider than the
    // panel and the ruler plus both lanes scroll together. The node surface is always
    // zoom 1, so it never scrolls. Nothing else in this file converts frames to pixels.
    function createSurface({ ruler, trackImage, trackAudio, fitWidth = false, padding = TRACK_PADDING, tickGapPx = 90 }) {
        return {
            ruler,
            trackImage,
            trackAudio,
            fitWidth,
            padding,
            tickGapPx,
            scale: null,
            scroll: 0,
            marks: [],
            laneItems: [],
            playhead: null,
            playheadFrame: 0,
        };
    }

    // The lane height is the only thing that sizes a lane card, so the header steps and the
    // grip under the lane go through one function. Like the zoom and the scroll it is view
    // state: it never marks the workflow dirty.
    function applyLaneHeights() {
        if (!els) return;
        const heights = laneHeights(doc.view_state);
        doc.view_state.lane_heights = heights;
        els.trackImage.style.height = `${heights[IMAGE_KIND]}px`;
        els.trackAudio.style.height = `${heights[AUDIO_KIND]}px`;
        els.pxImage.textContent = `图片轨 ${heights[IMAGE_KIND]}px`;
        els.pxAudio.textContent = `音频轨 ${heights[AUDIO_KIND]}px`;
    }

    // The node strip draws the same lanes with the same numbers, clamped to the height the
    // panel really has. Card sizing is deliberately absent: the two controls are independent
    // in both directions. Returns false when the tracks do not fit; their header stays visible.
    function applyStripHeights() {
        const wanted = laneHeights(doc.view_state);
        const customMarkerSide = hasStripMarkerSide(doc.view_state);
        const markerSide = customMarkerSide ? stripMarkerSide(doc.view_state) : 0;
        const headExtra = Math.max(0, stripHead.offsetHeight - 28);
        const plan = stripLaneHeights({
            room: stripRoom({
                containerHeight: container.clientHeight,
                toolbarHeight: toolbar.offsetHeight,
                footerHeight: nodeFooter.offsetHeight,
            }) - headExtra,
            image: wanted[IMAGE_KIND],
            audio: wanted[AUDIO_KIND],
        });
        strip.classList.toggle("h3guide-strip-custom-card", customMarkerSide);
        stripHeights = plan.heights;
        stripImageTrack.style.height = `${plan.heights[IMAGE_KIND]}px`;
        stripAudioTrack.style.height = `${plan.heights[AUDIO_KIND]}px`;
        for (const [kind, control] of [[IMAGE_KIND, stripImageSize], [AUDIO_KIND, stripAudioSize]]) {
            const asked = wanted[kind];
            const got = plan.heights[kind];
            control.px.textContent = `${got}px`;
            control.px.classList.toggle("h3guide-lane-px-clamped", got < asked);
            control.px.title = got === asked
                ? "节点内的轨道高度；图片卡片大小由「卡片 − / ＋」单独设置"
                : `面板只放得下 ${got}px（想要 ${asked}px）：把节点拉高，或调矮另一条轨道`;
        }
        stripCardSize.px.textContent = customMarkerSide ? `${markerSide}px` : "自动";
        stripCardSize.px.title = customMarkerSide
            ? "节点内图片卡片的独立边长；轨道高度、节点宽度和卡片数量都不会改变它"
            : "当前沿用旧版自动尺寸；点击 − 或 ＋ 后改为独立尺寸";
        for (const button of [stripCardSize.shrink, stripCardSize.grow]) {
            button.title = "只调整节点内图片卡片，不改变弹窗或音频轨道；设置会随工作流保存";
        }
        return plan.fits;
    }

    // Returns false when nothing changed, so the caller can skip a re-render.
    function setLaneHeight(kind, value) {
        const heights = laneHeights(doc.view_state);
        const next = clampLaneHeight(kind, value);
        if (next === heights[kind]) return false;
        heights[kind] = next;
        doc.view_state.lane_heights = heights;
        // Either place can change the number, so both views follow it - the editor when it is
        // open, the node strip whenever it is drawn.
        applyLaneHeights();
        applyStripHeights();
    // The editor cards follow their lane; an independent node card does not.
        // While a grip is held that is the cheap part only; the full render waits for release.
        syncMarkerSide(editorSurface);
        syncMarkerSide(nodeSurface);
        return true;
    }

    function markerPlanFor(surface, placedCount) {
        const laneHeight = surface.trackImage.clientHeight;
        if (surface.fitWidth) {
            const custom = hasStripMarkerSide(doc.view_state);
            const budget = custom ? 0 : stripMarkerPlan({
                laneWidth: surface.trackImage.clientWidth,
                count: placedCount,
            }).markerWidth;
            return stripCardPlan({
                laneHeight,
                widthBudget: budget,
                markerSide: custom ? stripMarkerSide(doc.view_state) : null,
            });
        }
        const max = Math.min(MARKER_SIDE_HARD_MAX, laneHeight - MARKER_INSET * 2);
        return squareMarkerPlan({ laneHeight, widthBudget: 0, max });
    }

    function syncMarkerSide(surface) {
        if (!surface?.trackImage) return;
        const plan = markerPlanFor(surface, surface.laneItems?.length || 0);
        surface.padding = plan.padding;
        surface.trackImage.style.setProperty("--h3guide-marker-side", `${plan.side}px`);
    }

    // Dragging the grip under a lane is the direct way to make a 9:16 frame readable. The
    // document is written once, on release, for the same reason a card drag is: one gesture
    // is one history step.
    function attachLaneResize(grip, kind, signal) {
        grip.addEventListener("pointerdown", (event) => {
            if (event.button) return;
            event.preventDefault();
            const track = kind === AUDIO_KIND ? els.trackAudio : els.trackImage;
            const startHeight = track.clientHeight;
            const startY = event.clientY;
            const pointerId = event.pointerId;
            grip.classList.add("dragging");
            beginDragSession((moveEvent) => {
                if (pointerId !== undefined && moveEvent.pointerId !== pointerId) return;
                setLaneHeight(kind, startHeight + (moveEvent.clientY - startY));
            }, () => {
                grip.classList.remove("dragging");
                writeDoc({ dirty: false });
                renderTimeline();
            });
        }, { signal });
    }

    function measureSurface(surface) {
        const range = timelineRange();
        surface.scale = createScale({
            frameCount: range.frames || 1,
            width: surface.trackImage.clientWidth || 0,
            zoom: surface.fitWidth ? 1 : doc.view_state.zoom,
            padding: surface.padding,
        });
        if (surface.fitWidth) {
            surface.scroll = 0;
            return;
        }
        // A zoom change asks for one frame to stay in the middle of the view. That only
        // means anything against the new transform, so it is applied here and dropped.
        if (surface.pendingCenter !== null && surface.pendingCenter !== undefined) {
            surface.scroll = scrollToFrame(surface.scale, surface.pendingCenter);
            surface.pendingCenter = null;
        } else {
            surface.scroll = clampScroll(doc.view_state.scroll, surface.scale.scrollMax);
        }
        doc.view_state.scroll = surface.scroll;
    }

    function setZoom(value) {
        const surface = editorSurface;
        if (surface?.scale && surface.scale.scrollMax > 0) {
            // Whatever is in the middle of the view stays there instead of jumping back
            // to the start of the video.
            surface.pendingCenter = surface.scale.pxToFrame(surface.scroll + surface.scale.viewWidth / 2, { clamp: false });
        }
        doc.view_state.zoom = Math.max(1, Number(value) || 1);
        writeDoc({ dirty: false });
        renderTimeline();
    }

    // One place changes the editor's scroll offset, whatever asked for it - the slider, the
    // wheel, dragging empty lane space or dragging a card. It is view state: it never marks
    // the workflow dirty, and the ruler and both lanes always move together.
    function setScroll(value) {
        const surface = editorSurface;
        if (!surface?.scale) return;
        surface.scroll = clampScroll(value, surface.scale.scrollMax);
        doc.view_state.scroll = surface.scroll;
        applyAllScrolls();
    }

    // The slider under the lanes is the explicit way to reach the rest of the video.
    // Stretching the panel or scrolling the page cannot do it: a lane is one row that fills
    // the panel and clips what does not fit, which is the "I can never see the rest" bug.
    function renderPanBar() {
        if (!els?.panBar) return;
        const surface = editorSurface;
        const view = panWindow(surface?.scale, surface?.scroll || 0);
        els.panBar.classList.toggle("h3guide-pan-off", !view.scrollable);
        if (els.headSub) {
            const zoom = Math.round((surface?.scale?.zoom || 1) * 100);
            els.headSub.textContent = view.scrollable
                ? `时间轴 ${zoom}% · 拖下方滑块、滚轮或轨道空白处可看到其余部分`
                : "时间轴 100% · 整段可见";
        }
        if (!view.scrollable) return;
        const barWidth = els.panBar.clientWidth || 0;
        if (!barWidth) return;
        const width = Math.max(PAN_THUMB_MIN_PX, Math.min(barWidth, view.widthFraction * barWidth));
        const left = Math.max(0, Math.min(barWidth - width, view.leftFraction * barWidth));
        els.panThumb.style.left = `${left}px`;
        els.panThumb.style.width = `${width}px`;
    }

    // Three gestures move the view: the slider, the wheel over a lane, and dragging the
    // empty space of a lane. Cards keep their own drag (attachLaneDrag), so anything that
    // is a card is left alone here.
    function timelinePanning(signal) {
        const surface = editorSurface;
        // The view offset is part of the saved document, so every gesture that moves it has to
        // write it back. A wheel is a burst of events, so the write waits for the burst to stop;
        // the slider and the lane drag write when their pointer is released.
        let settleWrite = 0;
        const settleViewWrite = () => {
            clearTimeout(settleWrite);
            settleWrite = setTimeout(() => { settleWrite = 0; writeDoc({ dirty: false }); }, 260);
        };
        signal.addEventListener("abort", () => {
            if (settleWrite) clearTimeout(settleWrite);
            settleWrite = 0;
        });
        for (const el of [els.ruler, els.trackImage, els.trackAudio]) {
            el.addEventListener("wheel", (event) => {
                if (!surface.scale || surface.scale.scrollMax <= 0) return;
                const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
                if (!delta) return;
                event.preventDefault();
                setScroll(panBy(surface.scale, surface.scroll, delta));
                settleViewWrite();
            }, { signal, passive: false });

            el.addEventListener("pointerdown", (event) => {
                if (event.button || !surface.scale || surface.scale.scrollMax <= 0) return;
                if (event.target?.closest?.(".h3guide-marker, .h3guide-clip, .h3guide-playhead")) return;
                const startX = event.clientX;
                const startScroll = surface.scroll;
                const pointerId = event.pointerId;
                let moved = false;
                el.classList.add("h3guide-panning");
                beginDragSession((moveEvent) => {
                    if (pointerId !== undefined && moveEvent.pointerId !== pointerId) return;
                    const dx = moveEvent.clientX - startX;
                    if (!dx) return;
                    moved = true;
                    // The content follows the pointer, so the view moves the other way.
                    setScroll(panBy(surface.scale, startScroll, -dx));
                }, () => {
                    el.classList.remove("h3guide-panning");
                    if (moved) writeDoc({ dirty: false });
                });
                event.preventDefault();
            }, { signal });
        }

        els.panThumb.addEventListener("pointerdown", (event) => {
            if (event.button || !surface.scale || surface.scale.scrollMax <= 0) return;
            const rect = els.panBar.getBoundingClientRect();
            const pointerId = event.pointerId;
            els.panThumb.classList.add("dragging");
            beginDragSession((moveEvent) => {
                if (pointerId !== undefined && moveEvent.pointerId !== pointerId) return;
                const fraction = (moveEvent.clientX - rect.left) / Math.max(1, rect.width);
                setScroll(scrollForPanThumb(surface.scale, fraction));
            }, () => {
                els.panThumb.classList.remove("dragging");
                writeDoc({ dirty: false });
            });
            event.preventDefault();
            event.stopPropagation();
        }, { signal });
    }

    function setTab(kind) {
        if (!KINDS.includes(kind) || doc.view_state.active_tab === kind) return;
        doc.view_state.active_tab = kind;
        writeDoc({ dirty: false });
        renderPool();
    }

    function scheduleMeasure() {
        if (measureFrame || !root) return;
        measureFrame = requestAnimationFrame(() => {
            measureFrame = 0;
            renderTimeline();
        });
    }

    function applyScroll(surface) {
        if (!surface || !surface.scale) return;
        // One transform for everything on the lanes: the ruler ticks, the gridlines, the
        // markers, the audio clips, the anchor ticks and the 定位 line. A marker may carry an
        // offsetPx because declutterMarkers moved it aside; its anchor tick never does, so the
        // true frame stays readable even when the card itself had to shift.
        const at = (frame, offset = 0) => `${surface.scale.markerPx(frame) - surface.scroll + (Number(offset) || 0)}px`;
        for (const item of surface.marks) item.el.style.left = at(item.frame, item.offsetPx);
        for (const item of surface.laneItems) {
            item.el.style.left = at(item.frame, item.offsetPx);
            if (item.link) {
                const delta = Number(item.offsetPx) || 0;
                item.link.style.left = delta >= 0 ? at(item.frame) : at(item.frame, delta);
                item.link.style.width = `${Math.abs(delta)}px`;
            }
            // Only an audio clip spans frames. An image marker is one frame wide and its
            // size is the measured square in CSS; setting a width here used to squash it
            // to pxPerFrame, which is how the cards became unreadable at fit-to-width.
            if (item.isAudio && item.widthFrames) {
                item.el.style.width = `${Math.max(0, item.widthFrames * surface.scale.pxPerFrame)}px`;
            }
        }
        if (surface.playhead) surface.playhead.style.left = at(surface.playheadFrame);
    }

    // Both copies of the timeline move together, each with its own transform.
    // Both copies of the timeline move together, each with its own transform. The pan
    // slider shows the same offset, so it stays honest during a card drag too.
    function applyAllScrolls() {
        if (root) applyScroll(editorSurface);
        if (stripOn) applyScroll(nodeSurface);
        renderPanBar();
    }

    // Which cards a validation message names. The messages start with the card label,
    // and the footer turns each one into a button that selects that card.
    function problemIds(problems) {
        const bad = new Set();
        for (const text of problems) {
            for (const guide of doc.guides) {
                if (guide.label && text.includes(guide.label)) bad.add(guide.id);
            }
        }
        return bad;
    }

    function placedGuides() {
        return doc.guides.filter((guide) => guide.frame_index !== null && guide.frame_index !== undefined);
    }

    function renderTimeline() {
        if (!root) return;
        renderSurface(editorSurface);
        renderPanBar();
    }

    // One renderer for both copies of the timeline. The node surface fits the whole video
    // to its own width and can have an independently sized image marker; the thumbnails,
    // labels and waveforms are the same DOM as in the editor.
    function renderSurface(surface) {
        if (!surface) return;
        const range = timelineRange();
        const placed = placedGuides();
        for (const track of [surface.ruler, surface.trackImage, surface.trackAudio]) track.replaceChildren();
        surface.laneItems = [];
        surface.marks = [];
        surface.playhead = null;

        if (!range.frames) {
            surface.trackImage.append(make("span", "h3guide-lane-hint", "连接 latent 并运行后，这里才会出现时间尺"));
            surface.trackAudio.append(make("span", "h3guide-lane-hint", "同上"));
            return;
        }

        const plan = markerPlanFor(surface, placed.length);
        surface.padding = plan.padding;
        surface.trackImage.style.setProperty("--h3guide-marker-side", `${plan.side}px`);
        measureSurface(surface);

        const { ticks } = tickMarks(surface.scale, doc.fps, { minGapPx: surface.tickGapPx });
        for (const tick of ticks) {
            const mark = make("div", "h3guide-tick");
            mark.append(make("span", null, tick.label));
            surface.ruler.appendChild(mark);
            surface.marks.push({ el: mark, frame: tick.frame });
            for (const track of [surface.trackImage, surface.trackAudio]) {
                const grid = make("div", "h3guide-gridline");
                track.appendChild(grid);
                surface.marks.push({ el: grid, frame: tick.frame });
            }
        }

        const selected = selectedGuide();
        if (selected && selected.frame_index !== null && selected.frame_index !== undefined) {
            surface.playhead = make("div", "h3guide-playhead cap");
            surface.playheadFrame = Math.trunc(Number(selected.frame_index));
            surface.ruler.appendChild(surface.playhead);
        }

        const spans = currentSpans();
        const bad = problemIds(currentProblems());
        if (!placed.length) {
            surface.trackImage.append(make("span", "h3guide-lane-hint", "把卡片拖到这条轨道，或点卡片上的「放置」"));
        }

        // Dense markers are spread apart in display space only. declutterMarkers never touches
        // frame_index, and every square keeps an anchor tick at its true frame plus a connector
        // to the shifted card, so the time is always readable. groupSize > 1 gets a badge: that
        // is the honest answer to "I cannot pick the card that is hidden behind another one",
        // and it beats raising z-index on hover, which hides the same problem.
        const laidOut = new Map();
        for (const item of declutterMarkers({
            anchors: placed.filter((guide) => guide.kind === IMAGE_KIND)
                .map((guide) => ({ id: guide.id, px: surface.scale.markerPx(Math.trunc(Number(guide.frame_index))) })),
            size: plan.side,
            laneWidth: surface.scale.contentWidth,
            minGap: 6,
        })) {
            laidOut.set(item.id, item);
        }

        for (const guide of placed) {
            const frame = Math.trunc(Number(guide.frame_index));
            const classes = [guide.kind === AUDIO_KIND ? "h3guide-clip" : "h3guide-marker"];
            if (guide.id === doc.view_state.selected_id) classes.push("selected");
            if (bad.has(guide.id)) classes.push("invalid");
            const el = make("div", classes.join(" "));
            if (guide.enabled === false) el.style.opacity = "0.45";

            let widthFrames = 1;
            let offsetPx = 0;
            let link = null;
            if (guide.kind === IMAGE_KIND) {
                const laid = laidOut.get(guide.id);
                offsetPx = Number(laid?.offset) || 0;
                const tick = make("div", "h3guide-anchor-tick");
                surface.trackImage.appendChild(tick);
                surface.marks.push({ el: tick, frame });
                if (offsetPx) {
                    link = make("div", "h3guide-anchor-link");
                    surface.trackImage.appendChild(link);
                }
                const img = make("img", "h3guide-marker-thumb");
                img.src = viewUrl(guide.asset);
                img.alt = guide.label || "";
                img.draggable = false;
                el.append(img, make("span", "h3guide-marker-cap", `${guide.label} · ${frame}f`));
                if (perImageStrength) el.appendChild(makeStrengthBadge(guide, true));
                if (laid?.groupSize > 1) el.append(make("span", "h3guide-group", `×${laid.groupSize}`));
                widthFrames = 1;
            } else {
                widthFrames = Number(spans[guide.id]) || 0;
                const status = audioStatus(audioMetaFor(guide));
                el.append(make("span", "h3guide-clip-cap", `${guide.label} · ${formatSeconds(frameToSeconds(widthFrames, doc.fps), 2)}s`));
                const wave = make("canvas", "h3guide-clip-wave");
                el.appendChild(wave);
                if (!status.waveform) {
                    // drawn once the element is in the DOM, where it has a size
                    el.classList.add("h3guide-wave-none");
                    el.append(make("span", "h3guide-wave-note", status.label));
                }
            }

            el.addEventListener("pointerdown", () => select(guide.id));
            attachLaneDrag(surface, el, guide, widthFrames);
            (guide.kind === AUDIO_KIND ? surface.trackAudio : surface.trackImage).appendChild(el);
            surface.laneItems.push({
                guide, el, frame, widthFrames, offsetPx, link,
                isAudio: guide.kind === AUDIO_KIND,
                wave: el.querySelector(".h3guide-clip-wave"),
            });
        }
        applyScroll(surface);
        for (const item of surface.laneItems) {
            if (item.wave) paintWave(item.wave, audioMetaFor(item.guide), null);
        }
    }

    // One place owns "a pointer gesture is in progress". Dragging a card on a lane, dragging
    // empty lane space and dragging the pan thumb all register here, and the session is gone
    // the moment the gesture ends. Closing the editor or deleting the node ends every open
    // session: scope.abort() only removes listeners that were given the signal, and these live
    // on window on purpose - a lane has overflow:hidden, so an element-level listener stops
    // firing the moment the pointer leaves it, which is what "the card does not follow the
    // mouse" looked like.
    const dragSessions = new Set();

    function beginDragSession(onMove, onEnd) {
        const session = {};
        session.move = (event) => onMove(event);
        session.up = (event) => { endDragSession(session); onEnd?.(event, false); };
        session.cancel = () => { endDragSession(session); onEnd?.(null, true); };
        window.addEventListener("pointermove", session.move);
        window.addEventListener("pointerup", session.up);
        window.addEventListener("pointercancel", session.cancel);
        dragSessions.add(session);
        return session;
    }

    function endDragSession(session) {
        if (!dragSessions.has(session)) return;
        dragSessions.delete(session);
        window.removeEventListener("pointermove", session.move);
        window.removeEventListener("pointerup", session.up);
        window.removeEventListener("pointercancel", session.cancel);
    }

    function endAllDragSessions() {
        for (const session of Array.from(dragSessions)) endDragSession(session);
    }

    // Dragging a marker or a clip moves that element, its card's two time fields and the
    // detail fields on every pointermove; the document is written once, on release, so one
    // drag is one history step. Dragging is clamped inside the video; typing an out-of-range
    // number is allowed and reported instead - silently moving a guide is what the plan forbids.
    // The guide is re-found by id on every move: writing into a stale object is how a drag
    // can "undo itself" after the list was rebuilt underneath it.
    function attachLaneDrag(surface, el, guide, widthFrames) {
        el.addEventListener("pointerdown", (event) => {
            if (event.button || !surface.scale) return;
            const range = timelineRange();
            if (!range.frames) return;
            const guideId = guide.id;
            const track = guide.kind === AUDIO_KIND ? surface.trackAudio : surface.trackImage;
            const rect = track.getBoundingClientRect();
            const grabbed = surface.scale.pxToFrame(event.clientX - rect.left + surface.scroll, { clamp: false });
            const offset = grabbed - Math.trunc(Number(guide.frame_index) || 0);
            const laneFrame = (clientX) => frameFromLanePointer({
                scale: surface.scale, scroll: surface.scroll, clientX, trackLeft: rect.left,
                offset, widthFrames, frameCount: range.frames,
            });
            const pointerId = event.pointerId;
            let moved = false;
            let panned = false;
            el.classList.add("dragging");
            // While a card is held it follows the pointer exactly: the declutter offset is a
            // resting-state rule, not a rule for the card under the cursor.
            for (const item of surface.laneItems) {
                if (item.guide.id === guideId) item.offsetPx = 0;
            }

            beginDragSession((moveEvent) => {
                if (pointerId !== undefined && moveEvent.pointerId !== pointerId) return;
                const live = guideById(guideId);
                if (!live) return;
                // Only the zoomed surface runs out of room: the node surface shows the whole
                // video, so there is nothing there to pan.
                const pointerX = moveEvent.clientX - rect.left;
                if (!surface.fitWidth) {
                    const wanted = scrollForPointerPan(surface.scale, surface.scroll, pointerX, rect.width, SCROLL_EDGE);
                    if (wanted !== null && wanted !== surface.scroll) {
                        surface.scroll = wanted;
                        doc.view_state.scroll = surface.scroll;
                        panned = true;
                    }
                }
                // The card stays pointerX minus the grab offset on screen whatever the scroll is,
                // so an edge pan moves the view without moving the card away from the cursor.
                const frame = laneFrame(moveEvent.clientX);
                if (frame !== live.frame_index) {
                    live.frame_index = frame;
                    for (const item of surface.laneItems) {
                        if (item.guide.id === guideId) item.frame = frame;
                    }
                    moved = true;
                    syncCardTime(live);
                    syncDetail(live);
                    showLiveNote(`${live.label} -> 第 ${frame} 帧（${formatSeconds(frameToSeconds(frame, doc.fps))} 秒）`);
                }
                applyAllScrolls();
            }, () => {
                el.classList.remove("dragging");
                if (moved && guideById(guideId)) writeDoc({ dirty: true });
                // A drag that only panned the view (a card held against an edge) still has to
                // keep that view after a reload.
                else if (panned) writeDoc({ dirty: false });
                renderAll();
            });
            event.preventDefault();
        });
    }

    // Left/Right moves the selected card by one frame, Shift by one second. Inside an
    // input the keys belong to the input.
    function laneKeyboard(signal) {
        root.addEventListener("keydown", (event) => {
            if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
            if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target?.tagName)) return;
            const guide = selectedGuide();
            if (!guide || guide.frame_index === null || guide.frame_index === undefined) return;
            const range = timelineRange();
            if (!range.frames) return;
            const spans = currentSpans();
            const widthFrames = guide.kind === AUDIO_KIND
                ? Math.ceil(Number(spans[guide.id]) || 0)
                : 1;
            const maxFrame = Math.max(0, range.frames - Math.max(1, widthFrames));
            const step = (event.shiftKey ? Math.max(1, Math.trunc(doc.fps)) : 1)
                * (event.key === "ArrowLeft" ? -1 : 1);
            const frame = Math.max(0, Math.min(maxFrame, Math.trunc(Number(guide.frame_index)) + step));
            if (frame === guide.frame_index) return;
            event.preventDefault();
            guide.frame_index = frame;
            writeDoc({ dirty: true });
            renderAll();
        }, { signal });
    }
    // ---------- the card pool ----------
    // One grid per tab, in list order, exactly like the picker and the reference
    // loaders: same grid, same 100%-400% card zoom, same drag-to-reorder. A card that
    // is not on the timeline yet keeps its place in the list and is marked 待放置
    // instead of being moved into a separate area, which would make the drag order and
    // the list order disagree.
    function activeTab() {
        return [IMAGE_KIND, AUDIO_KIND].includes(doc.view_state.active_tab) ? doc.view_state.active_tab : IMAGE_KIND;
    }

    function visibleGuides() {
        const kind = activeTab();
        return doc.guides.filter((guide) => guide.kind === kind);
    }

    function isPlaced(guide) {
        return guide.frame_index !== null && guide.frame_index !== undefined;
    }

    // v2 only: the strength belongs to the card, so it is shown on the card and edited in
    // the detail area - both from the same guide.strength. A v2 card always shows its
    // value, including 1.00, because "this card has no strength set" and "this card is at
    // the native 1.00" must not look like two different things. A 0.00 card also says 不加入:
    // the card is still on the timeline, and the node still will not encode it - both facts
    // have to be readable at the same time.
    function paintStrengthBadge(badge, guide, compact = false) {
        const strength = strengthOf(guide);
        const off = strength <= STRENGTH_OFF;
        badge.textContent = compact
            ? strength.toFixed(2)
            : (off ? "强度 0.00 · 不加入" : `强度 ${strength.toFixed(2)}`);
        badge.title = off
            ? "引导强度 0.00：卡片和插入位置都保留，但本次不会解码这张图，也不会加入 conditioning"
            : `引导强度 ${strength.toFixed(2)}：选中卡片后可在详情区修改；1.00 为原生行为`;
        badge.classList.toggle("h3guide-strength-native", strength >= STRENGTH_MAX);
        badge.classList.toggle("h3guide-strength-off", off);
    }

    function makeStrengthBadge(guide, compact = false) {
        const badge = make("div", `h3guide-strength${compact ? " h3guide-strength-compact" : ""}`);
        paintStrengthBadge(badge, guide, compact);
        return badge;
    }

    function syncStrengthBadge(card, guide) {
        const wrap = card.querySelector(".h3lvm-thumb-wrap");
        if (!wrap) return;
        const old = wrap.querySelector(".h3guide-strength");
        if (!perImageStrength || guide.kind !== IMAGE_KIND) {
            old?.remove();
            return;
        }
        if (old) {
            paintStrengthBadge(old, guide);
            return;
        }
        wrap.appendChild(makeStrengthBadge(guide));
    }

    function updateCardState(card, guide) {
        const placed = isPlaced(guide);
        card.classList.toggle("h3guide-off", guide.enabled === false);
        // v2 only: a 0.00 image card is enabled and placed but never encoded. It is drawn
        // between those two states, never greyed out like a disabled card.
        card.classList.toggle("h3guide-muted", perImageStrength && isMutedImage(guide));
        card.classList.toggle("h3guide-unplaced", !placed);
        card.classList.toggle("active", guide.id === doc.view_state.selected_id);
        // 放置 only makes sense for material that is not on the timeline yet. Leaving it on
        // every placed card pushed the buttons that are always needed onto a second row.
        const place = card.querySelector(".h3guide-place");
        if (place) place.hidden = placed;
        const wrap = card.querySelector(".h3lvm-thumb-wrap");
        if (!wrap) return;
        syncStrengthBadge(card, guide);
        const badge = wrap.querySelector(".h3lvm-active-badge");
        const text = !placed ? "待放置" : (guide.enabled === false ? "已停用" : "");
        if (!text) {
            badge?.remove();
            return;
        }
        if (badge) {
            badge.textContent = text;
            return;
        }
        wrap.appendChild(make("div", "h3lvm-active-badge", text));
    }

    // The card shows what a decision needs: the label, the file, the state and the time.
    // Resolution, occupied frames and the placeable range come from the video and change with
    // the latent, so they belong to the detail area - repeating them on every card is what
    // turned the pool into a wall of technical text with a big empty area beside it.
    function infoLinesFor(guide) {
        if (guide.kind === IMAGE_KIND) {
            const meta = imageCache.get(mediaKeyOf(guide));
            return meta?.error ? [meta.error] : [];
        }
        const status = audioStatus(audioMetaFor(guide));
        return status.waveform ? [] : [status.label];
    }

    function setCardInfo(card, lines) {
        for (const old of card.querySelectorAll(".h3lvm-seg-info")) old.remove();
        const meta = card.querySelector(".h3lvm-meta");
        if (!meta) return;
        for (const text of lines) meta.append(make("div", "h3lvm-seg-info", text));
    }

    function placeGuideOnTimeline(guide) {
        const range = timelineRange();
        const frame = nextFreeFrame(doc.guides, range.frames, currentSpans(), doc.fps);
        if (frame === null) {
            showLiveNote(range.frames ? "时间轴已经排满，放不下下一条 Guide 了" : "还没有可用的时间轴长度：填「时间轴长度（秒）」输入，或连接 latent 运行一次");
            return;
        }
        const next = patchGuide(doc.guides, guide.id, { frame_index: frame, enabled: true });
        if (!tryQuota(next, guide.kind)) return;
        mutate(next);
    }

    function buildCard(guide) {
        const card = make("div", "h3lvm-card h3guide-card");
        card.dataset.id = guide.id;

        // Only the picture/waveform is a drag handle. The card also holds two number fields
        // and five buttons, and a card that can be dragged from any of them turns "I am typing
        // a frame number" into "I started dragging the card". The picker and the manager still
        // drag the whole card, which is why this is not a shared-module change.
        // Nothing inside the card starts a native HTML5 drag. The card is a pointer-drag handle
        // except for its fields and buttons (see poolPointerDrag), and a draggable <img> would
        // start a browser drag image that competes with that gesture.
        const thumbWrap = make("div", "h3lvm-thumb-wrap");
        if (guide.kind === IMAGE_KIND) {
            // The thumbnail renderer only needs a url, and it is the same portrait-aware
            // one the picker uses, so a 9:16 frame shows whole here too.
            appendThumbnail(thumbWrap, { thumbnail_url: viewUrl(guide.asset) });
        } else {
            const wave = make("canvas", "h3guide-wave");
            const play = make("button", "h3guide-play", "▶");
            play.title = "试听：只播放会被输出的那一段";
            play.draggable = false;
            thumbWrap.append(wave, play);
            wirePlayer(play, guide);
        }
        card.appendChild(thumbWrap);

        const meta = make("div", "h3lvm-meta");
        meta.append(
            make("div", "h3lvm-seg-label", guide.label || ""),
            make("div", "h3lvm-seg-name", String(guide.asset.filename).split("/").pop()),
        );
        card.appendChild(meta);

        const time = make("div", "h3guide-time");
        const seconds = make("input", "h3guide-num h3guide-seconds");
        seconds.type = "number";
        seconds.step = String(SECOND_STEP);
        seconds.min = "0";
        seconds.placeholder = "待放置";
        seconds.title = "把这段素材放到输出的第几秒（整数帧吸附）";
        const frames = make("input", "h3guide-num h3guide-frames");
        frames.type = "number";
        frames.step = "1";
        frames.min = "0";
        frames.placeholder = "待放置";
        frames.title = "把这段素材放到输出的第几帧";
        for (const [field, label] of [[seconds, "插入秒"], [frames, "插入帧"]]) {
            const box = make("label", "h3guide-time-field");
            box.append(make("span", null, label), field);
            time.appendChild(box);
        }
        card.appendChild(time);

        // The crop belongs to the material, so it is editable on the card that owns it.
        // The detail area shows the same two fields; both write the same sample points.
        if (guide.kind === AUDIO_KIND) {
            // The crop fields start closed: the 裁切 button is what opens them. Without this the
            // box is visible on a fresh card, so the first click only flips the flag and looks dead.
            const crop = trimFields(guide);
            crop.hidden = !cropOpen.has(guide.id);
            card.appendChild(crop);
        }

        const acts = make("div", "h3guide-acts");
        const toggle = make("button", "h3guide-act", guide.enabled === false ? "启用" : "停用");
        toggle.title = "停用会保留这张卡片和它的时间，但不会执行";
        const place = make("button", "h3guide-act h3guide-place", "放置");
        place.title = "放到下一个空位（也可以直接把卡片或轨道上的标记拖到时间轴）";
        const replace = make("button", "h3guide-act", "替换");
        replace.title = "换素材：保留这条 Guide 的 ID 与时间";
        const copy = make("button", "h3guide-act", "复制");
        copy.title = "复制为新卡片，默认待放置，避免立刻和第 0 帧冲突";
        const remove = make("button", "h3guide-act warn", "删除");
        toggle.onclick = (event) => {
            event.stopPropagation();
            const next = patchGuide(doc.guides, guide.id, { enabled: guide.enabled === false });
            if (!tryQuota(next, guide.kind)) return;
            mutate(next);
        };
        place.onclick = (event) => {
            event.stopPropagation();
            placeGuideOnTimeline(guide);
        };
        replace.onclick = (event) => {
            event.stopPropagation();
            pendingReplaceId = guide.id;
            (guide.kind === AUDIO_KIND ? els.audioInput : els.imageInput).click();
        };
        copy.onclick = (event) => {
            event.stopPropagation();
            mutate(duplicateGuide(doc.guides, guide.id));
        };
        remove.onclick = (event) => {
            event.stopPropagation();
            mutate(removeGuide(doc.guides, guide.id));
        };
        acts.append(toggle, place, replace, copy, remove);
        if (guide.kind === AUDIO_KIND) {
            const cropBtn = make("button", "h3guide-act h3guide-crop-btn", "裁切");
            cropBtn.title = "在这张卡片上直接改源裁入/裁出（与详情区是同一份数据）";
            cropBtn.onclick = (event) => {
                event.stopPropagation();
                const open = !cropOpen.has(guide.id);
                if (open) cropOpen.add(guide.id);
                else cropOpen.delete(guide.id);
                const box = card.querySelector(".h3guide-crop");
                if (box) box.hidden = !open;
                cropBtn.classList.toggle("on", open);
                if (open) keepCardVisible(card);
            };
            if (cropOpen.has(guide.id)) cropBtn.classList.add("on");
            acts.insertBefore(cropBtn, replace);
        }
        card.appendChild(acts);

        seconds.addEventListener("change", () => applyTimeInput(guide, seconds.value, "seconds"));
        frames.addEventListener("change", () => applyTimeInput(guide, frames.value, "frames"));
        card.addEventListener("click", () => select(guide.id));
        cardEls.set(guide.id, card);
        syncCardTime(guide);
        updateCardState(card, guide);
        setCardInfo(card, infoLinesFor(guide));
        return card;
    }

    function applyTimeInput(guide, raw, unit) {
        const text = String(raw ?? "").trim();
        if (!text) {
            if (!isPlaced(guide)) return;
            doc.guides = ensureLabels(patchGuide(doc.guides, guide.id, { frame_index: null }));
            commitEdit();
            return;
        }
        const value = Number(text);
        if (!Number.isFinite(value)) return;
        const frame = unit === "seconds" ? secondsToFrame(value, doc.fps) : Math.round(value);
        if (isPlaced(guide) && frame === Math.trunc(Number(guide.frame_index))) return;
        // Out of range is kept, not clamped: the footer reports it and the marker is
        // drawn in red. Silently moving a guide to fit is what the plan forbids.
        const next = patchGuide(doc.guides, guide.id, { frame_index: frame, enabled: guide.enabled !== false });
        if (!tryQuota(next, guide.kind)) return;
        doc.guides = ensureLabels(next);
        commitEdit();
    }

    // The widget JSON must always be readable again, so the panel never writes a list
    // the node would reject: a change that would exceed the quota is refused with a
    // reason instead of being stored and lost on the next load.
    function tryQuota(candidate, kind) {
        const counts = countRunnable(candidate);
        if (kind === IMAGE_KIND && counts[IMAGE_KIND] > MAX_GUIDE_IMAGES) {
            showLiveNote(`启用的图片 Guide 最多 ${MAX_GUIDE_IMAGES} 个`);
            return false;
        }
        if (kind === AUDIO_KIND && counts[AUDIO_KIND] > MAX_GUIDE_AUDIOS) {
            showLiveNote(`启用的音频 Guide 最多 ${MAX_GUIDE_AUDIOS} 个`);
            return false;
        }
        const total = counts[IMAGE_KIND] + counts[AUDIO_KIND];
        if (total > MAX_GUIDE_TOTAL) {
            showLiveNote(`启用的 Guide 合计最多 ${MAX_GUIDE_TOTAL} 个`);
            return false;
        }
        return true;
    }

    function mutate(next) {
        if (!Array.isArray(next)) return;
        doc.guides = ensureLabels(next);
        if (doc.view_state.selected_id && !doc.guides.some((guide) => guide.id === doc.view_state.selected_id)) {
            doc.view_state.selected_id = null;
        }
        writeDoc({ dirty: true });
        renderAll();
    }

    function select(id) {
        if (doc.view_state.selected_id === id) return;
        doc.view_state.selected_id = id;
        writeDoc({ dirty: false });
        // Selection is view state. Rebuilding the pool here would destroy the input the
        // user is typing in, so only classes, the 定位 line and the detail area move.
        refreshSelection();
    }

    function syncCardTime(guide) {
        const card = cardEls.get(guide.id);
        if (!card) return;
        const placed = isPlaced(guide);
        const fields = [
            [".h3guide-seconds", placed ? formatSeconds(frameToSeconds(guide.frame_index, doc.fps), 3) : ""],
            [".h3guide-frames", placed ? String(Math.trunc(Number(guide.frame_index))) : ""],
        ];
        if (guide.kind === AUDIO_KIND) {
            const trim = trimWindow(guide, metaSource(audioMetaFor(guide)));
            fields.push(
                [".h3guide-crop-in", formatSeconds(trim.startSeconds, 3)],
                [".h3guide-crop-out", trim.endSeconds ? formatSeconds(trim.endSeconds, 3) : ""],
            );
        }
        for (const [selector, value] of fields) {
            const field = card.querySelector(selector);
            if (field && document.activeElement !== field) field.value = value;
        }
        updateCardState(card, guide);
    }

    function renderPool() {
        if (!root) return;
        generation += 1;
        cardEls.clear();
        const kind = activeTab();
        els.tabImage.classList.toggle("active", kind === IMAGE_KIND);
        els.tabAudio.classList.toggle("active", kind === AUDIO_KIND);
        els.poolKind.textContent = `当前显示 ${kind === IMAGE_KIND ? "图片卡片" : "音频卡片"}`;
        const held = { [IMAGE_KIND]: 0, [AUDIO_KIND]: 0 };
        for (const guide of doc.guides) {
            if (held[guide.kind] !== undefined) held[guide.kind] += 1;
        }
        els.countImage.textContent = `${held[IMAGE_KIND]} 张卡片`;
        els.countAudio.textContent = `${held[AUDIO_KIND]} 张卡片`;
        const counts = countRunnable(doc.guides);
        els.poolCounts.textContent = `启用 图片 ${counts[IMAGE_KIND]}/${MAX_GUIDE_IMAGES} · 音频 ${counts[AUDIO_KIND]}/${MAX_GUIDE_AUDIOS}`
            + ` · 合计 ${counts[IMAGE_KIND] + counts[AUDIO_KIND]}/${MAX_GUIDE_TOTAL} · 卡片 ${doc.guides.length}/${MAX_GUIDE_TOTAL}`;
        // Rebuilding the pool throws away the cards, so the players they own go with them:
        // a preview must not keep playing (or hold a decoded file) after its card is gone.
        for (const player of players) {
            player.onended = null;
            player.pause();
            player.src = "";
        }
        players.clear();
        els.deck.replaceChildren();
        for (const guide of visibleGuides()) els.deck.appendChild(buildCard(guide));
        void fillCards();
    }
    // ---------- media: uploaded, measured, drawn ----------
    const imageCache = new Map();     // mediaKey -> {width,height} | {error}
    let pendingReplaceId = null;

    function metaSource(meta) {
        if (!meta || !meta.sampleRate || !meta.sampleCount) return {};
        return { sample_rate: meta.sampleRate, sample_count: meta.sampleCount };
    }

    async function uploadFile(file) {
        const form = new FormData();
        // ComfyUI only has /upload/image and /upload/mask; the audio loader in this
        // plugin already uploads through /upload/image, and so does this one.
        form.append("image", file);
        form.append("subfolder", "");
        form.append("type", "input");
        const res = await api.fetchApi("/upload/image", { method: "POST", body: form });
        if (!res.ok) {
            const body = await res.text().catch(() => "");
            const detail = body.replace(/\s+/g, " ").trim().slice(0, 240);
            throw new Error(`HTTP ${res.status} ${res.statusText}${detail ? `：${detail}` : ""}`);
        }
        const data = await res.json().catch(() => ({}));
        if (!data.name) throw new Error("服务器没有返回文件名");
        return { filename: data.name, subfolder: data.subfolder || "", type: data.type || "input" };
    }

    function fileError(error) {
        return String(error?.message || error || "未知错误").replace(/\s+/g, " ").trim().slice(0, 300);
    }

    function importFiles(files, kind = null) {
        return addFiles(files, kind).catch((error) => {
            const reason = fileError(error);
            debugEvent("native-import-failed", { reason });
            showLiveNote(`素材载入失败：${reason}`);
        });
    }

    // Normalize FileList and Array at the same boundary. A native drop is not restricted to
    // the visible tab: each file becomes the card its own extension says it is.
    async function addFiles(files, kind = null) {
        if (!root) return;
        const list = Array.from(files ?? []);
        if (!list.length) {
            showLiveNote("没有读取到文件，请重新拖入或使用添加按钮");
            debugEvent("native-import-rejected", { reason: "empty-file-list" });
            return;
        }
        const wanted = KINDS.includes(kind) ? kind : null;
        const usable = list.filter((file) => {
            const found = mediaKind(file.name);
            return wanted ? found === wanted : KINDS.includes(found);
        });
        const wrong = list.length - usable.length;
        if (!usable.length) {
            const reason = wanted ? `只能添加${wanted === IMAGE_KIND ? "图片" : "音频"}文件` : "只能添加图片或音频文件";
            showLiveNote(`${reason}（${list.map((file) => file.name).join("、")}）`);
            debugEvent("native-import-rejected", {
                reason: "unsupported-files",
                names: list.map((file) => file.name),
                kinds: list.map((file) => mediaKind(file.name)),
            });
            return;
        }
        const incoming = [];
        const failed = [];
        for (const [position, file] of usable.entries()) {
            showLiveNote(`上传中 ${position + 1}/${usable.length}：${file.name}`);
            debugEvent("native-upload-start", { name: file.name, size: file.size, kind: mediaKind(file.name) });
            try {
                incoming.push(await uploadFile(file));
                debugEvent("native-upload-success", { name: file.name });
            } catch (error) {
                const reason = fileError(error);
                failed.push({ name: file.name, reason });
                debugEvent("native-upload-failed", { name: file.name, size: file.size, reason });
            }
        }
        const notes = [];
        if (failed.length) {
            notes.push(`上传失败 ${failed.length} 个：${failed.map((item) => `${item.name}（${item.reason}）`).join("；")}`);
        }
        if (wrong) notes.push(wanted ? `忽略 ${wrong} 个非${wanted === IMAGE_KIND ? "图片" : "音频"}文件` : `忽略 ${wrong} 个不支持的文件`);

        if (pendingReplaceId && guideById(pendingReplaceId)) {
            // Replacing keeps the Guide ID and its time: only the media changes.
            const guide = guideById(pendingReplaceId);
            pendingReplaceId = null;
            if (!incoming.length) {
                renderFooter();
                return;
            }
            const next = patchGuide(doc.guides, guide.id, { asset: incoming[0] });
            imageCache.delete(mediaKeyOf(guide));
            doc.guides = ensureLabels(next);
            writeDoc({ dirty: true });
            renderAll();
            if (notes.length) showLiveNote(notes.join(" · "));
            return;
        }
        pendingReplaceId = null;

        const result = addGuides(doc.guides, incoming, { maxTotal: MAX_GUIDE_TOTAL });
        doc.guides = result.guides;
        writeDoc({ dirty: true });
        // A dropped mp3 while the 图片 grid is open adds a card the user cannot see, which is the
        // second way a working drop looks like a dead one. Follow the file instead of the tab.
        const addedKinds = [...new Set(incoming.map((asset) => mediaKind(asset.filename)))];
        if (!wanted && addedKinds.length === 1 && addedKinds[0] !== activeTab()) {
            setTab(addedKinds[0]);
            notes.push(`已切到${addedKinds[0] === AUDIO_KIND ? "音频" : "图片"}卡片`);
        }
        renderAll();
        const summary = [`已添加 ${result.added} 个卡片（新卡片默认「待放置」，不会挤在第 0 帧）`];
        if (result.rejected) summary.push(`跳过 ${result.rejected} 个（重复、类型不符或超过 ${MAX_GUIDE_TOTAL} 个卡片）`);
        if (notes.length) summary.push(...notes);
        showLiveNote(summary.join(" · "));
    }

    async function loadImageMeta(guide) {
        const key = mediaKeyOf(guide);
        if (imageCache.has(key)) return imageCache.get(key);
        const meta = await new Promise((resolve) => {
            const image = new Image();
            image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight });
            image.onerror = () => resolve({ error: "图片读取失败" });
            image.src = viewUrl(guide.asset);
        });
        imageCache.set(key, meta);
        return meta;
    }

    // Audio readiness is a state machine, not a spinner. The cache entry is created as
    // {status: decoding} before the fetch starts, so a second render cannot start the same
    // decode twice, and it ends as ready / metadata_only / failed. Every label in the UI comes
    // from audioStatus(), so a card, a lane clip and the footer cannot disagree - which is
    // exactly how "reading audio..." and "validation passed" were shown at the same time.
    const audioInflight = new Set();

    async function loadAudioMeta(guide, { retry = false } = {}) {
        const key = mediaKeyOf(guide);
        if (audioInflight.has(key)) return audioCache.get(key) || null;
        const cached = audioCache.get(key);
        if (cached && !retry && cached.status !== AUDIO_FAILED) return cached;
        audioInflight.add(key);
        audioCache.set(key, { status: AUDIO_DECODING });
        const url = viewUrl(guide.asset);
        let meta = null;
        try {
            const res = await fetch(url);
            const buffer = await res.arrayBuffer();
            // Waveforms are CPU work. Decoding is what gives the real sample rate and sample
            // count, so it is worth doing - but not for a file big enough to stall the page.
            if (buffer.byteLength <= MAX_DECODE_BYTES) {
                const Ctor = window.AudioContext || window.webkitAudioContext;
                if (Ctor) {
                    const context = new Ctor();
                    try {
                        const decoded = await context.decodeAudioData(buffer.slice(0));
                        meta = {
                            status: AUDIO_READY,
                            duration: decoded.duration,
                            sampleRate: decoded.sampleRate,
                            sampleCount: decoded.length,
                            channels: decoded.numberOfChannels,
                            peaks: waveformPeaks(decoded),
                        };
                    } finally {
                        context.close?.();
                    }
                }
            }
        } catch (error) {
            meta = null;
        }
        if (!meta) {
            // No waveform, but a real duration: that is enough for the trim fields and the
            // preview, so it is its own state rather than a failure.
            const duration = await new Promise((resolve) => {
                const probe = new Audio();
                probe.preload = "metadata";
                probe.onloadedmetadata = () => resolve(probe.duration);
                probe.onerror = () => resolve(0);
                probe.src = url;
            });
            meta = duration > 0
                ? { status: AUDIO_METADATA_ONLY, duration }
                : { status: AUDIO_FAILED, error: "音频读取失败：浏览器无法解码这个文件" };
        }
        audioCache.set(key, meta);
        audioInflight.delete(key);
        if (meta.status === AUDIO_READY) {
            // The card stores sample points, so the real numbers belong on it; the node
            // re-decodes the file at run time either way.
            for (const other of doc.guides) {
                if (other.kind !== AUDIO_KIND || mediaKeyOf(other) !== key) continue;
                if (!other.sample_rate) other.sample_rate = meta.sampleRate;
                if (!other.source_end_sample) other.source_end_sample = meta.sampleCount;
            }
            writeDoc({ dirty: false });
        }
        return meta;
    }

    // Every audio guide gets its metadata, not only the cards on the visible tab: the audio
    // lane is drawn under the image tab too, and the overlap check needs all of them. One
    // decode per file (keyed by mediaKey), and the lanes/footer refresh as each one lands.
    async function refreshAudioMeta() {
        const at = generation;
        const seen = new Set();
        for (const guide of doc.guides) {
            if (guide.kind !== AUDIO_KIND) continue;
            const key = mediaKeyOf(guide);
            if (seen.has(key)) continue;
            seen.add(key);
            await loadAudioMeta(guide);
            if (at !== generation || !root) return;
            for (const other of doc.guides) {
                if (other.kind !== AUDIO_KIND || mediaKeyOf(other) !== key) continue;
                const card = cardEls.get(other.id);
                if (card) paintCardAudio(card, other);
            }
            renderTimeline();
            renderFooter();
        }
    }

    function waveformPeaks(buffer, buckets = 96) {
        try {
            const data = buffer.getChannelData(0);
            if (!data?.length) return null;
            const step = Math.max(1, Math.floor(data.length / buckets));
            const peaks = [];
            for (let start = 0; start < data.length; start += step) {
                let peak = 0;
                for (let index = start; index < Math.min(data.length, start + step); index++) {
                    const value = Math.abs(data[index]);
                    if (value > peak) peak = value;
                }
                peaks.push(peak);
            }
            return peaks;
        } catch (error) {
            return null;
        }
    }

    // Blue bars are what H3 receives, grey bars are what it does not. On a lane clip the
    // whole bar is the trimmed window, so everything is blue (win = null).
    function drawWave(canvas, peaks, win) {
        const box = canvas.getBoundingClientRect();
        if (!box.width || !box.height) return;
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.round(box.width * ratio);
        canvas.height = Math.round(box.height * ratio);
        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        const total = Number(win?.total) || 0;
        const from = total > 0 ? (Number(win?.first) || 0) / total : 0;
        const to = total > 0 ? (Number(win?.last) ?? total) / total : 1;
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

    // One card plays at a time, and only the trimmed window: that is the difference
    // between a real preview and a decoration.
    // A flat line is not a waveform. When there are no peaks the canvas is cleared and the
    // card shows the status text instead, so "reading", "no waveform" and "failed" are visible
    // states instead of a decoration that looks like audio.
    function paintWave(canvas, meta, win) {
        const status = audioStatus(meta);
        if (canvas) {
            const ctx = canvas.getContext("2d");
            if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
            if (status.waveform) drawWave(canvas, meta.peaks, win);
        }
        return status;
    }

    // One place paints an audio card's thumbnail area: the waveform (or the honest placeholder
    // for the state we are in) and, when reading failed, a retry that is not a spinner.
    function paintCardAudio(card, guide) {
        const wrap = card.querySelector(".h3lvm-thumb-wrap");
        const canvas = card.querySelector(".h3guide-wave");
        const meta = audioMetaFor(guide);
        const trim = trimWindow(guide, metaSource(meta));
        const status = paintWave(canvas, meta, { first: trim.startSeconds, last: trim.endSeconds, total: meta?.duration || 0 });
        if (!wrap) return status;
        wrap.classList.toggle("h3guide-wave-none", !status.waveform);
        let note = wrap.querySelector(".h3guide-wave-note");
        if (!note) {
            note = make("span", "h3guide-wave-note");
            wrap.appendChild(note);
        }
        note.textContent = status.waveform ? "" : status.label;
        const retry = wrap.querySelector(".h3guide-retry");
        if (status.retry) {
            const button = retry || make("button", "h3guide-retry", "重试读取");
            button.onclick = (event) => {
                event.stopPropagation();
                void retryAudio(guide.id);
            };
            if (!button.parentElement) wrap.appendChild(button);
        } else if (retry) {
            retry.remove();
        }
        return status;
    }

    async function retryAudio(guideId) {
        const guide = guideById(guideId);
        if (!guide) return;
        audioCache.delete(mediaKeyOf(guide));
        await loadAudioMeta(guide, { retry: true });
        if (!root) return;
        for (const [id, card] of cardEls) {
            const other = guideById(id);
            if (other && other.kind === AUDIO_KIND) paintCardAudio(card, other);
        }
        renderTimeline();
        renderFooter();
    }

    // One card plays at a time, and only the trimmed window: that is the difference between a
    // real preview and a decoration. The source trim decides which part of the recording is
    // used; the insert time decides where it lands in the video. They are never mixed here.
    function wirePlayer(play, guide) {
        const audio = new Audio();
        audio.preload = "none";
        audio.src = viewUrl(guide.asset);
        players.add(audio);

        const reset = () => { play.textContent = "▶"; };
        // The document is immutable: patchGuide() hands back a new object, and a committed edit
        // deliberately does not rebuild the card. So the guide captured when the card was built goes
        // stale the moment the user types a new trim - re-resolve it by id on every read, or the
        // player keeps using the window that existed before the edit.
        const liveGuide = () => guideById(guide.id) || guide;
        const trimOf = () => {
            const live = liveGuide();
            return trimWindow(live, metaSource(audioMetaFor(live)));
        };
        audio.addEventListener("ended", reset);
        audio.addEventListener("timeupdate", () => {
            const trim = trimOf();
            if (!audio.paused && trim.endSeconds && audio.currentTime >= trim.endSeconds) {
                audio.pause();
                reset();
            }
            const canvas = play.parentElement?.querySelector(".h3guide-wave");
            if (canvas) {
                const meta = audioMetaFor(liveGuide());
                paintWave(canvas, meta, { first: trim.startSeconds, last: trim.endSeconds, total: meta?.duration || 0 });
            }
        });
        play.onclick = (event) => {
            event.stopPropagation();
            if (!audio.paused) {
                audio.pause();
                reset();
                return;
            }
            for (const other of players) {
                if (other !== audio) other.pause();
            }
            const trim = trimOf();
            const end = trim.endSeconds || Number(audio.duration) || 0;
            if (!(audio.currentTime >= trim.startSeconds && audio.currentTime < end)) {
                audio.currentTime = trim.startSeconds;
            }
            audio.play?.().catch(() => {
                // the browser blocked it, or the file is gone; the card stays usable
            });
            play.textContent = "⏸";
        };
    }

    async function fillCards() {
        const at = generation;
        for (const guide of visibleGuides()) {
            if (guide.kind === IMAGE_KIND) await loadImageMeta(guide);
            if (at !== generation || !root) return;
            const card = cardEls.get(guide.id);
            if (!card) continue;
            setCardInfo(card, infoLinesFor(guide));
            if (guide.kind === AUDIO_KIND) paintCardAudio(card, guide);
        }
        if (at === generation && root) void refreshAudioMeta();
    }
    // ---------- two different things can land on the pool ----------
    // An external file drag stays native HTML5 drag and drop: it reports "Files" and uploads.
    // Everything internal - reordering a card, dropping a card onto a lane - is a pointer
    // gesture that shares the session, the coordinate maths and the cleanup rules of the lane
    // drag. Two reasons, both learned the hard way: a native drag cannot be driven by a real
    // mouse through CDP, so it can never be verified here; and its drag image, dragleave
    // ordering and "which element is under the pointer" rules are not the ones the timeline
    // needs. A pointer session decides the target from coordinates, which is what the lane drag
    // already does correctly.
    function poolFileDrop(signal) {
        const dragTypes = (event) => Array.from(event.dataTransfer?.types ?? []);
        const isFileDrag = (event) => dragTypes(event).includes("Files");

        // The whole 卡片池 section accepts a file, not only the card grid. The title bar with the
        // 卡片大小 control is part of the area a user aims at, and a drop on the section's padding
        // would otherwise be thrown away without a word. The highlight still goes on the grid,
        // because that is where the cards appear.
        const insidePool = (event) => {
            const rect = els.pool.getBoundingClientRect();
            return event.clientX >= rect.left && event.clientX <= rect.right
                && event.clientY >= rect.top && event.clientY <= rect.bottom;
        };

        root.addEventListener("dragstart", (event) => {
            const card = event.target?.closest?.(".h3lvm-card");
            if (!card || !els.deck.contains(card)) return;
            // Our own cards never start a native drag: the pointer gesture owns them. Without
            // this Chrome starts one for the <img> inside the card and two systems fight over
            // the same press.
            event.preventDefault();
            debugEvent("native-dragstart-suppressed", { guideId: card.dataset.id, types: dragTypes(event) });
        }, { signal });

        root.addEventListener("dragover", (event) => {
            if (!isFileDrag(event)) {
                debugEvent("native-dragover-rejected", { reason: "not-a-file-drag", types: dragTypes(event) });
                return;
            }
            if (!insidePool(event)) {
                debugEvent("native-dragover-rejected", {
                    reason: "outside-pool",
                    point: [event.clientX, event.clientY],
                    hit: describePoint(event.clientX, event.clientY),
                });
                return;
            }
            // ComfyUI also listens for file drops on the document and would create a
            // LoadImage node from the same file.
            event.preventDefault();
            event.stopPropagation();
            event.dataTransfer.dropEffect = "copy";
            els.deck.classList.add("h3guide-drop");
            debugEvent("native-dragover", {
                types: dragTypes(event),
                defaultPrevented: event.defaultPrevented,
                dropEffect: event.dataTransfer.dropEffect,
            });
        }, { signal });

        root.addEventListener("dragleave", (event) => {
            if (!isFileDrag(event)) return;
            if (els.pool.contains(event.relatedTarget)) return;
            els.deck.classList.remove("h3guide-drop");
        }, { signal });

        root.addEventListener("drop", (event) => {
            if (!isFileDrag(event)) {
                debugEvent("native-drop-rejected", { reason: "not-a-file-drag", types: dragTypes(event) });
                return;
            }
            if (!insidePool(event)) {
                debugEvent("native-drop-rejected", {
                    reason: "outside-pool",
                    point: [event.clientX, event.clientY],
                    hit: describePoint(event.clientX, event.clientY),
                });
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            els.deck.classList.remove("h3guide-drop");
            const files = Array.from(event.dataTransfer?.files ?? []);
            debugEvent("native-drop", {
                types: dragTypes(event),
                files: files.length,
                kinds: files.map((file) => mediaKind(file.name)),
            });
            void importFiles(files, null);
        }, { signal });
    }

    // Press a card anywhere that is not a field or a button, move a few pixels, and a small
    // fixed preview follows the pointer. The landing spot comes from coordinates
    // (resolveDropTarget + frameFromLanePointer), never from event.target: during a pointer
    // gesture the target is the card, not the lane. One ghost per gesture - it is moved, never
    // rebuilt. A cross-kind lane is refused out loud instead of silently landing elsewhere.
    function poolPointerDrag(signal) {
        const NOT_A_HANDLE = "input, button, select, textarea, .h3guide-time, .h3guide-acts, .h3guide-crop, .h3guide-play";
        const PREVIEW_OFFSET = 14;
        let gesture = null;
        let session = null;
        let scrollFrame = 0;

        const hideLaneHint = () => {
            if (gesture?.ghost) {
                gesture.ghost.remove();
                gesture.ghost = null;
                gesture.ghostTrack = null;
            }
            for (const track of [editorSurface?.trackImage, editorSurface?.trackAudio]) {
                if (track) track.classList.remove("h3guide-lane-drop");
            }
        };

        const hideCardHint = () => {
            for (const card of els.deck.querySelectorAll(".h3guide-drop-before, .h3guide-drop-after")) {
                card.classList.remove("h3guide-drop-before", "h3guide-drop-after");
            }
        };

        const cardRects = (visible) => {
            const rects = [];
            for (const [index, guide] of visible.entries()) {
                const rect = cardEls.get(guide.id)?.getBoundingClientRect();
                if (rect) rects.push({ index, left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom });
            }
            return rects;
        };

        const showCardHint = (at, visible) => {
            hideCardHint();
            if (at < 0) return;
            if (at >= visible.length) {
                cardEls.get(visible[visible.length - 1]?.id)?.classList.add("h3guide-drop-after");
                return;
            }
            cardEls.get(visible[at].id)?.classList.add("h3guide-drop-before");
        };

        // The lane ROW is the target: the track plus its label column. The lane header (tabs,
        // add, height) and the resize grip are siblings of the row, so they are not targets -
        // "any blank space is a lane" is what made the old hint impossible to trust.
        const laneRects = () => {
            const rows = [];
            for (const [kind, row, track] of [
                [IMAGE_KIND, els.rowImage, editorSurface?.trackImage],
                [AUDIO_KIND, els.rowAudio, editorSurface?.trackAudio],
            ]) {
                if (!row || !track) continue;
                const rect = row.getBoundingClientRect();
                rows.push({
                    kind,
                    left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom,
                    trackLeft: track.getBoundingClientRect().left,
                });
            }
            return rows;
        };

        const deckRect = () => {
            const rect = els.deck.getBoundingClientRect();
            return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
        };

        // One answer for "where would this land", used by the ghost and by the drop, so the
        // preview can never promise a frame the drop does not use.
        const targetAt = (clientX, clientY) => {
            const guide = guideById(gesture.guideId);
            if (!guide) return { type: "none", reason: "guide-gone" };
            const range = timelineRange();
            if (!range.frames) return { type: "none", reason: "no-frame-count" };
            const hit = resolveDropTarget({
                clientX, clientY, kind: guide.kind, lanes: laneRects(), deck: deckRect(),
            });
            if (hit.type !== "lane") return hit;
            const widthFrames = guide.kind === AUDIO_KIND
                ? Math.max(1, Math.ceil(Number(currentSpans()[guide.id]) || 0))
                : 1;
            const frame = frameFromLanePointer({
                scale: editorSurface.scale, scroll: editorSurface.scroll, clientX,
                trackLeft: hit.lane.trackLeft, widthFrames, frameCount: range.frames,
            });
            if (frame === null) return { type: "none", reason: "frame-null" };
            return {
                type: "lane",
                frame,
                widthFrames,
                track: guide.kind === AUDIO_KIND ? editorSurface.trackAudio : editorSurface.trackImage,
            };
        };

        const showGhost = (target) => {
            if (!gesture.ghost) {
                gesture.ghost = make("div", "h3guide-drop-ghost");
                target.track.appendChild(gesture.ghost);
                gesture.ghostTrack = target.track;
            } else if (gesture.ghostTrack !== target.track) {
                gesture.ghost.remove();
                target.track.appendChild(gesture.ghost);
                gesture.ghostTrack = target.track;
            }
            const scale = editorSurface.scale;
            gesture.ghost.style.left = `${scale.markerPx(target.frame) - editorSurface.scroll}px`;
            if (target.widthFrames > 1) {
                gesture.ghost.style.width = `${Math.max(12, Math.round(scale.markerPx(target.frame + target.widthFrames) - scale.markerPx(target.frame)))}px`;
            } else {
                gesture.ghost.style.width = "";
            }
            gesture.ghost.textContent = `${target.frame}f`;
            target.track.classList.add("h3guide-lane-drop");
        };

        const setNote = (text) => {
            if (gesture?.note) gesture.note.textContent = text || "";
        };

        const showPreview = (clientX, clientY, guide) => {
            if (!gesture.preview) {
                const preview = make("div", "h3guide-drag-preview");
                if (guide.kind === IMAGE_KIND) {
                    const shot = make("img", "h3guide-drag-shot");
                    shot.src = viewUrl(guide.asset);
                    preview.appendChild(shot);
                } else {
                    preview.appendChild(make("span", "h3guide-drag-shot", "♪"));
                }
                preview.append(make("span", "h3guide-drag-label", guide.label || ""));
                const note = make("span", "h3guide-drag-note");
                preview.appendChild(note);
                document.body.appendChild(preview);
                gesture.preview = preview;
                gesture.note = note;
            }
            gesture.preview.style.left = `${clientX + PREVIEW_OFFSET}px`;
            gesture.preview.style.top = `${clientY + PREVIEW_OFFSET}px`;
        };

        // The deck scrolls on its own (the pool grows with the panel), so a row out of view has
        // to be reachable while the pointer is held near the deck edge.
        const startAutoScroll = () => {
            if (scrollFrame) return;
            const step = () => {
                scrollFrame = requestAnimationFrame(step);
                if (!gesture || !gesture.pointerY || !root) return;
                const rect = els.deck.getBoundingClientRect();
                if (gesture.pointerY < rect.top + SCROLL_EDGE) els.deck.scrollTop -= 12;
                else if (gesture.pointerY > rect.bottom - SCROLL_EDGE) els.deck.scrollTop += 12;
            };
            scrollFrame = requestAnimationFrame(step);
        };
        const stopAutoScroll = () => {
            if (!scrollFrame) return;
            cancelAnimationFrame(scrollFrame);
            scrollFrame = 0;
        };

        const placeOnLane = (guideId, frame) => {
            const guide = guideById(guideId);
            if (!guide) return;
            if (isPlaced(guide) && Math.trunc(Number(guide.frame_index)) === frame) return;
            const next = patchGuide(doc.guides, guideId, { frame_index: frame, enabled: true });
            if (!tryQuota(next, guide.kind)) return;
            mutate(next);
            showLiveNote(`${guide.label} -> 第 ${frame} 帧（${formatSeconds(frameToSeconds(frame, doc.fps))} 秒）`);
        };

        const targetIndex = (at, visible, fromId) => {
            const withoutMoved = doc.guides.filter((guide) => guide.id !== fromId);
            if (at >= visible.length) {
                const last = withoutMoved.findIndex((guide) => guide.id === visible[visible.length - 1]?.id);
                return last < 0 ? withoutMoved.length : last + 1;
            }
            return withoutMoved.findIndex((guide) => guide.id === visible[at].id);
        };

        // Every exit goes through here: release, Escape, pointercancel, closing the editor and
        // removing the node. The preview lives on document.body, so forgetting this leaves a
        // card-shaped ghost on screen forever.
        const cleanup = () => {
            if (!gesture) return;
            const { preview, ghost, card } = gesture;
            gesture = null;
            session = null;
            preview?.remove();
            ghost?.remove();
            card?.classList.remove("h3guide-dragging");
            if (root && els) {
                hideLaneHint();
                hideCardHint();
            }
            stopAutoScroll();
        };

        const move = (event) => {
            if (!gesture) return;
            if (!guideById(gesture.guideId)) {
                debugEvent("pointer-drag-cancel", { reason: "guide-gone", guideId: gesture.guideId });
                cleanup();
                return;
            }
            const dragged = guideById(gesture.guideId);
            showPreview(event.clientX, event.clientY, dragged);
            const target = targetAt(event.clientX, event.clientY);
            gesture.target = target;
            if (target.type === "lane") {
                // Aiming at a lane must not scroll the card pool at the same time.
                gesture.pointerY = 0;
                hideCardHint();
                showGhost(target);
                setNote(`放到第 ${target.frame} 帧`);
            } else if (target.type === "wrong-lane") {
                gesture.pointerY = 0;
                hideCardHint();
                hideLaneHint();
                // The hint names the lane the card belongs to, not the lane under the pointer.
                // "请拖至图片轨" while the pointer is already on the image lane says nothing useful.
                setNote(dragged?.kind === IMAGE_KIND ? "请拖至图片轨" : "请拖至音频轨");
            } else if (target.type === "pool") {
                gesture.pointerY = event.clientY;
                hideLaneHint();
                const visible = visibleGuides();
                const from = visible.findIndex((item) => item.id === gesture.guideId);
                const at = insertPosition(cardRects(visible), event.clientX, event.clientY, from);
                showCardHint(at === from || at === from + 1 ? -1 : at, visible);
                setNote("卡片池排序");
            } else {
                gesture.pointerY = 0;
                hideLaneHint();
                hideCardHint();
                setNote("");
            }
            debugEvent("pointer-dragmove", {
                guideId: gesture.guideId,
                target: {
                    type: target.type,
                    frame: target.frame ?? null,
                    laneKind: target.laneKind ?? null,
                    reason: target.reason ?? null,
                },
                hit: describePoint(event.clientX, event.clientY),
                rootConnected: Boolean(root?.isConnected),
                deckConnected: Boolean(els?.deck?.isConnected),
                sourceInDom: Boolean(gesture.card?.isConnected),
                composedPath: (event.composedPath?.() ?? []).slice(0, 6).map((item) => describeTarget(item)),
            });
        };

        const start = (guideId, card, event) => {
            const guide = guideById(guideId);
            if (!guide) return false;
            gesture = {
                guideId, card, pointerId: event.pointerId,
                pointerY: 0, target: null, preview: null, ghost: null, ghostTrack: null, note: null,
            };
            card.classList.add("h3guide-dragging");
            showPreview(event.clientX, event.clientY, guide);
            startAutoScroll();
            debugEvent("pointer-dragstart", {
                guideId,
                kind: guide.kind,
                rootConnected: Boolean(root?.isConnected),
                deckConnected: Boolean(els?.deck?.isConnected),
                sourceInDom: Boolean(card.isConnected),
                lanes: laneRects().map((lane) => ({
                    kind: lane.kind,
                    left: Math.round(lane.left), top: Math.round(lane.top),
                    right: Math.round(lane.right), bottom: Math.round(lane.bottom),
                })),
                deck: deckRect(),
            });
            return true;
        };

        const finish = (event, cancelled) => {
            if (!gesture) return;
            const guideId = gesture.guideId;
            const hasPoint = !cancelled && Number.isFinite(event?.clientX) && Number.isFinite(event?.clientY);
            const target = hasPoint ? targetAt(event.clientX, event.clientY) : gesture.target;
            debugEvent("pointer-dragend", {
                guideId,
                cancelled: Boolean(cancelled),
                target: { type: target?.type ?? null, frame: target?.frame ?? null, reason: target?.reason ?? null },
                clientX: event?.clientX ?? null,
                clientY: event?.clientY ?? null,
            });
            cleanup();
            if (!hasPoint || !target) return;
            if (target.type === "lane") {
                placeOnLane(guideId, target.frame);
                return;
            }
            // A cross-kind lane and "nowhere" leave the data exactly as it was.
            if (target.type !== "pool") return;
            const visible = visibleGuides();
            const from = visible.findIndex((guide) => guide.id === guideId);
            if (from < 0) return;
            const at = insertPosition(cardRects(visible), event.clientX, event.clientY, from);
            if (at < 0) return;
            const to = targetIndex(at, visible, guideId);
            if (to < 0) return;
            doc.guides = moveGuide(doc.guides, guideId, to);
            writeDoc({ dirty: true });
            renderPool();
            renderFooter();
        };

        root.addEventListener("pointerdown", (event) => {
            if (event.button !== 0) return;
            // Touch keeps its own behaviour: the deck scrolls with a swipe, and a
            // threshold-based pointer drag would fight that.
            if (event.pointerType === "touch") return;
            const card = event.target?.closest?.(".h3lvm-card");
            if (!card || !els.deck.contains(card)) return;
            if (event.target?.closest?.(NOT_A_HANDLE)) {
                debugEvent("pointerdown-ignored", {
                    reason: "interactive-control", guideId: card.dataset.id, hit: describeTarget(event.target),
                });
                return;
            }
            const guideId = card.dataset.id;
            const startX = event.clientX;
            const startY = event.clientY;
            const pointerId = event.pointerId;
            let started = false;
            debugEvent("pointerdown", { guideId, startX, startY, hit: describeTarget(event.target) });
            session = beginDragSession((moveEvent) => {
                if (pointerId !== undefined && moveEvent.pointerId !== pointerId) return;
                if (!started) {
                    if (!passedDragThreshold({ dx: moveEvent.clientX - startX, dy: moveEvent.clientY - startY, threshold: DRAG_START_PX })) return;
                    started = start(guideId, card, moveEvent);
                    if (!started) return;
                }
                move(moveEvent);
            }, (endEvent, cancelled) => {
                session = null;
                finish(endEvent, cancelled);
            });
        }, { signal });

        // On window, not on root: grabbing a card with the mouse leaves focus on <body>, so a
        // keydown bound to the panel would never reach this handler. The guard on `gesture` keeps
        // the key harmless whenever no card is held.
        window.addEventListener("keydown", (event) => {
            if (event.key !== "Escape" || !gesture) return;
            debugEvent("pointer-drag-cancel", { reason: "escape", guideId: gesture.guideId });
            if (session) endDragSession(session);
            cleanup();
        }, { signal });

        // Closing the editor and removing the node both end here: the preview is not inside
        // root, so removing root would not remove it.
        poolDragCleanup = cleanup;
    }
    // ---------- F. selected item detail ----------
    // The card has the two time fields; the detail area is where the audio trim and the
    // derived numbers live, because those need labels the card has no room for.
    function detailField(labelText, className, { type = "number", step = "1", min = "0", width = null } = {}) {
        const box = make("label", "h3guide-field");
        box.append(make("span", null, labelText));
        const input = make("input", `h3guide-num ${className}`);
        input.type = type;
        input.step = step;
        input.min = min;
        if (width) input.style.width = `${width}px`;
        box.appendChild(input);
        return { box, input };
    }

    // Which audio cards show their crop fields. This is panel behaviour, not document data:
    // the values themselves are the guide's own sample points, which the detail area edits too.
    const cropOpen = new Set();

    // The card pool is a scroll container that is often shorter than one card, so opening the
    // crop fields can push the button that opens them (and the fields themselves) below its
    // bottom edge. scrollIntoView({block:"nearest"}) under-scrolls here because the card grows in
    // the same frame, so the deck is scrolled by the measured difference instead.
    function keepCardVisible(card) {
        const deck = card.closest(".h3lvm-deck");
        if (!deck) return;
        const deckBox = deck.getBoundingClientRect();
        const cardBox = card.getBoundingClientRect();
        if (cardBox.bottom > deckBox.bottom) deck.scrollTop += cardBox.bottom - deckBox.bottom;
        else if (cardBox.top < deckBox.top) deck.scrollTop -= deckBox.top - cardBox.top;
    }
    let detailPlayer = null;

    function releaseDetailPlayer() {
        if (!detailPlayer) return;
        detailPlayer.pause();
        detailPlayer.onended = null;
        detailPlayer.src = "";
        players.delete(detailPlayer);
        detailPlayer = null;
    }

    // One trim editor, used by the card and by the detail area, so the two cannot disagree.
    function trimFields(guide, className = "h3guide-crop") {
        const meta = audioMetaFor(guide);
        const trim = trimWindow(guide, metaSource(meta));
        const box = make("div", className);
        const start = detailField("源裁入秒", "h3guide-crop-in", { step: String(SECOND_STEP) });
        const end = detailField("源裁出秒", "h3guide-crop-out", { step: String(SECOND_STEP) });
        start.input.title = "使用原录音的哪一段（起点）";
        end.input.title = "使用原录音的哪一段（终点）；留空或 0 表示用到结尾";
        start.input.value = formatSeconds(trim.startSeconds, 3);
        end.input.value = trim.endSeconds ? formatSeconds(trim.endSeconds, 3) : "";
        const apply = () => applyTrimSeconds(guide, start.input.value, end.input.value);
        start.input.addEventListener("change", apply);
        end.input.addEventListener("change", apply);
        box.append(start.box, end.box);
        return box;
    }

    function applyTrimSeconds(guide, rawStart, rawEnd) {
        const meta = audioMetaFor(guide);
        const next = patchGuide(doc.guides, guide.id,
            trimFromSeconds({ ...metaSource(meta), sample_count: meta?.sampleCount }, rawStart, rawEnd));
        doc.guides = ensureLabels(next);
        commitEdit();
    }

    // v2 only. Clamped and snapped to the 0.05 grid here, so typing 0.75 or 0.9 lands on a
    // step the node accepts instead of an arbitrary float.
    function applyStrengthInput(guide, raw) {
        let strength;
        try {
            strength = normalizeStrength(raw);
        } catch (error) {
            showLiveNote(`引导强度无效：${error.message}`);
            syncDetail(guide);
            return;
        }
        mutate(patchGuide(doc.guides, guide.id, { strength }));
    }

    // The detail area is a list of labelled rows, not one long line. renderDetail builds the
    // rows and syncDetail refills them, so a drag updates exactly what the user can edit.
    function detailSpec(guide) {
        const range = timelineRange();
        const placed = isPlaced(guide);
        const rows = [
            { label: "编号", key: "label", value: guide.label || "待生成" },
            { label: "文件名", key: "file", value: String(guide.asset.filename).split("/").pop() },
            {
                label: placed ? "插入秒" : "插入秒（待放置）", key: "seconds", step: String(SECOND_STEP),
                title: "把这段素材放到输出的第几秒（整数帧吸附）",
                value: placed ? formatSeconds(frameToSeconds(guide.frame_index, doc.fps), 3) : "",
            },
            {
                label: placed ? "插入帧" : "插入帧（待放置）", key: "frames", step: "1",
                title: "把这段素材放到输出的第几帧",
                value: placed ? String(Math.trunc(Number(guide.frame_index))) : "",
            },
        ];
        if (guide.kind === IMAGE_KIND) {
            if (perImageStrength) {
                rows.push({
                    label: "引导强度", key: "strength", step: String(STRENGTH_STEP),
                    min: String(STRENGTH_MIN), max: String(STRENGTH_MAX),
                    title: "这张图对生成画面的约束强度（0.00 - 1.00，默认 1.00 就是原生行为）。"
                        + "数值越低，画面越自由，动作与场景衔接的空间越大；它不是保留像素的百分比。"
                        + "0.00 表示这张图片不加入本次生成：卡片、插入位置和这个数值都保留，但不会解码它、不会加入 conditioning。",
                    value: strengthOf(guide).toFixed(2),
                });
            }
            const meta = imageCache.get(mediaKeyOf(guide));
            const held = guideFramesFor(1);
            rows.push({
                label: "素材信息", key: "media",
                value: meta?.error ? meta.error
                    : (meta ? `源图 ${meta.width}×${meta.height} · 占用 ${held} 帧` : "读取中…"),
            });
            if (range.frames) {
                rows.push({ label: "可放范围", key: "room", value: `0 – ${range.frames - held} 帧（视频共 ${range.frames} 帧）` });
            }
            return rows;
        }
        const meta = audioMetaFor(guide);
        const status = audioStatus(meta);
        const trim = trimWindow(guide, metaSource(meta));
        const span = Number(currentSpans()[guide.id]) || 0;
        rows.push({ label: "源裁入秒", key: "in", step: String(SECOND_STEP), title: "使用原录音的哪一段（起点）", value: formatSeconds(trim.startSeconds, 3) });
        rows.push({
            label: "源裁出秒", key: "out", step: String(SECOND_STEP),
            title: "使用原录音的哪一段（终点）；留空或 0 表示用到结尾",
            value: trim.endSeconds ? formatSeconds(trim.endSeconds, 3) : "",
        });
        rows.push({
            label: "音频信息", key: "audio",
            value: status.label + (meta?.sampleRate ? ` · ${meta.sampleCount} 采样点 · ${meta.channels || "?"} 声道` : ""),
        });
        rows.push({
            label: "有效时长", key: "usable",
            value: status.confirmed ? `${formatSeconds(trim.durationSeconds, 3)}s · ${trim.sampleCount} 采样点` : "音频信息未确认，暂时算不出",
        });
        const tail = Math.round(Math.trunc(Number(guide.frame_index)) + span);
        rows.push({
            label: "输出结束位置", key: "tail",
            value: placed ? `第 ${tail} 帧（${formatSeconds(frameToSeconds(tail, doc.fps), 3)}s）` : "未放置",
        });
        if (range.frames) rows.push({ label: "视频总长", key: "room", value: `${range.frames} 帧` });
        return rows;
    }

    function renderDetail() {
        if (!root) return;
        releaseDetailPlayer();
        els.detail.replaceChildren();
        const guide = selectedGuide();
        if (!guide) {
            els.detail.append(make("span", "h3guide-note", "选中一张卡片或轨道上的标记后，这里可以编辑完整的时间与音频裁切。"));
            return;
        }

        const head = make("div", "h3guide-detail-head");
        head.append(
            make("strong", "h3guide-detail-id", guide.label || ""),
            make("span", "h3guide-note", `${guide.kind === AUDIO_KIND ? "音频" : "图片"} · ${String(guide.asset.filename).split("/").pop()}`),
        );
        const actions = make("div", "h3guide-detail-actions");
        const toggle = make("button", "h3guide-act", guide.enabled === false ? "启用" : "停用");
        toggle.title = "停用会保留这条记录、裁切和时间，但不会执行";
        toggle.onclick = (event) => {
            event.stopPropagation();
            const next = patchGuide(doc.guides, guide.id, { enabled: guide.enabled === false });
            if (!tryQuota(next, guide.kind)) return;
            mutate(next);
        };
        actions.appendChild(toggle);
        // 停用 is not the same as taking a card off the timeline. 移出时间轴 clears frame_index
        // only - the record, its crop and its enabled state stay, and the card returns to the
        // pool. The same slot becomes 放置 while the card is in the pool, so the action row
        // never gains or loses a button and the neighbouring buttons do not change width.
        const placed = guide.frame_index !== null && guide.frame_index !== undefined;
        const place = make("button", "h3guide-act", placed ? "移出时间轴" : "放置");
        place.title = placed
            ? "从时间轴上取下，回到卡片池待放置；这条记录、裁切和启用状态都保留"
            : "放到下一个空位（也可以直接把卡片或轨道上的标记拖到时间轴）";
        place.onclick = (event) => {
            event.stopPropagation();
            if (!placed) {
                placeGuideOnTimeline(guide);
                return;
            }
            mutate(patchGuide(doc.guides, guide.id, { frame_index: null }));
        };
        actions.appendChild(place);
        const drop = make("button", "h3guide-act warn", "删除");
        drop.title = "删除这条 Guide（与卡片池里的删除相同）";
        drop.onclick = (event) => {
            event.stopPropagation();
            mutate(removeGuide(doc.guides, guide.id));
        };
        actions.appendChild(drop);
        if (guide.kind === AUDIO_KIND) {
            // Previewing is the card's job when the card is on screen; the detail area only
            // owns its own player when the selection came from the other lane.
            const play = make("button", "h3guide-act", "▶ 试听当前裁切");
            play.title = "只播放会被输出的那一段：源裁切决定用录音的哪一段，插入时间决定放在视频哪里";
            const onCard = cardEls.get(guide.id)?.querySelector(".h3guide-play");
            if (onCard) play.onclick = (event) => { event.stopPropagation(); onCard.click(); };
            else wirePlayer(play, guide);
            actions.appendChild(play);
        }
        head.appendChild(actions);
        els.detail.appendChild(head);

        const fields = make("div", "h3guide-fields");
        for (const row of detailSpec(guide)) {
            const box = make("div", "h3guide-field");
            box.append(make("span", "h3guide-flabel", row.label));
            if (row.step !== undefined) {
                const input = make("input", "h3guide-num");
                input.type = "number";
                input.step = row.step;
                input.min = row.min !== undefined ? row.min : "0";
                input.max = row.max !== undefined ? row.max : "";
                input.dataset.key = row.key;
                if (row.title) input.title = row.title;
                input.value = row.value;
                input.addEventListener("change", () => onDetailInput(guide, row.key, input.value));
                box.appendChild(input);
                if (row.key === "strength") {
                    box.classList.add("h3guide-field-strength");
                    const controls = make("div", "h3guide-strength-controls");
                    const slider = make("input", "h3guide-strength-range");
                    slider.type = "range";
                    slider.min = String(STRENGTH_MIN);
                    slider.max = String(STRENGTH_MAX);
                    slider.step = String(STRENGTH_STEP);
                    slider.value = row.value;
                    slider.dataset.strengthRange = "";
                    slider.title = row.title;
                    slider.setAttribute("aria-label", "图片引导强度");
                    const presets = make("div", "h3guide-strength-presets");
                    const syncPresets = (raw) => {
                        const value = Number(raw);
                        for (const button of presets.children) {
                            const active = Math.abs(Number(button.dataset.strength) - value) < 0.001;
                            button.classList.toggle("active", active);
                            button.setAttribute("aria-pressed", String(active));
                        }
                    };
                    for (const preset of [
                        { value: 1, label: "原生 1.00", title: "沿用原生图片 Guide 行为" },
                        { value: 0.8, label: "0.80", title: "降低这张图片的画面约束" },
                        { value: 0.6, label: "0.60", title: "进一步放宽动作与场景衔接" },
                        { value: 0, label: "不加入 0.00", title: "保留卡片和时间位置，但不编码、不加入 conditioning" },
                    ]) {
                        const button = make("button", "h3guide-act h3guide-strength-preset", preset.label);
                        button.type = "button";
                        button.dataset.strength = String(preset.value);
                        button.title = preset.title;
                        button.onclick = (event) => {
                            event.stopPropagation();
                            applyStrengthInput(guide, preset.value);
                        };
                        presets.appendChild(button);
                    }
                    slider.addEventListener("input", () => {
                        input.value = Number(slider.value).toFixed(2);
                        syncPresets(slider.value);
                    });
                    slider.addEventListener("change", () => applyStrengthInput(guide, slider.value));
                    syncPresets(row.value);
                    controls.append(slider, presets);
                    box.appendChild(controls);
                }
            } else {
                const value = make("div", "h3guide-fvalue", row.value);
                value.dataset.key = row.key;
                box.appendChild(value);
            }
            fields.appendChild(box);
        }
        els.detail.appendChild(fields);
    }

    function onDetailInput(guide, key, value) {
        if (key === "seconds" || key === "frames") {
            applyTimeInput(guide, value, key === "seconds" ? "seconds" : "frames");
            return;
        }
        if (key === "strength") {
            applyStrengthInput(guide, value);
            return;
        }
        if (key === "in" || key === "out") {
            const read = (name) => els.detail.querySelector(`.h3guide-num[data-key="${name}"]`)?.value;
            applyTrimSeconds(guide, read("in"), read("out"));
        }
    }

    function syncDetail(guide) {
        if (!root || doc.view_state.selected_id !== guide.id) return;
        for (const row of detailSpec(guide)) {
            const field = els.detail.querySelector(`[data-key="${row.key}"]`);
            if (!field) continue;
            if (field.tagName === "INPUT") {
                if (document.activeElement !== field) field.value = row.value;
            } else {
                field.textContent = row.value;
            }
        }
        if (guide.kind === IMAGE_KIND && perImageStrength) {
            const strength = strengthOf(guide);
            const slider = els.detail.querySelector("[data-strength-range]");
            if (slider && document.activeElement !== slider) slider.value = strength.toFixed(2);
            for (const button of els.detail.querySelectorAll("[data-strength]")) {
                const active = Math.abs(Number(button.dataset.strength) - strength) < 0.001;
                button.classList.toggle("active", active);
                button.setAttribute("aria-pressed", String(active));
            }
        }
    }

    // ---------- G. validation footer ----------
    // Every message names the card it is about, so each one is a button that switches
    // tab, selects the card and scrolls to it.
    // Which audio files already have confirmed metadata. The footer needs this because an
    // empty problem list is only "passed" when the derived checks could actually run.
    function readyAudioKeys() {
        const keys = new Set();
        for (const [key, meta] of audioCache) {
            if (meta?.sampleRate && meta?.sampleCount) keys.add(key);
        }
        return keys;
    }

    function renderFooter() {
        if (!root) return;
        els.foot.replaceChildren();
        els.foot.classList.remove("ok", "pending");
        if (parseError) {
            // Unreadable list: the panel works on an empty document, but the original text is
            // still in the widget until the user chooses. Replacing it must be their decision.
            els.foot.append(make("span", null, `Guide 列表读不出来：${parseError}。当前显示的是空列表，原内容暂时保留；也可以主动改用空列表继续编辑。`));
            const reset = make("button", "h3guide-error", "改用空列表继续编辑");
            reset.title = "覆盖原来的内容，之后编辑才会保存";
            reset.onclick = () => resetDocumentToEmpty();
            els.foot.appendChild(reset);
            return;
        }
        if (liveNoteText) els.foot.append(make("span", "h3guide-sub", liveNoteText));
        const state = validationState(currentProblems(), pendingAudioCount(doc.guides, readyAudioKeys()));
        if (state.level === "pending") {
            els.foot.classList.add("pending");
            els.foot.append(make("span", null, state.text));
            return;
        }
        if (state.level === "ok") {
            els.foot.classList.add("ok");
            els.foot.append(make("span", null, state.text));
            return;
        }
        for (const text of state.problems) {
            const guide = doc.guides.find((item) => item.label && text.includes(item.label));
            const button = make("button", "h3guide-error", text);
            button.title = guide ? "点击定位到这张卡片" : "";
            button.onclick = () => {
                if (!guide) return;
                setTab(guide.kind);
                select(guide.id);
                cardEls.get(guide.id)?.scrollIntoView({ block: "center", behavior: "smooth" });
            };
            els.foot.appendChild(button);
        }
    }

    let liveNoteText = "";

    function showLiveNote(text) {
        liveNoteText = String(text || "");
        if (!root) return;
        const existing = els.foot.querySelector(".h3guide-sub");
        if (existing) {
            existing.textContent = liveNoteText;
            return;
        }
        els.foot.insertBefore(make("span", "h3guide-sub", liveNoteText), els.foot.firstChild);
    }

    // A committed edit does not rebuild the pool: the card that was typed into keeps its
    // focus, and only the derived views are redrawn.
    function commitEdit() {
        writeDoc({ dirty: true });
        for (const guide of doc.guides) syncCardTime(guide);
        if (root) {
            // A trim change moves the waveform window, so the audio cards repaint with it.
            for (const [id, card] of cardEls) {
                const other = guideById(id);
                if (other?.kind === AUDIO_KIND) paintCardAudio(card, other);
            }
            renderTimeline();
            renderDetail();
            renderFooter();
        }
        renderSummary();
    }

    function refreshSelection() {
        for (const [id, card] of cardEls) {
            const guide = guideById(id);
            if (guide) updateCardState(card, guide);
        }
        for (const surface of [editorSurface, nodeSurface]) {
            if (!surface) continue;
            if (surface === editorSurface && !root) continue;
            if (surface === nodeSurface && !stripOn) continue;
            for (const item of surface.laneItems) {
                item.el.classList.toggle("selected", item.guide.id === doc.view_state.selected_id);
            }
            surface.playhead?.remove();
            surface.playhead = null;
            const guide = selectedGuide();
            if (guide && isPlaced(guide)) {
                surface.playhead = make("div", "h3guide-playhead cap");
                surface.playheadFrame = Math.trunc(Number(guide.frame_index));
                surface.ruler.appendChild(surface.playhead);
                applyScroll(surface);
            }
        }
        if (root) renderDetail();
    }

    // ---------- the node summary ----------
    // Fixed height, always the same shape: the summary is text, and nothing here can
    // make the node grow. The node surface below fills whatever the panel still has.
    function renderSummary() {
        const range = timelineRange();
        const info = summaryOf(doc.guides, range.frames, doc.fps);
        nodeFooter.replaceChildren();
        if (perImageStrength) {
            const counts = guideStatusCounts(doc.guides, true);
            statusText.textContent = `生效 图片 ${counts.images} · 音频 ${counts.audios}`
                + ` · 待放置 ${counts.unplaced} · 停用 ${counts.disabled} · 强度0 ${counts.muted}`
                + ` · ${doc.fps} FPS · `
                + (range.frames ? `${range.frames} 帧 / ${formatSeconds(info.duration_seconds, 2)}s` : "总帧数未知");
            const active = counts.images + counts.audios;
            let vaeNote = "无需 VAE";
            if (counts.images && counts.audios) vaeNote = "需要视频 VAE + 音频 VAE";
            else if (counts.images) vaeNote = "需要视频 VAE · 无需音频 VAE";
            else if (counts.audios) vaeNote = "需要音频 VAE · 无需视频 VAE";
            let checkNote = "";
            let checkClass = "ok";
            let checkTitle = "";
            if (parseError) {
                checkNote = "Guide 列表读取失败 · 打开编辑器处理";
                checkClass = "error";
                checkTitle = parseError;
            } else if (active) {
                const state = validationState(currentProblems(), pendingAudioCount(doc.guides, readyAudioKeys()));
                checkTitle = state.problems.join("\n") || state.text;
                if (state.level === "error") {
                    checkNote = `编排 ${state.problems.length} 项待修正 · ${state.problems[0]}`;
                    checkClass = "error";
                } else if (state.level === "pending") {
                    checkNote = "音频信息待确认 · 时长与重叠检查未完成";
                    checkClass = "pending";
                } else {
                    checkNote = "编排校验通过";
                }
            }
            if (checkNote) {
                const hint = make("span", `h3lvm-hint h3guide-node-check ${checkClass}`, `${vaeNote} · ${checkNote}`);
                hint.title = checkTitle;
                nodeFooter.appendChild(hint);
            }
            scheduleStrip();
            return;
        }
        // "What runs" leaves out a 0.00 image card, so the node body cannot promise an encode
        // the node will not do. The editor quota line still counts the document, which is
        // what the node's own quota check counts.
        const counts = countRunnable(doc.guides);
        const parked = doc.guides.length - counts[IMAGE_KIND] - counts[AUDIO_KIND];
        statusText.textContent = `启用 图片 ${counts[IMAGE_KIND]} · 音频 ${counts[AUDIO_KIND]} · 不执行 ${parked}`
            + ` · ${doc.fps} FPS · `
            + (range.frames ? `${range.frames} 帧 / ${formatSeconds(info.duration_seconds, 2)}s` : "总帧数未知");
        if (doc.view_state.strip_open === true) {
            nodeFooter.append(make("span", "h3lvm-hint", "节点时间轴已开启：把节点拉高后才会显示；缩放与卡片池在 Guide 编辑器里。"));
        } else {
            nodeFooter.append(make("span", "h3lvm-hint", "连接 positive / latent / 视频 VAE / 音频 VAE；没有任何启用且已放置的 Guide 时，positive 原样透传。"));
        }
        scheduleStrip();
    }

    // ---------- the node surface ----------
    // Drawing it is a two-step decision: first whether the panel still has room for the two
    // lanes at their floor (an absolute check, never a CSS guess, and never a write to
    // node.size), then the render itself. Once it is on, a width change re-renders it,
    // because fit-to-width means every pixel is a scale change.

    function scheduleStrip() {
        if (stripFrame) return;
        stripFrame = requestAnimationFrame(() => {
            stripFrame = 0;
            fitStrip();
        });
    }

    // Two conditions, and the user's choice is the first one: the button has to be on and
    // the panel has to really have room for both lanes. That height check is absolute
    // (measured pixels, never a CSS guess) and it never writes node.size - a node that is
    // too short simply hides the helper view. Applying the heights is part of the same call:
    // the panel size is the only reason the requested lane heights would ever change.
    function fitStrip() {
        const wanted = doc.view_state.strip_open === true;
        const fits = applyStripHeights();
        stripBtn.classList.toggle("on", wanted);
        stripBtn.textContent = wanted ? "📈 隐藏节点时间轴" : "📈 显示节点时间轴";
        strip.classList.toggle("h3guide-strip-off", !wanted);
        stripBody.classList.toggle("h3guide-strip-body-off", !wanted || !fits);
        stripHint.textContent = wanted && !fits
            ? "空间不足：拉高节点或点「卡片 −」"
            : "整段视频按宽度铺满 · 缩放与卡片池在「打开 Guide 编辑器」";
        stripHint.classList.toggle("h3guide-lane-px-clamped", wanted && !fits);
        const next = wanted && fits;
        if (next === stripOn) {
            if (stripOn) renderSurface(nodeSurface);
            return;
        }
        stripOn = next;
        if (stripOn) renderSurface(nodeSurface);
    }

    function renderAll() {
        renderSummary();
        if (!root) return;
        renderTimeline();
        renderPool();
        renderDetail();
        renderFooter();
    }

    // ---------- wiring ----------
    openBtn.onclick = (event) => {
        event.stopPropagation();
        if (root) closeEditor();
        else openEditor();
    };
    stripBtn.onclick = (event) => {
        event.stopPropagation();
        doc.view_state.strip_open = doc.view_state.strip_open !== true;
        writeDoc({ dirty: false });
        fitStrip();
        renderSummary();
    };
    // The strip's own height steps. The base is the height that is actually drawn, so a
    // clamped lane answers to − at once; ＋ keeps the number the editor asked for when the
    // panel is the limit instead of quietly lowering it.
    const stripStepHeight = (kind, delta) => {
        const asked = laneHeights(doc.view_state)[kind];
        const base = delta > 0 ? Math.max(asked, stripHeights[kind]) : stripHeights[kind];
        if (!setLaneHeight(kind, stepLaneHeight(kind, base, delta))) return;
        writeDoc({ dirty: false });
        if (stripOn) renderSurface(nodeSurface);
    };
    stripImageSize.shrink.onclick = (event) => {
        event.stopPropagation();
        stripStepHeight(IMAGE_KIND, -1);
    };
    stripImageSize.grow.onclick = (event) => {
        event.stopPropagation();
        stripStepHeight(IMAGE_KIND, 1);
    };
    stripAudioSize.shrink.onclick = (event) => {
        event.stopPropagation();
        stripStepHeight(AUDIO_KIND, -1);
    };
    stripAudioSize.grow.onclick = (event) => {
        event.stopPropagation();
        stripStepHeight(AUDIO_KIND, 1);
    };
    const stripStepCard = (delta) => {
        const measured = markerPlanFor(nodeSurface, nodeSurface.laneItems?.length || 0).side;
        const current = hasStripMarkerSide(doc.view_state)
            ? stripMarkerSide(doc.view_state)
            : measured || stripMarkerSide(doc.view_state);
        doc.view_state.strip_marker_side = stepStripMarkerSide(current, delta);
        writeDoc({ dirty: false });
        fitStrip();
    };
    stripCardSize.shrink.onclick = (event) => {
        event.stopPropagation();
        stripStepCard(-1);
    };
    stripCardSize.grow.onclick = (event) => {
        event.stopPropagation();
        stripStepCard(1);
    };
    refreshBtn.onclick = (event) => {
        event.stopPropagation();
        audioCache.clear();
        imageCache.clear();
        doc = readDoc();
        renderSummary();
        if (root) renderAll();
    };

    // The duration box is what the ruler is drawn from before anything has been run, so typing
    // into it has to redraw the ruler and the placement checks straight away rather than on the
    // next 刷新. The node's own callback still runs first - this only adds a repaint.
    const lengthWidget = node.widgets?.find((item) => item.name === "length_seconds");
    if (lengthWidget) {
        const innerLengthCallback = lengthWidget.callback;
        lengthWidget.callback = function (value, ...rest) {
            const result = innerLengthCallback?.apply(this, [value, ...rest]);
            renderSummary();
            if (root) renderAll();
            return result;
        };
    }

    // The three hooks the extension entry point calls: reopening a workflow, a finished
    // run, and a removed node.
    node._h3guideReload = () => {
        doc = readDoc();
        renderSummary();
        if (root) renderAll();
    };
    node._h3guideResolved = (frames) => {
        const value = Math.max(0, Math.trunc(Number(frames) || 0));
        if (!value) return;
        doc.resolved_frame_count = value;
        doc.resolved_source = "run";
        writeDoc({ dirty: false });
        renderSummary();
        if (root) renderAll();
    };
    node._h3guideDispose = () => {
        closeEditor();
        endAllDragSessions();
        stripObserver?.disconnect();
        if (stripFrame) cancelAnimationFrame(stripFrame);
        stripFrame = 0;
        lifetime.abort();
    };

    // The node surface follows the node size; it never asks the node for one.
    let stripObserver = null;
    try {
        stripObserver = new ResizeObserver(() => scheduleStrip());
        stripObserver.observe(container);
        stripObserver.observe(stripHead);
    } catch (error) {
        console.warn("[H3 Guide Timeline] the node timeline cannot follow the node size:", error);
    }

    renderSummary();
}
