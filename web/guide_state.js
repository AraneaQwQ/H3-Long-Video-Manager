// RAFOLIE 2026-10-22: the Guide Timeline store, in plain functions.
//
// Why a separate module: the node decides what may run (core/guide_timeline.py) and
// the panel has to say the same thing before the user presses 执行. Both sides read
// one list of rules, so a rule cannot drift between the card deck and the node. If a
// rule changes in core/guide_timeline.py, change it here in the same commit; the two
// test files (tests/test_guide_timeline_core.py, work/guide_state.test.mjs) assert
// the same cases on purpose.
//
// No DOM here on purpose: this is the part that can be tested with plain node.
//
// frame_index is the authoritative position, exactly like the native Add Guide node's
// frame_idx. FPS is the native constant 24, so seconds are only an input and a label.
// Audio trimming is stored in sample points, never in seconds, so repeated edits do
// not accumulate float error.

export const SCHEMA_VERSION = 1;
export const DEFAULT_FPS = 24;

// First-version product limits, mirrored from core/guide_timeline.py. Parked
// (enabled=false) and unplaced (frame_index=null) cards count for neither.
export const MAX_GUIDE_IMAGES = 16;
export const MAX_GUIDE_AUDIOS = 16;
export const MAX_GUIDE_TOTAL = 32;

// comfy/ldm/minimax/model.py: pixel frames per video latent token.
export const FRAME_PER_TOKEN = [1, 4, 4, 4, 4];

export const IMAGE_KIND = "image";
export const AUDIO_KIND = "audio";
export const KINDS = [IMAGE_KIND, AUDIO_KIND];

export const ALLOWED_MEDIA_TYPES = ["input", "output", "temp"];

const ID_RE = /^[A-Za-z0-9_-]{1,64}$/;
const AUDIO_EXT = /\.(wav|mp3|m4a|aac|ogg|oga|flac|opus|webm)$/i;
const IMAGE_EXT = /\.(png|jpe?g|jfif|webp|bmp|gif|tif|tiff)$/i;

export function mediaKind(filename) {
    const name = String(filename || "");
    if (AUDIO_EXT.test(name)) return AUDIO_KIND;
    if (IMAGE_EXT.test(name)) return IMAGE_KIND;
    return "other";
}

export function labelFor(kind, index) {
    return `${kind === AUDIO_KIND ? "AUD" : "IMG"}-${String(index + 1).padStart(2, "0")}`;
}

// --- Time ---
export function frameCountFromLatentT(latentT, table = FRAME_PER_TOKEN) {
    const tokens = Number(latentT);
    if (!Number.isFinite(tokens) || tokens <= 0) return 0;
    const map = Array.isArray(table) && table.length ? table : FRAME_PER_TOKEN;
    let total = 0;
    for (let index = 0; index < tokens; index++) {
        total += map[index % map.length];
    }
    return total;
}

export function guideFramesFor(imageFrames) {
    let count = Math.trunc(Number(imageFrames) || 1);
    if (count < 5) return 1;
    while (count % 17 !== 5) count -= 1;
    return Math.max(count, 1);
}

export function frameToSeconds(frameIndex, fps = DEFAULT_FPS) {
    if (frameIndex === null || frameIndex === undefined) return 0;
    return Number(frameIndex) / (Number(fps) || DEFAULT_FPS);
}

export function secondsToFrame(seconds, fps = DEFAULT_FPS) {
    return Math.round((Number(seconds) || 0) * (Number(fps) || DEFAULT_FPS));
}

export function audioSpanFrames(sampleCount, sampleRate, fps = DEFAULT_FPS) {
    const count = Number(sampleCount) || 0;
    const rate = Number(sampleRate) || 0;
    if (!count || !rate) return 0;
    return Math.max(0, count) / rate * (Number(fps) || DEFAULT_FPS);
}

export function formatSeconds(seconds, digits = 3) {
    const value = Number(seconds) || 0;
    return value.toFixed(digits);
}

// --- One guide ---
export function newId() {
    const cryptoObj = globalThis.crypto;
    if (cryptoObj?.randomUUID) return cryptoObj.randomUUID().replace(/-/g, "").slice(0, 16);
    let out = "";
    for (let i = 0; i < 16; i++) out += Math.floor(Math.random() * 16).toString(16);
    return out;
}

function cleanId(value, seen) {
    const raw = String(value || "");
    if (ID_RE.test(raw) && !seen.has(raw)) {
        seen.add(raw);
        return raw;
    }
    for (;;) {
        const fresh = newId();
        if (!seen.has(fresh)) {
            seen.add(fresh);
            return fresh;
        }
    }
}

function cleanAsset(value, index) {
    let raw = value;
    if (typeof raw === "string") raw = { filename: raw };
    if (!raw || typeof raw !== "object") throw new Error(`guide ${index} has no media file`);
    const filename = String(raw.filename || "").trim().replace(/\\/g, "/");
    if (!filename) throw new Error(`guide ${index} has no media file`);
    if (filename.startsWith("/") || /^[A-Za-z]:[\\/]/.test(filename) || filename.split("/").includes("..")) {
        throw new Error(`guide ${index} must be a path inside the media folder, got: ${filename}`);
    }
    const base = filename.split("/").pop();
    if (base.startsWith(".")) throw new Error(`guide ${index} has a hidden file name: ${filename}`);
    const type = String(raw.type || "input");
    if (!ALLOWED_MEDIA_TYPES.includes(type)) {
        throw new Error(`guide ${index} has an unknown media folder: ${type}`);
    }
    return { filename, subfolder: String(raw.subfolder || ""), type };
}

function cleanSample(value, index, field) {
    if (value === null || value === undefined || value === "") return 0;
    if (typeof value === "boolean") throw new Error(`guide ${index} has a non-numeric ${field}`);
    const number = Number(value);
    if (!Number.isFinite(number) || number < 0) {
        throw new Error(`guide ${index} has an invalid ${field}: ${value}`);
    }
    return Math.round(number);
}

export function normalizeGuide(item, index, seenIds) {
    if (!item || typeof item !== "object") throw new Error(`guide ${index} is not an object`);
    const kind = String(item.kind || "").trim().toLowerCase();
    if (!KINDS.includes(kind)) throw new Error(`guide ${index} has an unknown kind: ${item.kind}`);

    let frame = item.frame_index === undefined ? item.frame_idx : item.frame_index;
    if (frame === null || frame === undefined || frame === "") {
        frame = null;
    } else {
        const number = Number(frame);
        if (!Number.isFinite(number)) throw new Error(`guide ${index} has a non-numeric frame_index: ${frame}`);
        frame = Math.trunc(number);
        if (frame < 0) throw new Error(`guide ${index} has a negative frame_index: ${frame}`);
    }

    const guide = {
        id: cleanId(item.id, seenIds),
        kind,
        label: String(item.label || "").trim() || null,
        enabled: item.enabled !== false,
        frame_index: frame,
        asset: cleanAsset(item.asset === undefined ? item.filename : item.asset, index),
    };
    if (kind === AUDIO_KIND) {
        guide.source_start_sample = cleanSample(item.source_start_sample, index, "source_start_sample");
        guide.source_end_sample = cleanSample(item.source_end_sample, index, "source_end_sample");
        const rate = Number(item.sample_rate) || 0;
        guide.sample_rate = Math.max(0, Math.trunc(rate));
    }
    return guide;
}

export const LABEL_RE = /^(IMG|AUD)-(\d{2,})$/;

// The display number is part of what the user reads on every card, on the lane and in
// every validation message, so it must not move when the list is reordered or a card is
// deleted. A label that is already there is kept; only a card without one (a fresh
// import, a copy) gets the smallest free number of its kind.
export function ensureLabels(guides) {
    const taken = new Set();
    for (const guide of guides || []) {
        const label = String(guide.label || "").trim().toUpperCase();
        if (LABEL_RE.test(label) && !taken.has(label)) {
            guide.label = label;
            taken.add(label);
        } else {
            guide.label = null;
        }
    }
    for (const guide of guides || []) {
        if (guide.label) continue;
        guide.label = nextFreeLabel(guide.kind, taken);
        taken.add(guide.label);
    }
    return guides;
}

function nextFreeLabel(kind, taken) {
    for (let index = 0; ; index += 1) {
        const label = labelFor(kind, index);
        if (!taken.has(label)) return label;
    }
}

// --- The document in the widget ---
export const DEFAULT_DOCUMENT = JSON.stringify({
    schema_version: SCHEMA_VERSION, fps: DEFAULT_FPS, guides: [],
});

export const DEFAULT_VIEW_STATE = { selected_id: null, active_tab: IMAGE_KIND, zoom: 1, scroll: 0, strip_open: false };

// The two lanes can be made taller inside the editor: a 9:16 frame needs a tall image lane,
// a waveform does not. This is view state - it survives a save and reload, and it never
// changes what a workflow does. The limits keep a lane usable: below the minimum the cards
// stop being readable, above the maximum the card pool is pushed out of the panel.
export const DEFAULT_LANE_HEIGHTS = { [IMAGE_KIND]: 112, [AUDIO_KIND]: 72 };
export const LANE_HEIGHT_LIMITS = {
    [IMAGE_KIND]: { min: 96, max: 420, step: 24 },
    [AUDIO_KIND]: { min: 56, max: 260, step: 16 },
};

export function clampLaneHeight(kind, value) {
    const limits = LANE_HEIGHT_LIMITS[kind] || LANE_HEIGHT_LIMITS[IMAGE_KIND];
    const fallback = DEFAULT_LANE_HEIGHTS[kind] ?? limits.min;
    // "not set" is not "zero": null, "" and anything that is not a number must not
    // quietly become the minimum height - a document that never set a lane keeps the default.
    const type = typeof value;
    if (type !== "number" && type !== "string") return fallback;
    if (String(value).trim() === "") return fallback;
    const wanted = Number(value);
    if (!Number.isFinite(wanted)) return fallback;
    return Math.min(limits.max, Math.max(limits.min, Math.trunc(wanted)));
}

export function laneHeights(view = {}) {
    const raw = view.lane_heights && typeof view.lane_heights === "object" ? view.lane_heights : {};
    return {
        [IMAGE_KIND]: clampLaneHeight(IMAGE_KIND, raw[IMAGE_KIND] ?? DEFAULT_LANE_HEIGHTS[IMAGE_KIND]),
        [AUDIO_KIND]: clampLaneHeight(AUDIO_KIND, raw[AUDIO_KIND] ?? DEFAULT_LANE_HEIGHTS[AUDIO_KIND]),
    };
}

export function stepLaneHeight(kind, current, delta) {
    const limits = LANE_HEIGHT_LIMITS[kind] || LANE_HEIGHT_LIMITS[IMAGE_KIND];
    const step = Math.max(1, Math.trunc(Number(limits.step) || 1));
    return clampLaneHeight(kind, (Number(current) || 0) + (Number(delta) || 0) * step);
}

// Only write lane_heights when the user actually moved something: a workflow that never
// touched the editor keeps the same compact document it had before.
export function laneHeightsDiffer(heights) {
    const safe = laneHeights({ lane_heights: heights });
    return safe[IMAGE_KIND] !== DEFAULT_LANE_HEIGHTS[IMAGE_KIND] || safe[AUDIO_KIND] !== DEFAULT_LANE_HEIGHTS[AUDIO_KIND];
}

export function parseDocument(raw) {
    let data = raw;
    if (data === null || data === undefined) data = {};
    if (typeof data === "string") {
        const text = data.trim();
        if (!text) data = {};
        else {
            try {
                data = JSON.parse(text);
            } catch (error) {
                throw new Error(`guides is not valid JSON: ${error.message}`);
            }
        }
    }
    if (Array.isArray(data)) data = { guides: data };
    if (typeof data !== "object") throw new Error("guides must be a JSON list of guide objects");

    const list = Array.isArray(data.guides) ? data.guides : [];
    const seen = new Set();
    const guides = ensureLabels(list.map((item, index) => normalizeGuide(item, index, seen)));
    // Quotas and ranges are NOT checked here. A document that is over quota or has a
    // guide out of range is still a document the user must be able to open and fix, so
    // parseDocument only rejects what cannot be read at all; validateGuides and
    // assertQuota are what stop it from executing.

    const view = { ...DEFAULT_VIEW_STATE, ...(data.view_state && typeof data.view_state === "object" ? data.view_state : {}) };
    if (!KINDS.includes(view.active_tab)) view.active_tab = IMAGE_KIND;
    view.zoom = Number(view.zoom) || 1;
    view.scroll = Number(view.scroll) || 0;
    view.strip_open = view.strip_open === true;
    view.lane_heights = laneHeights(view);

    return {
        schema_version: SCHEMA_VERSION,
        fps: Number(data.fps) || DEFAULT_FPS,
        guides,
        view_state: view,
        // Written by the node after a run; the ruler uses it before the next run.
        resolved_frame_count: Math.max(0, Math.trunc(Number(data.resolved_frame_count) || 0)),
        resolved_source: data.resolved_source === "upstream" ? "upstream" : "run",
    };
}

export function assertQuota(guides) {
    const counts = countRunnable(guides);
    const over = [];
    if (counts[IMAGE_KIND] > MAX_GUIDE_IMAGES) over.push(`启用的图片 Guide 有 ${counts[IMAGE_KIND]} 个，最多 ${MAX_GUIDE_IMAGES} 个`);
    if (counts[AUDIO_KIND] > MAX_GUIDE_AUDIOS) over.push(`启用的音频 Guide 有 ${counts[AUDIO_KIND]} 个，最多 ${MAX_GUIDE_AUDIOS} 个`);
    const total = counts[IMAGE_KIND] + counts[AUDIO_KIND];
    if (total > MAX_GUIDE_TOTAL) over.push(`启用的 Guide 合计 ${total} 个，最多 ${MAX_GUIDE_TOTAL} 个`);
    if (over.length) throw new Error(over.join("；"));
    return guides;
}

export function serializeDocument(doc) {
    const document = { schema_version: SCHEMA_VERSION, fps: Number(doc.fps) || DEFAULT_FPS, guides: [] };
    for (const guide of doc.guides || []) {
        const entry = {
            id: guide.id,
            kind: guide.kind,
            label: guide.label || labelFor(guide.kind, 0),
            enabled: guide.enabled !== false,
            frame_index: guide.frame_index === undefined ? null : guide.frame_index,
            asset: {
                filename: guide.asset.filename,
                subfolder: guide.asset.subfolder || "",
                type: guide.asset.type || "input",
            },
        };
        if (guide.kind === AUDIO_KIND) {
            entry.source_start_sample = Math.trunc(Number(guide.source_start_sample) || 0);
            entry.source_end_sample = Math.trunc(Number(guide.source_end_sample) || 0);
            entry.sample_rate = Math.trunc(Number(guide.sample_rate) || 0);
        }
        document.guides.push(entry);
    }
    const frameCount = Math.max(0, Math.trunc(Number(doc.resolved_frame_count) || 0));
    if (frameCount) document.resolved_frame_count = frameCount;
    const view = doc.view_state || {};
    const heights = laneHeights(view);
    const heightsChanged = laneHeightsDiffer(heights);
    if (view.selected_id || view.active_tab || (Number(view.zoom) || 1) !== 1 || (Number(view.scroll) || 0) !== 0 || view.strip_open === true || heightsChanged) {
        document.view_state = {
            selected_id: view.selected_id ?? null,
            active_tab: KINDS.includes(view.active_tab) ? view.active_tab : IMAGE_KIND,
            zoom: Number(view.zoom) || 1,
            scroll: Number(view.scroll) || 0,
            strip_open: view.strip_open === true,
        };
        if (heightsChanged) document.view_state.lane_heights = heights;
    }
    return JSON.stringify(document);
}

// --- What would run ---
export function isRunnable(guide) {
    return Boolean(guide) && guide.enabled !== false && guide.frame_index !== null && guide.frame_index !== undefined;
}

export function runnableGuides(guides) {
    return (guides || []).filter(isRunnable);
}

export function parkedGuides(guides) {
    return (guides || []).filter((guide) => !isRunnable(guide));
}

export function countRunnable(guides) {
    const counts = { [IMAGE_KIND]: 0, [AUDIO_KIND]: 0 };
    for (const guide of runnableGuides(guides)) counts[guide.kind] += 1;
    return counts;
}

export function sortForExecution(guides) {
    const order = { [IMAGE_KIND]: 0, [AUDIO_KIND]: 1 };
    return runnableGuides(guides)
        .map((guide, index) => ({ guide, index }))
        .sort((a, b) => (a.guide.frame_index - b.guide.frame_index)
            || (order[a.guide.kind] - order[b.guide.kind])
            || (a.index - b.index))
        .map((entry) => entry.guide);
}

export function summaryOf(guides, frameCount = 0, fps = DEFAULT_FPS) {
    const counts = countRunnable(guides);
    const frames = Math.max(0, Math.trunc(Number(frameCount) || 0));
    const rate = Number(fps) || DEFAULT_FPS;
    return {
        images: counts[IMAGE_KIND],
        audios: counts[AUDIO_KIND],
        parked: parkedGuides(guides).length,
        fps: rate,
        frame_count: frames,
        duration_seconds: frames / rate,
    };
}
// --- Validation ---
// Same table of rules as validate_guides() in core/guide_timeline.py. The node is
// still the authority; this only lets the panel say it before a run.
export function audioSpans(guides, metaById = {}) {
    const spans = {};
    for (const guide of guides || []) {
        if (guide.kind !== AUDIO_KIND) continue;
        const meta = metaById[guide.id] || {};
        const window = trimWindow(guide, meta);
        spans[guide.id] = audioSpanFrames(window.sampleCount, window.sampleRate, DEFAULT_FPS);
    }
    return spans;
}

export function findAudioOverlaps(guides, spans = {}) {
    const windows = [];
    for (const guide of runnableGuides(guides)) {
        if (guide.kind !== AUDIO_KIND) continue;
        const start = Number(guide.frame_index);
        const end = start + Number(spans[guide.id] || 0);
        if (end <= start) continue;
        windows.push({ start, end, guide });
    }
    const overlaps = [];
    for (let a = 0; a < windows.length; a++) {
        for (let b = a + 1; b < windows.length; b++) {
            const first = windows[a];
            const second = windows[b];
            if (first.start < second.end && second.start < first.end) {
                overlaps.push([first.guide, second.guide,
                    [Math.max(first.start, second.start), Math.min(first.end, second.end)]]);
            }
        }
    }
    return overlaps;
}

export function validateGuides(guides, frameCount, { spans = {}, imageFrames = {}, fps = DEFAULT_FPS } = {}) {
    const frames = Math.trunc(Number(frameCount) || 0);
    if (frames <= 0) return ["上游没有给出可用的 H3 AV latent，无法确定视频总帧数。"];

    const runnable = runnableGuides(guides);
    const counts = countRunnable(guides);
    const rate = Number(fps) || DEFAULT_FPS;
    const errors = [];

    for (const guide of runnable) {
        const frame = Math.trunc(Number(guide.frame_index));
        if (frame < 0 || frame >= frames) {
            errors.push(`${guide.label} 在第 ${frame} 帧（${formatSeconds(frameToSeconds(frame, rate))} 秒），超出视频范围 0–${frames - 1} 帧。`);
            continue;
        }
        if (guide.kind === IMAGE_KIND) {
            const held = guideFramesFor(imageFrames[guide.id] || 1);
            if (frame + held > frames) {
                errors.push(`${guide.label} 是一段 ${held} 帧的片段，放在第 ${frame} 帧放不下（视频只有 ${frames} 帧）。`);
            }
            continue;
        }
        const startSample = Math.trunc(Number(guide.source_start_sample) || 0);
        const endSample = Math.trunc(Number(guide.source_end_sample) || 0);
        if (endSample && endSample <= startSample) {
            errors.push(`${guide.label} 的裁切区间是空的：起点 ${startSample} 采样点已经在终点 ${endSample} 之后。`);
        }
        const span = Number(spans[guide.id] || 0);
        if (frame + span > frames + 1e-6) {
            errors.push(`${guide.label} 从第 ${frame} 帧开始，音频长 ${formatSeconds(frameToSeconds(frame + span, rate))} 秒，超出视频结尾。`);
        }
    }

    const seenFrames = {};
    for (const guide of runnable) {
        if (guide.kind !== IMAGE_KIND) continue;
        const frame = Math.trunc(Number(guide.frame_index));
        if (seenFrames[frame]) {
            errors.push(`${seenFrames[frame].label} 和 ${guide.label} 都在第 ${frame} 帧：同一帧只能锚一张图片，请错开时间。`);
        } else {
            seenFrames[frame] = guide;
        }
    }

    for (const [first, second, window] of findAudioOverlaps(runnable, spans)) {
        errors.push(`${first.label} 和 ${second.label} 在 ${Math.floor(window[0])}–${Math.ceil(window[1])} 帧重叠：音频 Guide 不能互相覆盖。`);
    }

    if (counts[IMAGE_KIND] > MAX_GUIDE_IMAGES) errors.push(`启用的图片 Guide 有 ${counts[IMAGE_KIND]} 个，最多 ${MAX_GUIDE_IMAGES} 个。`);
    if (counts[AUDIO_KIND] > MAX_GUIDE_AUDIOS) errors.push(`启用的音频 Guide 有 ${counts[AUDIO_KIND]} 个，最多 ${MAX_GUIDE_AUDIOS} 个。`);
    if (runnable.length > MAX_GUIDE_TOTAL) errors.push(`启用的 Guide 合计 ${runnable.length} 个，最多 ${MAX_GUIDE_TOTAL} 个。`);
    return errors;
}

// --- Audio trim: sample points are the stored form ---
export function trimWindow(guide, meta = {}) {
    const sampleRate = Math.trunc(Number(meta.sample_rate || guide?.sample_rate) || 0);
    const total = Math.trunc(Number(meta.sample_count) || 0);
    const start = Math.max(0, Math.trunc(Number(guide?.source_start_sample) || 0));
    const requested = Math.trunc(Number(guide?.source_end_sample) || 0);
    const end = requested > 0 ? requested : total;
    const clampedEnd = total ? Math.min(end, total) : end;
    const count = Math.max(0, clampedEnd - start);
    return {
        sampleRate,
        sampleCount: count,
        startSample: start,
        endSample: clampedEnd,
        totalSamples: total,
        startSeconds: sampleRate ? start / sampleRate : 0,
        endSeconds: sampleRate ? clampedEnd / sampleRate : 0,
        durationSeconds: sampleRate ? count / sampleRate : 0,
    };
}

export function trimFromSeconds(meta, startSeconds, endSeconds) {
    const rate = Math.trunc(Number(meta?.sample_rate) || 0);
    if (!rate) return { source_start_sample: 0, source_end_sample: 0 };
    const total = Math.trunc(Number(meta?.sample_count) || 0);
    const start = Math.max(0, Math.round((Number(startSeconds) || 0) * rate));
    let end = Math.round((Number(endSeconds) || 0) * rate);
    if (end <= 0) end = 0;
    if (total && end > total) end = total;
    if (end && end <= start) return { source_start_sample: start, source_end_sample: start + 1 };
    return { source_start_sample: start, source_end_sample: end };
}

// --- Editing (pure: a new list, never a mutated one) ---
export function addGuides(list, incoming, { maxTotal = MAX_GUIDE_TOTAL } = {}) {
    const guides = (list || []).map((guide) => ({ ...guide }));
    const seen = new Set(guides.map((guide) => guide.id));
    const taken = new Set(guides.map((guide) => mediaKeyOf(guide)));
    let added = 0;
    let rejected = 0;
    for (const item of incoming || []) {
        const asset = typeof item === "string" ? { filename: item } : { ...(item || {}) };
        const kind = mediaKind(asset.filename);
        if (!KINDS.includes(kind)) { rejected++; continue; }
        const key = mediaKeyOf({ asset });
        if (taken.has(key)) { rejected++; continue; }
        if (guides.length + 1 > maxTotal) { rejected++; continue; }
        taken.add(key);
        const guide = normalizeGuide({ kind, asset, frame_index: null, enabled: true }, guides.length, seen);
        if (kind === AUDIO_KIND) guide.sample_rate = Math.trunc(Number(asset.sample_rate) || 0);
        guides.push(guide);
        added++;
    }
    return { guides: ensureLabels(guides), added, rejected };
}

export function removeGuide(list, id) {
    return (list || []).filter((guide) => guide.id !== id).map((guide) => ({ ...guide }));
}

export function patchGuide(list, id, patch) {
    return (list || []).map((guide) => {
        if (guide.id !== id) return { ...guide };
        const next = { ...guide, ...(patch || {}) };
        const seen = new Set((list || []).filter((other) => other.id !== next.id).map((other) => other.id));
        return normalizeGuide(next, 0, seen);
    });
}

export function duplicateGuide(list, id) {
    const guides = (list || []).map((guide) => ({ ...guide }));
    const at = guides.findIndex((guide) => guide.id === id);
    if (at < 0) return guides;
    const source = guides[at];
    const copy = { ...source, id: newId(), frame_index: null, label: null };
    if (copy.asset) copy.asset = { ...source.asset };
    // A copy that is already on the timeline would immediately collide with its
    // source, so it starts in 待放置 like any freshly imported card.
    guides.splice(at + 1, 0, copy);
    return ensureLabels(guides);
}

export function moveGuide(list, fromId, toIndex) {
    const guides = (list || []).map((guide) => ({ ...guide }));
    const from = guides.findIndex((guide) => guide.id === fromId);
    if (from < 0) return guides;
    const [moved] = guides.splice(from, 1);
    const target = Math.max(0, Math.min(guides.length, Math.trunc(toIndex)));
    guides.splice(target, 0, moved);
    return ensureLabels(guides);
}

export function mediaKeyOf(guide) {
    const asset = guide?.asset || {};
    return `${asset.type || "input"}|${asset.subfolder || ""}|${asset.filename}`;
}

// Where a newly placed card goes when the user asks for it instead of dragging:
// just past the last card already on the timeline, on a whole-second step. Appending
// is predictable; landing in a gap the user left on purpose is not. Five cards in a
// row therefore never stack, and null means the video is too short for another one.
export function nextFreeFrame(guides, frameCount = 0, spans = {}, fps = DEFAULT_FPS) {
    const limit = Math.trunc(Number(frameCount) || 0);
    const step = Math.max(1, Math.trunc(Number(fps) || DEFAULT_FPS));
    let after = 0;
    for (const other of runnableGuides(guides)) {
        const start = Number(other.frame_index);
        if (!Number.isFinite(start)) continue;
        const width = other.kind === AUDIO_KIND ? Number(spans[other.id] || 0) : 1;
        after = Math.max(after, start + Math.max(1, width));
    }
    const frame = Math.ceil(after / step) * step;
    if (limit && frame >= limit) return null;
    return frame;
}
// --- Timeline geometry ---
// One transform for the ruler, both tracks, the markers and the audio clips. The
// prototype used different percentages per lane, which is exactly what the plan
// says must not ship. Zoom 1 means "the whole video fits"; anything above it makes
// the content wider than the panel and the lanes scroll together.
export const ZOOM_STEPS = [1, 1.5, 2, 3, 4, 6, 8];
export const TRACK_PADDING = 28; // px of dead space so frame 0 and the last frame are not clipped

export function zoomStepAt(zoom, delta) {
    // An off-ladder value (an older document, a hand-edited number) still moves to
    // the next real rung up or down instead of jumping to the nearest rung or back to 1x.
    const wanted = Number(zoom) || 1;
    const step = Number(delta) || 0;
    if (step > 0) {
        const up = ZOOM_STEPS.find((value) => value > wanted + 1e-6);
        return up === undefined ? ZOOM_STEPS[ZOOM_STEPS.length - 1] : up;
    }
    if (step < 0) {
        const down = ZOOM_STEPS.filter((value) => value < wanted - 1e-6);
        return down.length ? down[down.length - 1] : ZOOM_STEPS[0];
    }
    let same = ZOOM_STEPS[0];
    for (const value of ZOOM_STEPS) {
        if (Math.abs(value - wanted) < Math.abs(same - wanted)) same = value;
    }
    return same;
}

export function clampScroll(value, scrollMax) {
    const max = Math.max(0, Number(scrollMax) || 0);
    const wanted = Number(value) || 0;
    return Math.max(0, Math.min(max, wanted));
}

export function createScale({ frameCount, width, zoom = 1, padding = TRACK_PADDING }) {
    const frames = Math.max(1, Math.trunc(Number(frameCount) || 1));
    const viewWidth = Math.max(0, Number(width) || 0);
    const pad = Math.max(0, Number(padding) || 0);
    const inner = Math.max(10, viewWidth - pad * 2);
    const base = inner / Math.max(1, frames - 1);
    const factor = Math.max(1, Number(zoom) || 1);
    const pxPerFrame = base * factor;
    const contentWidth = pad * 2 + (frames - 1) * pxPerFrame;
    const scale = {
        frames,
        viewWidth,
        padding: pad,
        zoom: factor,
        pxPerFrame,
        contentWidth,
        scrollMax: Math.max(0, contentWidth - viewWidth),
        frameToPx(frame) {
            return pad + (Number(frame) || 0) * pxPerFrame;
        },
        pxToFrame(px, { clamp = true } = {}) {
            const frame = Math.round(((Number(px) || 0) - pad) / pxPerFrame);
            return clamp ? Math.max(0, Math.min(frames - 1, frame)) : frame;
        },
        clampFrame(frame) {
            const value = Math.trunc(Number(frame) || 0);
            return Math.max(0, Math.min(frames - 1, value));
        },
        // Out of range is a state the user can be left in on purpose (a number
        // typed in a field), so the panel can still draw it: just outside the end.
        markerPx(frame) {
            return pad + (Number(frame) || 0) * pxPerFrame;
        },
    };
    return scale;
}

// One place turns "the pointer is here" into "the frame is here". Dragging a card that is
// already on a lane and dropping a card from the pool onto a lane need the same rule, and the
// two must not drift apart: the clamp is identical, including the rule that a clip with a width
// cannot start so late that it runs past the end of the video.
export function frameFromLanePointer({ scale, scroll = 0, clientX, trackLeft = 0, offset = 0, widthFrames = 1, frameCount = 0 }) {
    if (!scale) return null;
    const frames = Math.max(0, Math.trunc(Number(frameCount) || 0));
    if (!frames) return null;
    const width = Math.max(1, Math.ceil(Number(widthFrames) || 1));
    const maxFrame = Math.max(0, frames - width);
    const grabbed = scale.pxToFrame((Number(clientX) || 0) - (Number(trackLeft) || 0) + (Number(scroll) || 0), { clamp: false });
    return Math.max(0, Math.min(maxFrame, Math.round(grabbed - (Number(offset) || 0))));
}

// How far the pointer has to move before a press becomes a drag. Below this the press is a
// click (select the card, focus a field), and a card that starts moving on a 1 px jitter is
// what makes a user think the panel is fighting them.
export const DRAG_START_PX = 6;

export function passedDragThreshold({ dx = 0, dy = 0, threshold = DRAG_START_PX } = {}) {
    const limit = Math.max(0, Number(threshold) || 0);
    if (!limit) return true;
    const x = Number(dx) || 0;
    const y = Number(dy) || 0;
    return x * x + y * y >= limit * limit;
}

// "Which region is the pointer over?" is a separate question from "which frame", and the answer
// has rules the old code only got right by accident:
//   - a lane row accepts a card of its own kind, and the row includes its label column;
//   - a lane row of the other kind is refused out loud, so a card never lands on a lane the
//     user was not aiming at;
//   - the card pool accepts a card for reordering;
//   - anything else (a lane header, a resize grip, the gap between sections) changes nothing.
// Rects are plain numbers so this is testable without a DOM.
export function resolveDropTarget({ clientX, clientY, kind, lanes = [], deck = null } = {}) {
    const x = Number(clientX) || 0;
    const y = Number(clientY) || 0;
    const inside = (rect) => Boolean(rect)
        && Number.isFinite(Number(rect.left)) && Number.isFinite(Number(rect.top))
        && x >= Number(rect.left) && x <= Number(rect.right)
        && y >= Number(rect.top) && y <= Number(rect.bottom);
    for (const lane of (Array.isArray(lanes) ? lanes : [])) {
        if (!inside(lane)) continue;
        if (lane.kind !== kind) return { type: "wrong-lane", lane, laneKind: lane.kind };
        return { type: "lane", lane };
    }
    if (inside(deck)) return { type: "pool" };
    return { type: "none" };
}

const TICK_STEPS = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];

export function tickMarks(scale, fps = DEFAULT_FPS, { minGapPx = 90 } = {}) {
    const rate = Number(fps) || DEFAULT_FPS;
    let stepSeconds = TICK_STEPS[TICK_STEPS.length - 1];
    for (const candidate of TICK_STEPS) {
        if (candidate * rate * scale.pxPerFrame >= (Number(minGapPx) || 0)) {
            stepSeconds = candidate;
            break;
        }
    }
    const stepFrames = Math.max(1, Math.round(stepSeconds * rate));
    const ticks = [];
    for (let frame = 0; frame <= scale.frames - 1; frame += stepFrames) {
        const seconds = frame / rate;
        ticks.push({ frame, seconds, px: scale.frameToPx(frame), label: tickLabel(seconds, stepSeconds) });
    }
    return { stepSeconds, ticks };
}

export function tickLabel(seconds, stepSeconds) {
    const value = Number(seconds) || 0;
    if (value === 0) return "0s";
    const whole = Math.abs(value % 1) < 1e-9;
    if (whole && stepSeconds >= 1) {
        if (value >= 60) return `${Math.floor(value / 60)}:${String(Math.round(value % 60)).padStart(2, "0")}`;
        return `${Math.round(value)}s`;
    }
    return value.toFixed(stepSeconds < 0.25 ? 2 : 1);
}

// The ruler and both lanes share one scroll offset; holding a card near an edge pans the
// lanes instead of running the card off the panel. The pointer decides when that happens,
// not the card's own frame: the frame is computed from the pointer plus the scroll, so using
// the frame to choose the scroll makes the two chase each other and the card runs away from
// the cursor. Panning by the pointer overshoot keeps the card under the cursor while the
// view moves, which is what a held card should do.
export function scrollForPointerPan(scale, scroll, pointerX, viewWidth = 0, edgePx = 40) {
    if (!scale || scale.scrollMax <= 0) return null;
    const shown = Math.max(0, Number(viewWidth) || 0) || scale.viewWidth;
    const edge = Math.max(0, Number(edgePx) || 0);
    if (pointerX > shown - edge) return panBy(scale, scroll, pointerX - (shown - edge));
    if (pointerX < edge) return panBy(scale, scroll, pointerX - edge);
    return null;
}

// ---------- panning a zoomed timeline ----------
// Above fit-to-width part of the video is off screen, and the only way to reach it is to
// move the view. Three gestures do that (the slider under the lanes, the wheel over a
// lane, dragging empty lane space) and all of them go through these helpers, so they
// cannot disagree about where the view ends up.
export function panBy(scale, scroll, deltaPx) {
    if (!scale) return 0;
    // deltaPx > 0 shows later frames; dragging the content to the right is the negative case.
    return clampScroll((Number(scroll) || 0) + (Number(deltaPx) || 0), scale.scrollMax);
}

// Keep one frame in the middle of the view across a zoom change, so pressing + does not
// throw the user back to the start of the video.
export function scrollToFrame(scale, frame, viewWidth = 0) {
    if (!scale) return 0;
    const shown = Math.max(0, Number(viewWidth) || 0) || scale.viewWidth;
    return clampScroll(scale.markerPx(frame) - shown / 2, scale.scrollMax);
}

// Where the visible window sits inside the content, as fractions of the content - all a
// slider needs, whatever its pixel width turns out to be.
export function panWindow(scale, scroll, viewWidth = 0) {
    if (!scale) return { scrollable: false, leftFraction: 0, widthFraction: 1 };
    const shown = Math.max(0, Number(viewWidth) || 0) || scale.viewWidth;
    const content = Math.max(1, scale.contentWidth);
    return {
        scrollable: scale.scrollMax > 0,
        leftFraction: clampScroll(scroll, scale.scrollMax) / content,
        widthFraction: Math.min(1, shown / content),
    };
}

// The inverse, for dragging that slider: the thumb stands for the visible window, so its
// centre is the centre of the view.
export function scrollForPanThumb(scale, thumbCenterFraction, viewWidth = 0) {
    if (!scale) return 0;
    const shown = Math.max(0, Number(viewWidth) || 0) || scale.viewWidth;
    const fraction = Math.max(0, Math.min(1, Number(thumbCenterFraction) || 0));
    return clampScroll(fraction * Math.max(1, scale.contentWidth) - shown / 2, scale.scrollMax);
}

// ---------- the timeline inside the node ----------
// The node panel owns whatever height the user drags it to, so the same timeline can
// be drawn there as well as in the editor. Two numbers keep that honest: the height
// below which drawing it would only clip its own labels, and the marker width that
// still fits when placed guides crowd a narrow lane.

// What the strip draws above and between its lanes, added up from the sheet: container
// padding 12 + strip margin 8 + strip padding 12 + head row 28 + ruler row 24 + two lane
// borders 4 + two row margins 12. It is a constant on purpose: the room check is
// arithmetic, never a CSS guess, and it never writes node.size.
export const STRIP_CHROME_H = 100;
// Under this an image marker is smaller than STRIP_MARKER_MIN and a waveform is a line, so
// the strip hides itself instead of drawing something unreadable.
export const STRIP_LANE_MIN = { [IMAGE_KIND]: 52, [AUDIO_KIND]: 44 };
export const STRIP_MARKER_MIN = 40;

export function stripRoom({ containerHeight, toolbarHeight, footerHeight } = {}) {
    return Math.trunc(Number(containerHeight) || 0)
        - Math.trunc(Number(toolbarHeight) || 0)
        - Math.trunc(Number(footerHeight) || 0);
}

// The lane heights are the editor's numbers, but the node panel owns its own height, so in
// the strip they are a request: both lanes shrink together until they fit, and never below
// their own floor. fits=false is the case that hides the helper view. The card side follows
// the height that was actually applied, so the same - / + control works in both places and
// the two never disagree about what a card looks like.
export function stripLaneHeights({ room, image, audio } = {}) {
    const wanted = {
        [IMAGE_KIND]: clampLaneHeight(IMAGE_KIND, image),
        [AUDIO_KIND]: clampLaneHeight(AUDIO_KIND, audio),
    };
    const available = Math.trunc(Number(room) || 0) - (Number(STRIP_CHROME_H) || 0);
    const floorSum = STRIP_LANE_MIN[IMAGE_KIND] + STRIP_LANE_MIN[AUDIO_KIND];
    if (available < floorSum) return { fits: false, heights: wanted };
    const total = wanted[IMAGE_KIND] + wanted[AUDIO_KIND];
    if (total <= available) return { fits: true, heights: wanted };
    const heights = {};
    for (const kind of [IMAGE_KIND, AUDIO_KIND]) {
        heights[kind] = Math.max(STRIP_LANE_MIN[kind], Math.floor((available * wanted[kind]) / total));
    }
    // Two floored shares can still overshoot when one of them hit its floor; take the
    // overshoot back out of the lane with the most room to spare.
    let over = heights[IMAGE_KIND] + heights[AUDIO_KIND] - available;
    const order = [IMAGE_KIND, AUDIO_KIND]
        .sort((a, b) => (heights[b] - STRIP_LANE_MIN[b]) - (heights[a] - STRIP_LANE_MIN[a]));
    for (const kind of order) {
        if (over <= 0) break;
        const take = Math.min(Math.max(0, heights[kind] - STRIP_LANE_MIN[kind]), over);
        heights[kind] -= take;
        over -= take;
    }
    return { fits: true, heights };
}

// Half a marker has to stay inside the scale padding or the first and last marker get
// cut off, so the padding is derived from the marker size rather than fixed at 28px.
// Same contract as the editor, just measured. The ceiling is the lane's own, not a fixed
// design size: in a fit-to-width lane N cards may only take width/N each, and that is the
// real limit - asking for a taller lane is how the user asks for a bigger card.
export function stripMarkerPlan({ laneWidth, count, max = MARKER_SIDE_HARD_MAX, min = STRIP_MARKER_MIN } = {}) {
    const width = Math.max(0, Number(laneWidth) || 0);
    const total = Math.max(0, Math.trunc(Number(count) || 0));
    const markerWidth = total > 0 && width > 0
        ? Math.max(min, Math.min(max, Math.floor(width / total)))
        : max;
    return { markerWidth, padding: Math.ceil(markerWidth / 2) + 4 };
}

// A marker is a square, never a thin sliver: its side is the lane's inner height minus
// the CSS inset, capped only by the width budget a fit-to-width lane needs so N guides
// still fit across it (0 = no cap, which is the editor case - it scrolls and zooms).
// The lane CSS owns the floor via min-height, so the smallest legal square is that lane
// minus the inset; that floor is what "at least 1:1" means in practice.
export const MARKER_INSET = 6;
// The design size for an image marker at the default lane height: 112px lane - 2x6px inset
// is 100, and the plan asks for 72-88. It is the default for a caller that has no lane
// height to ask about, not a ceiling - sizing a card is the lane height's job in the editor
// and in the node strip alike.
export const MARKER_SIDE_MAX = 88;
// The card side may follow the lane the user chose, in either place. This is only a sanity
// ceiling for an absurdly tall lane, and in the node strip the fit-to-width budget
// (stripMarkerPlan) is the limit that actually binds once several guides are placed.
export const MARKER_SIDE_HARD_MAX = 320;

export function squareMarkerPlan({ laneHeight, widthBudget = 0, inset = MARKER_INSET, max = MARKER_SIDE_MAX } = {}) {
    const inner = Math.max(0, Math.trunc(Number(laneHeight) || 0) - Math.max(0, Math.trunc(Number(inset) || 0)) * 2);
    const cap = Number(widthBudget) > 0 ? Math.trunc(Number(widthBudget)) : Infinity;
    const ceiling = Number(max) > 0 ? Math.trunc(Number(max)) : Infinity;
    const side = Math.min(inner, cap, ceiling);
    return { side, padding: Math.ceil(side / 2) + 4 };
}

// ---------- dense markers ----------
// Two guides 3 frames apart are a real thing; at 100% they are 3px apart, and two 88px
// squares would sit on top of each other. The old answer was a hover z-index, which is
// not an answer: the card under it cannot be clicked.
//
// This is a display-only spread. Every entry keeps its true anchor (anchorPx) so the
// panel can draw the exact frame position as a tick, and the frame_index in the document
// never moves. The result is a left-to-right packing that stays inside the lane; when the
// lane genuinely cannot hold every square, the last ones share space and groupSize says
// how many real anchors are crowded together, which is what the panel labels.
export function declutterMarkers({ anchors = [], size = 0, laneWidth = 0, minGap = 6 } = {}) {
    const side = Math.max(0, Number(size) || 0);
    const width = Math.max(0, Number(laneWidth) || 0);
    const gap = Math.max(0, Number(minGap) || 0);
    const items = (Array.isArray(anchors) ? anchors : [])
        .map((entry) => ({ id: entry?.id, anchorPx: Number(entry?.px) || 0 }))
        .sort((a, b) => a.anchorPx - b.anchorPx);
    const flat = (list) => list.map((item) => ({ ...item, px: item.anchorPx, offset: 0, groupSize: 1, crowded: false }));
    if (!items.length) return [];
    if (!side || !width) return flat(items);

    const half = side / 2;
    const step = side + gap;
    // A card may drift from its own frame by about one card width: far enough to make
    // room for a neighbour, close enough that the eye can follow it back to the tick.
    // Past that the tick carries the time, so the card stops being pushed and only
    // keeps a clickable strip (minGap) out from under the card in front of it.
    const px = [];
    const crowded = [];
    let right = -Infinity;
    let last = -Infinity;
    items.forEach((item, index) => {
        let center = Math.max(item.anchorPx, right + gap + half);
        let isCrowded = false;
        if (center > item.anchorPx + side) {
            center = Math.max(item.anchorPx, last + gap);
            isCrowded = true;
        }
        px.push(center);
        crowded.push(isCrowded);
        right = center + half;
        last = center;
    });

    // Slide the whole chain into the lane when it fits; when it cannot, clamp each card
    // on its own and accept the overlap - the tick and the group badge stay honest.
    const span = px[px.length - 1] + half - (px[0] - half);
    if (span <= width) {
        const overflow = px[px.length - 1] + half - width;
        if (overflow > 0) for (let i = 0; i < px.length; i += 1) px[i] -= overflow;
        const underflow = half - px[0];
        if (underflow > 0) for (let i = 0; i < px.length; i += 1) px[i] += underflow;
    } else {
        for (let i = 0; i < px.length; i += 1) px[i] = Math.min(Math.max(px[i], half), width - half);
        for (let i = 1; i < px.length; i += 1) crowded[i] = true;
    }

    const out = items.map((item, index) => ({
        ...item,
        px: px[index],
        offset: px[index] - item.anchorPx,
        groupSize: 1,
        crowded: crowded[index] || px[index] + half > (px[index + 1] ?? Infinity) - half,
    }));
    // Real anchors closer than one square are one visual group: the badge says how many
    // cards are stacked here, which is what "cannot select what is hidden" is about.
    for (let i = 0; i < out.length; i += 1) {
        for (let j = i + 1; j < out.length; j += 1) {
            if (out[j].anchorPx - out[i].anchorPx > side) break;
            out[i].groupSize += 1;
        }
    }
    return out;
}

// --- audio readiness: five states, one source of truth ---
// The panel used to show "reading audio..." forever while the footer said "validation
// passed", because nothing in the code distinguished "not read yet" from "read but no
// waveform". A cache entry now carries an explicit status, and every label in the UI is
// derived from this one function:
//   decoding       - the decode has been started, nothing is known
//   ready          - duration + sample rate confirmed, real waveform available
//   metadata_only  - duration confirmed, waveform unavailable (large or undecodable file)
//   failed         - nothing could be read; the card offers a retry
// "confirmed" is what the footer needs: without it the effective duration, the output
// end and the overlap check cannot be computed, so a full "validation passed" would lie.
export const AUDIO_DECODING = "decoding";
export const AUDIO_READY = "ready";
export const AUDIO_METADATA_ONLY = "metadata_only";
export const AUDIO_FAILED = "failed";

export function audioStatus(meta) {
    if (!meta) return { state: AUDIO_DECODING, label: "正在读取音频信息…", waveform: false, confirmed: false, retry: false };
    if (meta.status === AUDIO_DECODING) return { state: AUDIO_DECODING, label: "正在读取音频信息…", waveform: false, confirmed: false, retry: false };
    if (meta.status === AUDIO_FAILED || (!meta.duration && meta.error)) {
        return { state: AUDIO_FAILED, label: meta.error || "音频读取失败", waveform: false, confirmed: false, retry: true };
    }
    const duration = Number(meta.duration) || 0;
    if (meta.status === AUDIO_READY || (meta.peaks?.length && meta.sampleRate)) {
        return {
            state: AUDIO_READY,
            label: `波形已就绪 ${formatSeconds(duration, 2)}s · ${meta.sampleRate || "?"} Hz`,
            waveform: true, confirmed: true, retry: false,
        };
    }
    if (meta.status === AUDIO_METADATA_ONLY || duration > 0) {
        return {
            state: AUDIO_METADATA_ONLY,
            label: `时长已确认 ${formatSeconds(duration, 2)}s · 波形不可用`,
            waveform: false, confirmed: true, retry: false,
        };
    }
    return { state: AUDIO_FAILED, label: meta.error || "音频读取失败", waveform: false, confirmed: false, retry: true };
}

// The footer has three states, not two. An empty problem list is only "passed" when every
// enabled and placed audio guide has confirmed metadata; otherwise the derived checks were
// never run and the honest message is "not finished yet".
export function validationState(problems = [], pendingAudio = 0) {
    const list = Array.isArray(problems) ? problems.filter(Boolean) : [];
    if (list.length) return { level: "error", text: "", problems: list };
    if (Number(pendingAudio) > 0) {
        return {
            level: "pending",
            text: `还有 ${Number(pendingAudio)} 个音频素材的信息没有读完：音频有效时长、输出尾端与重叠检查暂时无法判断。`,
            problems: [],
        };
    }
    return { level: "ok", text: "校验通过：启用的 Guide 都在范围内，没有同帧冲突，也没有音频重叠。", problems: [] };
}

// How many enabled+placed audio guides still need metadata before the checks are complete.
export function pendingAudioCount(guides = [], readyKeys = new Set()) {
    const seen = new Set();
    for (const guide of guides) {
        if (!guide || guide.kind !== AUDIO_KIND) continue;
        if (guide.enabled === false) continue;
        if (guide.frame_index === null || guide.frame_index === undefined) continue;
        const key = mediaKeyOf(guide);
        if (readyKeys.has(key)) continue;
        seen.add(key);
    }
    return seen.size;
}
// The native H3 node rounds its length up to the next 17n+5 (comfy_extras/nodes_minimax_h3.py,
// align_frame_count). The panel draws the ruler the run would produce, so it aligns the same way.
export function alignFrameCount(value) {
    let frames = Math.max(5, Math.trunc(Number(value) || 0));
    while (frames % 17 !== 5) frames += 1;
    return frames;
}

// Seconds typed in this node's own duration box -> the frame count the run would produce.
// Mirrors core/guide_timeline.py: frames_from_seconds(). Returns 0 for "not set" so the caller
// can tell an empty box from a real instruction.
export function framesFromSeconds(seconds, fps = DEFAULT_FPS) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value <= 0) return 0;
    return alignFrameCount(Math.max(5, Math.round(value * (Number(fps) || DEFAULT_FPS))));
}

// Which length the panel draws its ruler and its range checks from.
//
// A number typed into this node's own duration box is an explicit instruction, so it wins over the
// frame count left behind by an earlier run - that number describes a past run, not what the user
// is planning now. The run value is still returned as runFrames so the panel can say out loud when
// the two disagree, because execution validates against the real latent. Without a typed number the
// last real run is the best answer, and an upstream generator's widget is only a guess.
//
// The box is in seconds because that is how a person plans a shot; the frames it converts to are
// kept in rawFrames (before alignment) and frames (after 17n+5) so the panel can show its work.
export function resolveTimelineRange(options = {}) {
    const {
        resolvedFrameCount = 0, resolvedSource = "", ownSeconds = 0, fps = DEFAULT_FPS, upstream = null,
    } = options || {};
    const seconds = Number(ownSeconds);
    const typed = Number.isFinite(seconds) && seconds > 0 ? seconds : 0;
    const rawFrames = typed > 0 ? Math.max(5, Math.round(typed * (Number(fps) || DEFAULT_FPS))) : 0;
    const run = Math.trunc(Number(resolvedFrameCount) || 0);
    if (typed > 0) {
        return {
            frames: alignFrameCount(rawFrames), source: "manual", label: "本节点的时长（秒）",
            seconds: typed, rawFrames,
            runFrames: run > 0 ? run : 0, runSource: run > 0 ? String(resolvedSource || "run") : "",
        };
    }
    if (run > 0) return { frames: run, source: String(resolvedSource || "run"), label: "", seconds: 0, rawFrames: 0, runFrames: run, runSource: "" };
    const up = Math.trunc(Number(upstream?.frames) || 0);
    if (up > 0) return { frames: up, source: "upstream", label: String(upstream.label || "上游节点"), seconds: 0, rawFrames: 0, runFrames: 0, runSource: "" };
    return { frames: 0, source: "none", label: "", seconds: 0, rawFrames: 0, runFrames: 0, runSource: "" };
}
