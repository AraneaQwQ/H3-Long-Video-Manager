// RAFOLIE 2026-10-10: the ordered media list behind the two reference loaders.
//
// The panel keeps its cards in one hidden text widget, so the order survives
// save / reload / API queue exactly like any other widget value. This file is the
// JavaScript mirror of core/ref_media.py: same JSON shape, same path rules, same
// slot limits, same truncation. No DOM and no api here on purpose - that is what
// makes the rules testable with node --test instead of only by clicking.
//
// If a rule changes here, change core/ref_media.py in the same commit; the node
// is the one that actually reads the files, so the two must not drift.

export const MAX_REF_IMAGES = 9;
export const MAX_REF_AUDIOS = 3;

const IMAGE_EXT = /\.(png|jpe?g|jfif|webp|bmp|gif|tif|tiff)$/i;
const AUDIO_EXT = /\.(wav|mp3|m4a|aac|ogg|oga|flac|opus|webm)$/i;

// The three folders ComfyUI serves through /view. The panel only ever uploads to
// "input", but a saved graph may point at a file that lives elsewhere.
export const MEDIA_TYPES = ["input", "output", "temp"];

export function mediaKind(filename) {
    const name = String(filename ?? "");
    if (AUDIO_EXT.test(name)) return "audio";
    if (IMAGE_EXT.test(name)) return "image";
    return "other";
}

export function maxSlots(kind) {
    return kind === "audio" ? MAX_REF_AUDIOS : MAX_REF_IMAGES;
}

// The official MiniMaxH3ReferenceToVideo autogrows ref_image_ / ref_audio_ with
// these prefixes, so the card label has to name the port it really feeds.
export function slotName(kind, index) {
    return `${kind === "audio" ? "ref_audio_" : "ref_image_"}${index}`;
}

// The human-facing number is 1-based: the official skill calls ref_image_0 "picture 1",
// so a card reads 参考图 1 → ref_image_0. Only slotName() is 0-based, because that is
// the port name; the two must never be swapped.
export function slotTitle(kind, index) {
    const label = index + 1;
    return kind === "audio" ? `参考音频 ${label}` : `参考图 ${label}`;
}

export function slotRangeText(kind, used, max) {
    const filled = used > 0 ? `已用 ${used}/${max}（${slotName(kind, 0)}..${slotName(kind, used - 1)}）` : `未选择（0/${max}）`;
    return `${filled} · 空槽输出 None`;
}

// --- One entry: { filename, subfolder, type } ---
export function normalizeEntry(item, index = 0) {
    const raw = typeof item === "string" ? { filename: item } : item;
    if (!raw || typeof raw !== "object") {
        throw new Error(`第 ${index + 1} 项不是有效的文件条目`);
    }
    const name = String(raw.filename ?? "").trim().replace(/\\/g, "/");
    if (!name) throw new Error(`第 ${index + 1} 项没有文件名`);
    if (name.startsWith("/") || /^[a-zA-Z]:/.test(name) || name.split("/").includes("..")) {
        throw new Error(`第 ${index + 1} 项必须是素材目录内的相对路径：${raw.filename}`);
    }
    const base = name.split("/").pop();
    if (base.startsWith(".")) throw new Error(`第 ${index + 1} 项是隐藏文件：${name}`);

    let subfolder = String(raw.subfolder ?? "").trim().replace(/\\/g, "/");
    if (subfolder.startsWith("/") || subfolder.split("/").includes("..")) {
        throw new Error(`第 ${index + 1} 项的子目录不安全：${raw.subfolder}`);
    }
    subfolder = subfolder.replace(/^\/+|\/+$/g, "");

    let type = String(raw.type ?? "input").trim().toLowerCase();
    if (!MEDIA_TYPES.includes(type)) type = "input";

    const entry = { filename: name, subfolder, type };
    // "skip" is a parked card: the file stays in the list so the panel can show it
    // and bring it back, but it holds no slot. Absent means active, which keeps
    // every workflow saved before this feature byte-identical.
    if (raw.skip === true || raw.skip === "true") entry.skip = true;
    // Trim is seconds and only audio cards have it - the same mediaKind rule
    // core/ref_media.py applies, so an image entry with a stray start key parses
    // exactly as it always did.
    if (mediaKind(name) === "audio") {
        const trim = normalizeTrim(raw.start, raw.duration);
        if (trim.start) entry.start = trim.start;
        if (trim.duration) entry.duration = trim.duration;
    }
    return entry;
}

// --- Trim: seconds, and the same rules as ComfyUI's own TrimAudioDuration ---
//
// A negative start counts back from the end of the file; a duration of 0 runs to the
// end. It belongs to the entry rather than to a node widget because every card asks
// for its own window, and because that is what makes it survive a save, a reload and
// a project preset.
export function normalizeTrim(start, duration) {
    const seconds = (value, field) => {
        if (value === null || value === undefined || value === "") return 0;
        if (typeof value === "boolean") throw new Error(`${field} 必须是秒数：${value}`);
        const number = typeof value === "number" ? value : Number(String(value).trim());
        if (!Number.isFinite(number)) throw new Error(`${field} 必须是有限的秒数：${value}`);
        return number;
    };
    const trim = { start: seconds(start, "开始时间"), duration: seconds(duration, "时长") };
    if (trim.duration < 0) throw new Error(`时长不能为负：${trim.duration}`);
    return trim;
}

export function trimRange(entry) {
    return normalizeTrim(entry?.start, entry?.duration);
}

// Where the window lands in a file of `total` seconds, after the same clamping the
// node does. The card shows this instead of the raw numbers: "start = -2" is only
// useful once you can see where it ended up.
export function resolveTrim(total, start, duration) {
    const length = Number(total);
    if (!Number.isFinite(length) || length <= 0) return null;
    const first = Math.min(Math.max(start < 0 ? length + start : start, 0), length);
    const last = Math.min(Math.max(duration ? first + duration : length, first), length);
    return { first, last, empty: last <= first };
}

export function hasTrim(entry) {
    const trim = trimRange(entry);
    return trim.start !== 0 || trim.duration !== 0;
}

export function formatTime(seconds) {
    const value = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(value / 60);
    const rest = value - minutes * 60;
    return `${minutes}:${rest < 10 ? "0" : ""}${rest.toFixed(2)}`;
}

export function parseMedia(raw, max = MAX_REF_IMAGES) {
    const text = typeof raw === "string" ? raw.trim() : raw;
    if (text === null || text === undefined || text === "") return { entries: [], truncated: 0 };

    let data = text;
    if (typeof text === "string") {
        try {
            data = JSON.parse(text);
        } catch (error) {
            throw new Error(`media_files 不是有效的 JSON：${error.message}`);
        }
    }
    if (!Array.isArray(data)) throw new Error("media_files 必须是文件条目的 JSON 列表");

    const entries = data.map((item, index) => normalizeEntry(item, index));
    // Only the cards that hold a slot are limited. A parked card costs nothing, so
    // truncating it would quietly delete work the user chose to keep.
    const kept = [];
    let used = 0;
    let truncated = 0;
    for (const entry of entries) {
        if (isSkipped(entry)) {
            kept.push(entry);
            continue;
        }
        if (used >= max) {
            truncated++;
            continue;
        }
        used++;
        kept.push(entry);
    }
    return { entries: kept, truncated };
}

// Key order is fixed so an unchanged list never looks like an edit in a diff.
export function serializeMedia(entries) {
    return JSON.stringify((entries ?? []).map(entry => {
        const item = {
            filename: entry.filename,
            subfolder: entry.subfolder || "",
            type: entry.type || "input",
        };
        if (isSkipped(entry)) item.skip = true;
        // Key order is fixed here too, and a zero is left out: an untrimmed card keeps
        // the exact bytes it had before trim existed.
        if (Number(entry.start)) item.start = Number(entry.start);
        if (Number(entry.duration)) item.duration = Number(entry.duration);
        return item;
    }));
}

export function mediaKey(entry) {
    return `${entry?.type || "input"}|${entry?.subfolder || ""}|${entry?.filename || ""}`;
}

// --- List edits: every one of them returns a new array, never mutates ---
export function addEntries(entries, incoming, max) {
    // New cards join the slot block, never the parked block behind it. A parked
    // file still counts as "already here", so adding it again stays a no-op.
    const { active, parked } = splitEntries(entries);
    const out = active;
    const seen = new Set([...out, ...parked].map(mediaKey));
    let added = 0;
    let skipped = 0;
    for (const item of incoming ?? []) {
        const entry = normalizeEntry(item, out.length + skipped);
        const key = mediaKey(entry);
        if (seen.has(key)) {
            skipped++;
            continue;
        }
        if (out.length >= max) {
            skipped++;
            continue;
        }
        seen.add(key);
        out.push(entry);
        added++;
    }
    return { entries: [...out, ...parked], added, skipped };
}

export function removeEntry(entries, index) {
    const out = [...(entries ?? [])];
    if (index >= 0 && index < out.length) out.splice(index, 1);
    return out;
}

export function replaceEntry(entries, index, item) {
    const out = [...(entries ?? [])];
    if (index < 0 || index >= out.length) return out;
    out[index] = normalizeEntry(item, index);
    return out;
}

export function moveEntry(entries, index, delta) {
    const out = [...(entries ?? [])];
    const to = index + delta;
    if (index < 0 || index >= out.length || to < 0 || to >= out.length) return out;
    const [item] = out.splice(index, 1);
    out.splice(to, 0, item);
    return out;
}

// --- Parked cards: the 跳过 / 放回 pair ---
//
// A parked card stays in the same list but holds no slot: core/ref_media.py drops
// it before filling ref_image_ / ref_audio_, so the numbered ports are the active
// cards only. The list keeps one canonical order - slot cards first, parked cards
// after - which is why the deck can draw two blocks out of one field and why a
// card's position in the deck is its index in this list.
export function isSkipped(entry) {
    return entry?.skip === true;
}

export function splitEntries(entries) {
    const active = [];
    const parked = [];
    for (const entry of entries ?? []) {
        (isSkipped(entry) ? parked : active).push(entry);
    }
    return { active, parked };
}

export function countActive(entries) {
    return splitEntries(entries).active.length;
}

// Park one card: index is the slot number printed on the card, and the card moves
// to the back of the deck instead of disappearing.
export function skipAt(entries, index) {
    const { active, parked } = splitEntries(entries);
    if (index < 0 || index >= active.length) return [...(entries ?? [])];
    const [moved] = active.splice(index, 1);
    return [...active, ...parked, { ...moved, skip: true }];
}

// Bring one parked card back at the end of the slot order. It never steals a slot
// from a card already in use: without room nothing moves, and the caller says why.
export function restoreAt(entries, index, max = Infinity) {
    const { active, parked } = splitEntries(entries);
    if (index < 0 || index >= parked.length) return { entries: [...(entries ?? [])], restored: 0 };
    if (active.length >= max) return { entries: [...(entries ?? [])], restored: 0 };
    const back = { ...parked[index] };
    delete back.skip;
    parked.splice(index, 1);
    return { entries: [...active, back, ...parked], restored: 1 };
}

// The same for every parked card, in order, stopping at the slot limit.
export function restoreAll(entries, max = Infinity) {
    const { active, parked } = splitEntries(entries);
    const out = [...active];
    for (const entry of parked) {
        if (out.length >= max) break;
        const back = { ...entry };
        delete back.skip;
        out.push(back);
    }
    const restored = out.length - active.length;
    return { entries: [...out, ...parked.slice(restored)], restored, blocked: parked.length - restored };
}

// Reorder inside the slot block only; a parked card has no slot to move into.
export function moveActive(entries, index, delta) {
    const { active, parked } = splitEntries(entries);
    const to = index + delta;
    if (index < 0 || index >= active.length || to < 0 || to >= active.length) return [...(entries ?? [])];
    const out = [...active];
    const [item] = out.splice(index, 1);
    out.splice(to, 0, item);
    return [...out, ...parked];
}

// Where a dragged card would land, as a position in the list as it is drawn now
// (0 = before the first card, n = after the last one), or -1 when the drop would
// change nothing.
//
// The pointer aims at the NEAREST card rather than the card exactly under it. That
// is the whole point: aiming only under the pointer made dragging feel broken,
// because a gap between two cards returned "end of the list" and a pointer a few
// pixels outside the grid returned "no target at all".
//
// rects is plain data on purpose - the caller reads getBoundingClientRect(), and a
// wrapping grid is easy to test when the geometry is an argument.
export function insertPosition(rects, x, y, draggedIndex) {
    const boxes = [];
    for (const rect of rects ?? []) {
        const box = {
            index: Number(rect?.index),
            left: Number(rect?.left),
            top: Number(rect?.top),
            right: Number(rect?.right),
            bottom: Number(rect?.bottom),
        };
        if ([box.index, box.left, box.top, box.right, box.bottom].every(Number.isFinite)) {
            boxes.push(box);
        }
    }
    if (!boxes.length) return -1;

    // Distance to the box edge, so a pointer in a gap still has a clear nearest card.
    let aim = null;
    let best = Infinity;
    for (const box of boxes) {
        const dx = Math.max(box.left - x, 0, x - box.right);
        const dy = Math.max(box.top - y, 0, y - box.bottom);
        const distance = dx * dx + dy * dy;
        if (distance < best) {
            best = distance;
            aim = box;
        }
    }
    if (!aim || aim.index === Number(draggedIndex)) return -1;

    // Same row as the aim -> before/after split at its middle. Below or above it ->
    // after/before, which is how a wrapping grid reads.
    if (y >= aim.top && y <= aim.bottom) {
        return x > (aim.left + aim.right) / 2 ? aim.index + 1 : aim.index;
    }
    return y > aim.bottom ? aim.index + 1 : aim.index;
}

// --- Project presets: the same entries, kept per project as paths only ---
//
// The server keeps { project_name, references: [...] } in one project of one kind's
// library (comfyui/ref_presets.py): image presets and audio presets live in different
// folders, so the audio loader can never offer the image projects of a story. A preset
// is a shortcut for "the references of this project", not a second copy of the media:
// every entry is the same { filename, subfolder, type } path a card already holds.
//
// A preset is saved with its order and its skip flags, and both are part of what the
// user arranged: the order of the slot cards IS the order of the ref_image_ ports, and
// a parked card has to come back parked. So loading one rebuilds the list from the
// preset instead of appending paths to whatever the panel happens to hold.
//
// Defensive on purpose - the panel must keep working when a preset is missing or
// half-written, and the server already re-validates every entry it hands back.
export function pickPresetEntries(preset) {
    const list = preset?.references;
    return Array.isArray(list) ? list : [];
}

// Rebuild a card list from a preset: the panel becomes the preset - its cards in the
// saved order, each one active or parked exactly as saved. Cards the panel holds that
// the preset does not mention are removed: a preset IS the reference set of a project,
// so keeping the leftovers beside it means the next run quietly carries references the
// user had already decided against. Adding a card back is a normal add, not a side
// effect of loading. The slot limit still only counts the active block.
export function applyPreset(entries, incoming, max) {
    const wanted = [];
    const seen = new Set();
    let ignored = 0;
    for (const item of incoming ?? []) {
        try {
            const entry = normalizeEntry(item, wanted.length + ignored);
            const key = mediaKey(entry);
            if (seen.has(key)) {
                ignored++;
                continue;
            }
            seen.add(key);
            wanted.push(entry);
        } catch (error) {
            ignored++;
        }
    }

    const saved = splitEntries(wanted);
    const current = splitEntries(entries);
    // What the panel is about to lose, so the status line can say so out loud.
    const dropped = current.active.filter(entry => !seen.has(mediaKey(entry))).length
        + current.parked.filter(entry => !seen.has(mediaKey(entry))).length;

    const placed = saved.active.slice(0, max);
    return {
        entries: [...placed, ...saved.parked],
        restored: placed.length + saved.parked.length,
        parked: saved.parked.length,
        dropped,
        truncated: saved.active.length - placed.length,
        ignored,
    };
}

// --- Card text ---
export function sizeLine({ source, plan, full = false }) {
    if (!source) return "读取尺寸中…";
    if (!plan) return `${source.width}×${source.height} · 计算输出尺寸中…`;
    const mp = Number(plan.actual_megapixels);
    const mpText = Number.isFinite(mp) ? ` · ${mp.toFixed(2)} MP` : "";
    // "grid_align" means the target MP was deliberately not applied to this image
    // (upscale is off, only the 32 grid was). Saying so is what stops a small image
    // from looking like a bug on the card. The card only gets the short marker, because
    // its info block is a fixed two lines and a long sentence is what overflows it;
    // the tooltip passes full: true and gets the whole wording.
    const kept = plan.mode === "grid_align" ? (full ? "（未放大，仅对齐网格）" : " · 未放大") : "";
    return `${source.width}×${source.height} → ${plan.width}×${plan.height}${mpText}${kept}`;
}

export function formatDuration(seconds) {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value <= 0) return "";
    return `${value.toFixed(2)} 秒`;
}

export function audioInfoLine({ duration, sampleRate, channels, trimStart = 0, trimLength = 0 }) {
    // A trimmed card says what H3 will actually receive, and keeps the real file length
    // in the same line, so the window can never be read as the length of the file.
    const parts = [];
    const length = formatDuration(duration);
    const window = trimStart || trimLength ? resolveTrim(duration, trimStart, trimLength) : null;
    if (window) {
        parts.push(`${formatTime(window.first)} → ${formatTime(window.last)} · ${(window.last - window.first).toFixed(2)} 秒`);
    } else if (length) {
        parts.push(length);
    }
    const rate = Number(sampleRate);
    if (Number.isFinite(rate) && rate > 0) parts.push(`${Math.round(rate / 1000)} kHz`);
    const ch = Number(channels);
    if (Number.isFinite(ch) && ch > 0) parts.push(ch === 1 ? "单声道" : `${ch} 声道`);
    if (window && length) parts.push(`全片 ${length}`);
    if (window?.empty) parts.push("⚠ 裁切后没有样本");
    return parts.length ? parts.join(" · ") : "读取音频信息中…";
}
