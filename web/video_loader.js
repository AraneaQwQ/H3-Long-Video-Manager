import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addPanel } from "./dom_panel.js";

const NODE_NAME = "H3 Video Loader";
const LABELS = {
    video: "视频文件",
    custom_path: "本地完整路径（可选，优先）",
    output_size: "输出分辨率",
    custom_max_side: "自定义最长边",
};

try {
    if (!document.getElementById("h3video-loader-styles")) {
        const link = document.createElement("link");
        link.id = "h3video-loader-styles";
        link.rel = "stylesheet";
        link.href = new URL("./video_loader.css", import.meta.url).href;
        document.head.appendChild(link);
    }
} catch (error) {
    console.warn("[H3 Video Loader] CSS injection failed:", error);
}

function setWidget(widget, value) {
    if (!widget) return;
    widget.value = value;
    widget.callback?.(value);
}

function formatBytes(value) {
    const bytes = Number(value) || 0;
    if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
    if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
    return `${Math.max(0, bytes / 1024).toFixed(1)} KB`;
}

function formatDuration(value) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds < 0) return "未知";
    const minutes = Math.floor(seconds / 60);
    const rest = seconds - minutes * 60;
    return minutes ? `${minutes}分${rest.toFixed(1)}秒` : `${rest.toFixed(2)} 秒`;
}

async function responseJson(response) {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `读取失败（HTTP ${response.status}）`);
    return data;
}

export function openFileBrowser(onSelect) {
    const dialog = document.createElement("dialog");
    dialog.className = "h3video-browser";
    dialog.innerHTML = `
        <div class="h3video-head">
            <div><strong>选择服务器视频</strong><span>只读取路径，不上传、不复制文件</span></div>
            <button type="button" data-action="close" title="关闭">✕</button>
        </div>
        <div class="h3video-tools">
            <button type="button" data-action="up">← 上一级</button>
            <span class="h3video-location"></span>
            <input type="search" placeholder="筛选当前目录" aria-label="筛选当前目录">
            <button type="button" data-action="refresh">↻ 刷新</button>
        </div>
        <div class="h3video-list" role="listbox" aria-label="服务器视频文件"></div>
        <div class="h3video-foot">
            <div class="h3video-info">选择一个视频查看信息</div>
            <button type="button" data-action="cancel">取消</button>
            <button type="button" class="h3video-confirm" data-action="confirm" disabled>选择此视频</button>
        </div>`;
    document.body.appendChild(dialog);

    const list = dialog.querySelector(".h3video-list");
    const location = dialog.querySelector(".h3video-location");
    const search = dialog.querySelector("input[type=search]");
    const info = dialog.querySelector(".h3video-info");
    const up = dialog.querySelector("[data-action=up]");
    const confirm = dialog.querySelector("[data-action=confirm]");
    let directory = "";
    let parent = null;
    let directories = [];
    let files = [];
    let selected = null;
    let generation = 0;
    let infoGeneration = 0;

    function selectVideo(file) {
        selected = file;
        confirm.disabled = false;
        for (const row of list.querySelectorAll("[data-video-path]")) {
            row.classList.toggle("selected", row.dataset.videoPath === file.path);
        }
        const ticket = ++infoGeneration;
        info.textContent = "正在读取视频信息…";
        api.fetchApi(`/h3_lvm/video_file_info?path=${encodeURIComponent(file.path)}`, { cache: "no-store" })
            .then(responseJson)
            .then(data => {
                if (ticket !== infoGeneration || selected?.path !== file.path) return;
                const size = `${data.width || "?"}×${data.height || "?"}`;
                const fps = data.source_fps ? `${Number(data.source_fps).toFixed(2)} fps` : "帧率未知";
                info.textContent = `${file.name} · ${formatBytes(data.size_bytes)} · ${size} · ${formatDuration(data.duration_sec)} · ${fps} · ${data.has_audio ? "有音轨" : "无音轨"}`;
            })
            .catch(error => {
                if (ticket === infoGeneration) info.textContent = `已选择 ${file.name}；信息读取失败：${error.message}`;
            });
    }

    function choose() {
        if (!selected) return;
        onSelect(selected.path);
        dialog.close();
    }

    function renderRows() {
        list.replaceChildren();
        const query = search.value.trim().toLocaleLowerCase();
        const visibleDirectories = directories.filter(item => item.name.toLocaleLowerCase().includes(query));
        const visibleFiles = files.filter(item => item.name.toLocaleLowerCase().includes(query));
        for (const entry of visibleDirectories) {
            const row = document.createElement("button");
            row.type = "button";
            row.className = "h3video-row directory";
            row.innerHTML = "<span>📁</span>";
            const name = document.createElement("span");
            name.textContent = entry.name;
            row.append(name);
            row.addEventListener("click", () => void load(entry.path));
            list.appendChild(row);
        }
        for (const entry of visibleFiles) {
            const row = document.createElement("button");
            row.type = "button";
            row.className = "h3video-row";
            row.dataset.videoPath = entry.path;
            row.setAttribute("role", "option");
            row.classList.toggle("selected", selected?.path === entry.path);
            row.innerHTML = "<span>🎬</span>";
            const name = document.createElement("span");
            name.textContent = entry.name;
            const size = document.createElement("small");
            size.textContent = formatBytes(entry.size_bytes);
            row.append(name, size);
            row.addEventListener("click", () => selectVideo(entry));
            row.addEventListener("dblclick", () => {
                selectVideo(entry);
                choose();
            });
            list.appendChild(row);
        }
        if (!visibleDirectories.length && !visibleFiles.length) {
            const empty = document.createElement("div");
            empty.className = "h3video-empty";
            empty.textContent = query ? "当前目录没有匹配的视频" : "这里暂时没有视频；可进入子目录，或把视频复制到 input 后刷新";
            list.appendChild(empty);
        }
    }

    async function load(nextDirectory = "") {
        const ticket = ++generation;
        selected = null;
        confirm.disabled = true;
        info.textContent = "正在读取目录…";
        list.textContent = "正在读取…";
        try {
            const response = await api.fetchApi(`/h3_lvm/video_files?directory=${encodeURIComponent(nextDirectory)}`, { cache: "no-store" });
            const data = await responseJson(response);
            if (ticket !== generation) return;
            directory = data.directory || "";
            parent = data.parent;
            directories = data.directories || [];
            files = data.files || [];
            location.textContent = `input${directory ? ` / ${directory}` : ""}`;
            location.title = location.textContent;
            up.disabled = parent === null || parent === undefined;
            info.textContent = "选择一个视频查看信息";
            renderRows();
        } catch (error) {
            if (ticket !== generation) return;
            list.textContent = "";
            const message = document.createElement("div");
            message.className = "h3video-empty error";
            message.textContent = error.message;
            list.appendChild(message);
            info.textContent = "目录读取失败";
        }
    }

    dialog.querySelector("[data-action=close]").addEventListener("click", () => dialog.close());
    dialog.querySelector("[data-action=cancel]").addEventListener("click", () => dialog.close());
    dialog.querySelector("[data-action=refresh]").addEventListener("click", () => void load(directory));
    up.addEventListener("click", () => {
        if (parent !== null && parent !== undefined) void load(parent);
    });
    confirm.addEventListener("click", choose);
    search.addEventListener("input", renderRows);
    dialog.addEventListener("close", () => {
        generation++;
        infoGeneration++;
        dialog.remove();
    }, { once: true });
    dialog.showModal();
    void load("");
    return dialog;
}

function installLoaderPanel(node) {
    const container = document.createElement("div");
    container.className = "h3video-node-panel";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "h3video-open";
    button.textContent = "📁 选择视频（路径）";
    const selection = document.createElement("span");
    selection.className = "h3video-selection";
    container.append(button, selection);
    addPanel(node, "h3video_loader_panel", container, 42);

    function widgetFor(name) {
        return node.widgets?.find(item => item.name === name);
    }
    function refreshSelection() {
        const explicit = String(widgetFor("custom_path")?.value || "").trim();
        const relative = String(widgetFor("video")?.value || "").trim();
        selection.textContent = explicit ? `完整路径：${explicit}` : relative ? `input/${relative}` : "尚未选择视频";
        selection.title = selection.textContent;
    }
    button.addEventListener("click", () => {
        node._h3videoBrowser?.close();
        node._h3videoBrowser = openFileBrowser(path => {
            setWidget(widgetFor("video"), path);
            setWidget(widgetFor("custom_path"), "");
            refreshSelection();
            node.setDirtyCanvas?.(true, true);
        });
    });
    node._h3videoLoaderRefresh = refreshSelection;
    refreshSelection();
}

app.registerExtension({
    name: "H3.LVM.VideoLoader",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) return;
        const originalCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalCreated?.apply(this, arguments);
            for (const widget of this.widgets ?? []) {
                if (LABELS[widget.name]) widget.label = LABELS[widget.name];
            }
            installLoaderPanel(this);
            return result;
        };
        const originalConfigure = nodeType.prototype.configure;
        nodeType.prototype.configure = function (info) {
            const result = originalConfigure?.apply(this, arguments);
            this._h3videoLoaderRefresh?.();
            return result;
        };
        const originalRemoved = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            this._h3videoBrowser?.close();
            return originalRemoved?.apply(this, arguments);
        };
    },
});
