// RAFOLIE 2026-02: one MP4 preview modal, shared by the Picker panel and the
// Manager node's run strip. It closes with the panel that opened it.

// infoText is optional: an uploaded video has no frame count, so its card supplies
// its own caption instead of the segment one. Nothing else about the modal changes.
import { api } from "../../scripts/api.js";

export function openPreview(seg, signal, infoText) {
    const existing = document.getElementById("h3lvm-preview-overlay");
    if (existing) existing._h3Close?.();

    const overlay = document.createElement("div");
    overlay.id = "h3lvm-preview-overlay";
    overlay.className = "h3lvm-overlay";

    const modal = document.createElement("div");
    modal.className = "h3lvm-modal";

    const video = document.createElement("video");
    video.controls = true;
    video.autoplay = true;
    video.playsInline = true;
    video.className = "h3lvm-preview-video";

    const info = document.createElement("div");
    info.className = "h3lvm-preview-info";
    const seconds = seg.duration_sec != null ? seg.duration_sec.toFixed(1) + " 秒 · " : "";
    const baseInfo = infoText
        || `片段 ${seg.segment_id} · ${seg.frames} 帧 · ${seconds}${seg.width}×${seg.height}`;
    info.textContent = baseInfo;

    const actions = document.createElement("div");
    actions.className = "h3lvm-modal-actions";
    const compatibleBtn = document.createElement("button");
    compatibleBtn.className = "h3lvm-modal-close h3lvm-compatible-btn";
    compatibleBtn.textContent = "🔄 兼容预览";
    compatibleBtn.title = "画面黑屏或无法播放时，生成 H.264 临时预览；不会修改原视频";
    const closeBtn = document.createElement("button");
    closeBtn.className = "h3lvm-modal-close";
    closeBtn.textContent = "✕ 关闭";
    if (seg.proxy_url) actions.appendChild(compatibleBtn);
    actions.appendChild(closeBtn);

    modal.appendChild(video);
    modal.appendChild(info);
    modal.appendChild(actions);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    let closed = false;
    let generation = 0;
    let proxyState = seg.proxy_url ? "idle" : "unavailable";

    async function useCompatiblePreview() {
        if (closed || !seg.proxy_url || proxyState === "loading" || proxyState === "ready") return;
        const ticket = ++generation;
        proxyState = "loading";
        compatibleBtn.disabled = true;
        info.textContent = `${baseInfo} · 正在生成兼容预览…`;
        try {
            const response = await api.fetchApi(seg.proxy_url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: "{}",
            });
            const proxy = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(proxy.error || `兼容预览生成失败（HTTP ${response.status}）`);
            if (closed || ticket !== generation) return;
            proxyState = "ready";
            video.src = proxy.url;
            video.load();
            info.textContent = `${baseInfo} · H.264 兼容预览`;
            info.title = "只生成临时预览副本，原视频和正式投放输出不变";
        } catch (error) {
            if (closed || ticket !== generation) return;
            proxyState = "failed";
            info.textContent = `${baseInfo} · 兼容预览失败：${error.message}`;
        } finally {
            if (!closed && ticket === generation) {
                compatibleBtn.disabled = proxyState === "ready" || proxyState === "loading";
            }
        }
    }

    compatibleBtn.addEventListener("click", useCompatiblePreview);
    video.addEventListener("error", () => {
        if (closed) return;
        if (proxyState === "idle") {
            void useCompatiblePreview();
        } else if (proxyState === "ready") {
            info.textContent = `${baseInfo} · 兼容预览也无法播放`;
        }
    });

    function close() {
        if (closed) return;
        closed = true;
        generation++;
        video.pause();
        video.removeAttribute("src");
        video.load();
        overlay.remove();
        window.removeEventListener("keydown", onKey);
        signal?.removeEventListener("abort", close);
    }
    overlay._h3Close = close;
    signal?.addEventListener("abort", close, { once: true });
    function onKey(e) { if (e.key === "Escape") close(); }
    closeBtn.onclick = close;
    overlay.onclick = (e) => { if (e.target === overlay) close(); };
    window.addEventListener("keydown", onKey);

    if (seg.proxy_recommended) {
        void useCompatiblePreview();
    } else {
        video.src = seg.mp4_url;
    }
}
