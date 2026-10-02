// RAFOLIE 2026-02: one MP4 preview modal, shared by the Picker panel and the
// Manager node's run strip. It closes with the panel that opened it.

export function openPreview(seg, signal) {
    const existing = document.getElementById("h3lvm-preview-overlay");
    if (existing) existing._h3Close?.();

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
    const seconds = seg.duration_sec != null ? seg.duration_sec.toFixed(1) + " 秒 · " : "";
    info.textContent = `片段 ${seg.segment_id} · ${seg.frames} 帧 · ${seconds}${seg.width}×${seg.height}`;

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
}
