// RAFOLIE 2026-10-19: the Segment Picker's two modes, as plain functions.
//
// The node has exactly three real inputs (project_name, segment_id, source_mode).
// Everything here is UI bookkeeping: which mode the panel is showing, and which
// project/segment belongs to which mode. It is kept free of DOM and of ComfyUI
// imports so it can be checked with node --test like the other pure web modules.
//
// The two libraries are separate on disk (h3-lvm/ vs h3-lvm-video-uploads/), so a
// project name may exist in both at once. That is why the panel keeps one entry per
// mode instead of one shared "current project".

export const MODE_SEGMENTS = "segments";
export const MODE_UPLOADS = "uploads";
export const MODE_ORDER = [MODE_SEGMENTS, MODE_UPLOADS];

// UI-only copy. The stored value is always the ASCII mode name, which is also what
// the backend node compares against.
export const MODE_LABELS = {
    [MODE_SEGMENTS]: {
        button: "🎬 裁切片段",
        title: "读取 H3 Long Video Manager / H3 Smart Split 保存的裁切片段",
        hint: "读取本插件裁切并保存的片段；先在 Manager 或 Smart Split 里保存，这里就会出现卡片。",
        footer: "👉 点卡片＝选片段 · ▶＝预览 · 🗑＝永久删除",
        emptyTitle: "还没有已保存片段",
        emptyHint: "先在「H3 Long Video Manager」节点裁切并保存，或用上方菜单新建项目",
    },
    [MODE_UPLOADS]: {
        button: "📥 投放视频",
        title: "读取你自己导入的完整视频（原文件保存，不裁切、不转码）",
        hint: "把视频文件拖进卡片区，或点「＋ 载入视频」；导入不需要运行工作流。",
        footer: "👉 拖入或「＋ 载入视频」＝导入 · 点卡片＝选视频 · ▶＝预览 · 🗑＝删除该视频",
        emptyTitle: "将视频拖入此区域，或点击＋载入视频",
        emptyHint: "原文件按原样保存，运行时按 24fps 采样输出 IMAGE/AUDIO；不裁切、不补黑帧。",
    },
};

export const MODE_STATE_KEY = "h3lvm_picker_modes";
export const DEFAULT_PROJECT = "H3_LVM";
export const TARGET_FPS = 24;

/** Anything that is not the upload mode is the original cut-segment mode. */
export function modeFromValue(value) {
    const text = String(value ?? "").trim().toLowerCase();
    return text === MODE_UPLOADS ? MODE_UPLOADS : MODE_SEGMENTS;
}

export function defaultEntry() {
    return { project_name: DEFAULT_PROJECT, segment_id: 1 };
}

/** A usable entry for one mode; anything unusable falls back to the defaults. */
export function normalizeEntry(entry) {
    const raw = entry && typeof entry === "object" ? entry : {};
    const name = typeof raw.project_name === "string" && raw.project_name.trim()
        ? raw.project_name.trim()
        : DEFAULT_PROJECT;
    const id = Number.parseInt(raw.segment_id, 10);
    return { project_name: name, segment_id: Number.isFinite(id) && id > 0 ? id : 1 };
}

export function emptyState() {
    return { [MODE_SEGMENTS]: defaultEntry(), [MODE_UPLOADS]: defaultEntry() };
}

/** Read the panel state out of node.properties, always filling in both modes. */
export function readModeState(properties) {
    const stored = properties?.[MODE_STATE_KEY];
    const state = emptyState();
    if (stored && typeof stored === "object") {
        for (const mode of MODE_ORDER) state[mode] = normalizeEntry(stored[mode]);
    }
    return state;
}

/** Pure update: returns a new state with one mode's entry replaced. */
export function saveModeState(state, mode, entry) {
    const next = { ...emptyState(), ...(state && typeof state === "object" ? state : {}) };
    next[modeFromValue(mode)] = normalizeEntry(entry);
    return next;
}

/** Store the panel state on the node so a saved workflow restores it. */
export function writeModeState(properties, state) {
    if (!properties || typeof properties !== "object") return null;
    const clean = readModeState({ [MODE_STATE_KEY]: state });
    properties[MODE_STATE_KEY] = clean;
    return clean;
}

export function entryForMode(state, mode) {
    return normalizeEntry(state?.[modeFromValue(mode)]);
}

/**
 * The first time an old workflow is opened there is no source_mode and no stored
 * state. In that case the two real widgets are the truth for the current mode, and
 * the other mode starts at the default bin - never the other way round.
 */
export function seedState(state, mode, entry) {
    const modeKey = modeFromValue(mode);
    const next = readModeState({ [MODE_STATE_KEY]: state });
    next[modeKey] = normalizeEntry(entry);
    return next;
}

export function formatDuration(seconds) {
    // null/"" mean "the index has no duration", which is not the same as 0 seconds.
    if (seconds === null || seconds === "" || seconds === undefined) return "时长未知";
    const value = Number(seconds);
    if (!Number.isFinite(value) || value < 0) return "时长未知";
    return `${value.toFixed(1)} 秒`;
}

export function formatFps(value) {
    const fps = Number(value);
    if (!Number.isFinite(fps) || fps <= 0) return "帧率未知";
    return `${Math.round(fps * 100) / 100} fps`;
}

/** True when the source is not already 24fps, so the card has to say what runs. */
export function needsFpsNote(record) {
    if (record?.variable_fps) return true;
    const fps = Number(record?.source_fps);
    return !(Number.isFinite(fps) && Math.abs(fps - TARGET_FPS) < 0.01);
}

/** Card lines for an uploaded video: size/duration, decode size, fps, audio. */
export function uploadInfoLines(record) {
    const width = Number(record?.width);
    const height = Number(record?.height);
    const size = Number.isFinite(width) && Number.isFinite(height) && width > 0 && height > 0
        ? `${width}×${height}`
        : "尺寸未知";
    const lines = [`${size} · ${formatDuration(record?.duration_sec)}`];
    // The node's 输出分辨率 caps the decode, never the file, so the card has to say which
    // of the two numbers a run produces. The server plans the size; this only formats it.
    const outWidth = Number(record?.out_width);
    const outHeight = Number(record?.out_height);
    if (record?.out_scaled && Number.isFinite(outWidth) && Number.isFinite(outHeight)) {
        lines.push(`源 ${size} → 输出 ${outWidth}×${outHeight}（原文件不变）`);
    }
    if (needsFpsNote(record)) {
        lines.push(`${formatFps(record?.source_fps)} → 输出按 ${TARGET_FPS}fps 采样`);
    } else {
        lines.push(`${TARGET_FPS}fps（与输出一致）`);
    }
    lines.push(record?.has_audio ? "含音频" : "无音轨（输出静音）");
    return lines;
}

/** The browser can only play a few containers; the node can still decode them. */
export function canBrowserPreview(record) {
    return Boolean(record?.browser_preview) && !record?.missing_file;
}

export function browserPreviewHint(record) {
    const suffix = String(record?.storage_name ?? "").toLowerCase();
    return `这个封装（${suffix.slice(suffix.lastIndexOf(".")) || "未知"}）浏览器不能直接播放，`
        + "但节点执行不受影响；需要预览请先转成 MP4。";
}
// --- Card order in the upload library (pure, so it is testable without a browser) ---
//
// The panel sends the ids in the order the user arranged them and the store renumbers
// the cards to match, because segment_id is how a workflow picks a card. These two
// helpers only compute: moveIds() turns a drag into that id list, and renumberedId()
// says which number the dragged video ends up with so the panel can follow it.
/** The same ids with the one at `from` moved to `to`; null when nothing would move. */
export function moveIds(ids, from, to) {
    const list = Array.isArray(ids) ? ids.map((value) => Number(value)).filter(Number.isFinite) : [];
    if (!list.length) return null;
    if (!Number.isInteger(from) || !Number.isInteger(to)) return null;
    if (from < 0 || to < 0 || from >= list.length || to >= list.length) return null;
    if (from === to) return null;
    const next = [...list];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    return next;
}

/** The number one id gets after a reorder; null when it is not in the new order. */
export function renumberedId(order, assetId) {
    if (!Array.isArray(order)) return null;
    const at = order.findIndex((value) => Number(value) === Number(assetId));
    return at < 0 ? null : at + 1;
}