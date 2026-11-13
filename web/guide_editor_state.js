// Display mapping only: these positions are not percentages of sampling steps.
export function referencePosition(config) {
    if (!config?.enabled) return 100;
    return Math.max(0, Math.min(100, (1 - Number(config.threshold)) * 100));
}
export function releaseFromPosition(raw, previous = { threshold: 0.9 }) {
    const value = Number(raw);
    if (typeof raw === 'boolean' || raw === null || !Number.isFinite(value) || raw === '' || value < 0 || value > 100) throw new Error('无效的图片参考约束');
    return value === 100
        ? { enabled: false, threshold: Number(previous.threshold ?? 0.9) }
        : { enabled: true, threshold: Math.round((1 - value / 100) * 1e6) / 1e6 };
}
export function referenceDescription(config) {
    if (!config?.enabled || Number(config.threshold) === 0) return '全程保留图片条件';
    const position = referencePosition(config);
    return position >= 65 ? '较晚释放 · 更持久地参考画面'
        : position >= 30 ? '适度保留图片条件' : '较早释放 · 后期交给模型发挥';
}
// History contains executable document data only, never selection, zoom or run metadata.
function content(doc) {
    return JSON.stringify({ guides: doc.guides, ...('keyframe_release' in doc ? { keyframe_release: doc.keyframe_release } : {}) });
}
export function createGuideHistory(doc, limit = 60) {
    let current = content(doc);
    const past = [], future = [];
    return {
        get canUndo() { return past.length > 0; },
        get canRedo() { return future.length > 0; },
        record(doc) {
            const next = content(doc);
            if (next === current) return false;
            past.push(current);
            if (past.length > limit) past.shift();
            current = next;
            future.length = 0;
            return true;
        },
        undo() { if (!past.length) return null; future.push(current); current = past.pop(); return JSON.parse(current); },
        redo() { if (!future.length) return null; past.push(current); current = future.pop(); return JSON.parse(current); },
        reset(doc) { current = content(doc); past.length = 0; future.length = 0; },
    };
}

// Viewport-only space: never writes responsive sizes into the saved document.
export function laneSpaceBonus(spare) {
    const total = Math.max(0, Math.floor(Number(spare) || 0));
    const image = Math.round(total * 0.7);
    return { image, audio: total - image };
}

export function sidebarWidthsFor(width, desired = {}) {
    const left = Math.max(200, Math.min(420, Number(desired.left) || 280));
    const right = Math.max(250, Math.min(440, Number(desired.right) || 320));
    const spare = Math.max(0, Number(width) - 300 - 450);
    const wanted = left + right - 450;
    const scale = wanted > spare ? spare / wanted : 1;
    return { left: Math.floor(200 + (left - 200) * scale), right: Math.floor(250 + (right - 250) * scale) };
}

export function localPointerX(clientX, rect, cssWidth, borderLeft = 0) {
    return (clientX - rect.left) * cssWidth / Math.max(0.001, rect.width) - borderLeft;
}
