import { api } from "../../scripts/api.js";

try {
    if (!document.getElementById("h3video-source-preview-styles")) {
        const link = document.createElement("link");
        link.id = "h3video-source-preview-styles";
        link.rel = "stylesheet";
        link.href = new URL("./source_preview.css", import.meta.url).href;
        document.head.appendChild(link);
    }
} catch (error) {
    console.warn("[H3 v2] preview CSS injection failed:", error);
}

function setWidget(widget, value) {
    if (!widget) return;
    widget.value = value;
    widget.callback?.(value);
}

export function createSourceControls(node) {
    const element = document.createElement("div");
    element.className = "h3video-node-panel h3video-source-controls";
    const browse = document.createElement("button");
    browse.type = "button";
    browse.className = "h3video-open";
    browse.textContent = "📁 选择视频…";
    browse.title = "打开 Windows 系统选框；可选择任意磁盘位置，只返回路径，不上传";
    const preview = document.createElement("button");
    preview.type = "button";
    preview.className = "h3video-preview-open";
    preview.textContent = "▶ 原视频预览";
    const selection = document.createElement("span");
    selection.className = "h3video-selection";
    element.append(browse, preview, selection);

    let dialog = null;
    let generation = 0;
    const widgetFor = name => node.widgets?.find(item => item.name === name);

    function refresh() {
        const explicit = String(widgetFor("custom_path")?.value || "").trim();
        const relative = String(widgetFor("video")?.value || "").trim();
        selection.textContent = explicit ? `完整路径：${explicit}` : relative ? `input/${relative}` : "尚未选择视频";
        selection.title = selection.textContent;
    }

    function closePreview() {
        generation++;
        dialog?.close();
        dialog = null;
    }

    browse.addEventListener("click", async () => {
        browse.disabled = true;
        selection.textContent = "请在 ComfyUI 所在电脑的系统选框中选择视频…";
        try {
            const response = await api.fetchApi("/h3_lvm/system_video_picker", { method: "POST" });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || `系统选框打开失败（HTTP ${response.status}）`);
            if (data.cancelled) {
                refresh();
                return;
            }
            closePreview();
            setWidget(widgetFor("custom_path"), data.path);
            refresh();
            node.setDirtyCanvas?.(true, true);
        } catch (error) {
            selection.textContent = `选择失败：${error.message}`;
            selection.title = selection.textContent;
        } finally {
            browse.disabled = false;
        }
    });

    preview.addEventListener("click", async () => {
        closePreview();
        const ticket = ++generation;
        preview.disabled = true;
        try {
            const response = await api.fetchApi("/h3_lvm/source_preview", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    video: widgetFor("video")?.value || "",
                    custom_path: widgetFor("custom_path")?.value || "",
                }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || `预览读取失败（HTTP ${response.status}）`);
            if (ticket !== generation) return;

            const modal = document.createElement("dialog");
            modal.className = "h3video-browser h3video-source-preview";
            modal.innerHTML = `
                <div class="h3video-head">
                    <div><strong>原视频预览</strong><span>优先直接播放；不兼容时仅生成 H.264 预览，不改源文件</span></div>
                    <div class="h3video-preview-actions">
                        <button type="button" data-action="compatible" title="画面黑屏或无法播放时，生成浏览器兼容预览">🔄 兼容预览</button>
                        <button type="button" data-action="close" title="关闭">✕</button>
                    </div>
                </div>
                <video controls preload="metadata" playsinline></video>
                <div class="h3video-preview-caption"></div>`;
            const video = modal.querySelector("video");
            const caption = modal.querySelector(".h3video-preview-caption");
            const compatible = modal.querySelector("[data-action=compatible]");
            const baseCaption = `${data.name || "源视频"} · ${data.width || "?"}×${data.height || "?"}`;
            caption.textContent = baseCaption;
            caption.title = selection.textContent;
            let proxyState = "idle";

            async function useCompatiblePreview() {
                if (proxyState === "loading" || proxyState === "ready") return;
                proxyState = "loading";
                compatible.disabled = true;
                caption.textContent = `${baseCaption} · 正在生成兼容预览…`;
                try {
                    const response = await api.fetchApi(data.proxy_url, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: "{}",
                    });
                    const proxy = await response.json().catch(() => ({}));
                    if (!response.ok) throw new Error(proxy.error || `兼容预览生成失败（HTTP ${response.status}）`);
                    if (ticket !== generation || dialog !== modal) return;
                    proxyState = "ready";
                    video.src = proxy.url;
                    video.load();
                    caption.textContent = `${baseCaption} · H.264 兼容预览`;
                } catch (error) {
                    if (ticket !== generation || dialog !== modal) return;
                    proxyState = "failed";
                    caption.textContent = `${baseCaption} · 兼容预览失败`;
                    selection.textContent = `预览失败：${error.message}`;
                    selection.title = selection.textContent;
                } finally {
                    compatible.disabled = proxyState === "ready" || proxyState === "loading";
                }
            }

            compatible.addEventListener("click", useCompatiblePreview);
            video.addEventListener("error", () => {
                if (dialog !== modal) return;
                if (proxyState === "idle") {
                    useCompatiblePreview();
                } else if (proxyState === "ready") {
                    caption.textContent = `${baseCaption} · 兼容预览也无法播放`;
                }
            });
            modal.querySelector("[data-action=close]").addEventListener("click", () => modal.close());
            modal.addEventListener("close", () => {
                video.pause();
                video.removeAttribute("src");
                video.load();
                modal.remove();
                if (dialog === modal) dialog = null;
            }, { once: true });
            dialog = modal;
            document.body.appendChild(modal);
            modal.showModal();
            if (data.proxy_recommended) {
                useCompatiblePreview();
            } else {
                video.src = data.url;
            }
        } catch (error) {
            if (ticket === generation) {
                selection.textContent = `预览失败：${error.message}`;
                selection.title = selection.textContent;
            }
        } finally {
            preview.disabled = false;
        }
    });

    refresh();
    return {
        element,
        refresh,
        close() {
            closePreview();
        },
    };
}
