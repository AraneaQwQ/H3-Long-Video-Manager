import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addPanel } from "./dom_panel.js";

const NODE_NAME = "H3 Video Compare Slider";
const PANEL_MIN_HEIGHT = 430;

const LABELS = {
    slider_position: "初始分割位置",
    before_label: "左侧标签",
    after_label: "右侧标签",
    show_labels: "显示标签",
    loop: "循环播放",
    muted: "静音",
    record_duration: "录制时长（秒）",
    fps: "IMAGE 帧率",
};

function element(tag, className, text = "") {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text) item.textContent = text;
    return item;
}

function actionButton(text, title) {
    const item = element("button", "h3lvm-refresh-btn h3-vc-button", text);
    item.type = "button";
    item.title = title;
    return item;
}

function timeText(value) {
    const total = Math.max(0, Number(value) || 0);
    const minutes = Math.floor(total / 60);
    const seconds = Math.floor(total - minutes * 60);
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function createCompareView(node) {
    const lifetime = new AbortController();
    const signal = lifetime.signal;
    const listen = (target, type, handler, options = {}) => {
        target.addEventListener(type, handler, { ...options, signal });
    };
    const widget = name => node.widgets?.find(item => item.name === name);
    const value = (name, fallback) => widget(name)?.value ?? fallback;
    const writeValue = (name, next) => {
        const target = widget(name);
        if (!target) return;
        target.value = next;
        node.setDirtyCanvas?.(true, true);
    };

    const root = element("div", "h3-vc-root");
    const stageHome = element("div", "h3-vc-stage-home");
    const stage = element("div", "h3-vc-stage");
    const before = document.createElement("video");
    const after = document.createElement("video");
    const afterLayer = element("div", "h3-vc-after-layer");
    const divider = element("div", "h3-vc-divider");
    const grip = element("div", "h3-vc-grip", "↔");
    const beforeTag = element("div", "h3-vc-tag h3-vc-before-tag");
    const afterTag = element("div", "h3-vc-tag h3-vc-after-tag");
    const placeholder = element("div", "h3-vc-placeholder", "运行节点，或在下方分别选择两个视频");
    grip.tabIndex = 0;
    grip.setAttribute("role", "slider");
    grip.setAttribute("aria-label", "对比分割位置");
    grip.setAttribute("aria-valuemin", "0");
    grip.setAttribute("aria-valuemax", "100");
    divider.appendChild(grip);
    afterLayer.appendChild(after);
    stage.append(before, afterLayer, divider, beforeTag, afterTag, placeholder);
    stageHome.appendChild(stage);

    for (const player of [before, after]) {
        player.className = "h3-vc-video";
        player.preload = "metadata";
        player.playsInline = true;
        player.disablePictureInPicture = true;
    }
    after.muted = true;

    const play = actionButton("▶ 播放", "同步播放或暂停两个视频");
    const restart = actionButton("↺ 从头", "两个视频一起回到开头");
    const timeline = document.createElement("input");
    timeline.type = "range";
    timeline.min = "0";
    timeline.max = "0";
    timeline.step = "0.01";
    timeline.className = "h3-vc-range";
    const clock = element("span", "h3-vc-clock", "00:00 / 00:00");
    const loop = actionButton("🔁 循环", "开启或关闭循环播放");
    const mute = actionButton("🔇", "开启或关闭原视频声音");
    const fullscreen = actionButton("⛶ 全屏", "全屏对比，滚轮缩放");
    const toolbar = element("div", "h3-vc-toolbar");
    toolbar.append(play, restart, timeline, clock, loop, mute, fullscreen);
    const toolbarHome = element("div", "h3-vc-toolbar-home");
    toolbarHome.appendChild(toolbar);

    const chooseBefore = actionButton("选择 / 更换", "从电脑上传处理前的视频");
    const chooseAfter = actionButton("选择 / 更换", "从电脑上传处理后的视频");
    const beforePicker = document.createElement("input");
    const afterPicker = document.createElement("input");
    for (const picker of [beforePicker, afterPicker]) {
        picker.type = "file";
        picker.accept = ".mp4,.mov,.webm,.mkv,.avi,.m4v,video/*";
        picker.hidden = true;
    }
    const beforeName = element("span", "h3-vc-source-name", "未选择");
    const afterName = element("span", "h3-vc-source-name", "未选择");
    const beforeSource = element("div", "h3-vc-source");
    const afterSource = element("div", "h3-vc-source");
    beforeSource.append(element("span", "h3-vc-source-label", "原视频"), beforeName, chooseBefore);
    afterSource.append(element("span", "h3-vc-source-label", "处理后"), afterName, chooseAfter);
    const fileStatus = element("div", "h3-vc-file-status");
    const fileRow = element("div", "h3-vc-file-row");
    fileRow.append(beforeSource, afterSource, beforePicker, afterPicker);

    const record = actionButton("● 录制对比视频", "把当前分割画面录制成 MP4");
    const recordStatus = element("div", "h3-vc-record-status");
    const recordRow = element("div", "h3-vc-record-row");
    recordRow.append(record, recordStatus);

    const settings = element("details", "h3-vc-settings");
    settings.open = true;
    const settingsSummary = element("summary", "h3-vc-settings-summary", "⚙ 对比设置");
    const settingsGrid = element("div", "h3-vc-settings-grid");
    const settingField = (labelText, control) => {
        const field = element("label", "h3-vc-setting");
        field.append(element("span", "", labelText), control);
        return field;
    };
    const beforeLabelInput = document.createElement("input");
    const afterLabelInput = document.createElement("input");
    for (const [input, name] of [[beforeLabelInput, "before_label"], [afterLabelInput, "after_label"]]) {
        input.type = "text";
        input.name = name;
        input.maxLength = 40;
    }
    const showLabelsInput = document.createElement("input");
    showLabelsInput.type = "checkbox";
    showLabelsInput.name = "show_labels";
    const recordDurationInput = document.createElement("input");
    recordDurationInput.type = "number";
    recordDurationInput.name = "record_duration";
    recordDurationInput.min = "0.5";
    recordDurationInput.max = "300";
    recordDurationInput.step = "0.5";
    const fpsInput = document.createElement("input");
    fpsInput.type = "number";
    fpsInput.name = "fps";
    fpsInput.min = "1";
    fpsInput.max = "240";
    fpsInput.step = "0.1";
    settingsGrid.append(
        settingField("左侧标签", beforeLabelInput),
        settingField("右侧标签", afterLabelInput),
        settingField("显示标签", showLabelsInput),
        settingField("录制时长（秒）", recordDurationInput),
        settingField("IMAGE 帧率", fpsInput),
    );
    settings.append(settingsSummary, settingsGrid);
    root.append(stageHome, toolbarHome, fileRow, fileStatus, recordRow, settings);

    let duration = 0;
    let splitPosition = 0.5;
    let syncFrame = 0;
    let splitDragging = false;
    let recorder = null;
    let recordTimer = 0;
    let recordFrame = 0;
    let overlay = null;
    let zoom = 1;
    let zoomOrigin = { x: 50, y: 50 };
    let zoomReadout = null;
    let destroyed = false;
    const temporaryUrls = new Set();

    function mediaUrl(path) {
        return api.apiURL(`/h3_lvm/video_compare/media?path=${encodeURIComponent(path)}`);
    }

    function applySettings() {
        const labelsVisible = Boolean(value("show_labels", true));
        beforeTag.textContent = String(value("before_label", "原视频") || "原视频");
        afterTag.textContent = String(value("after_label", "处理后") || "处理后");
        beforeTag.hidden = !labelsVisible;
        afterTag.hidden = !labelsVisible;
        before.muted = Boolean(value("muted", true));
        const looping = Boolean(value("loop", true));
        loop.setAttribute("aria-pressed", String(looping));
        loop.title = looping ? "关闭循环播放" : "开启循环播放";
        mute.textContent = before.muted ? "🔇" : "🔊";
        mute.setAttribute("aria-pressed", String(before.muted));
        mute.setAttribute("aria-label", before.muted ? "开启原视频声音" : "关闭原视频声音");
        if (document.activeElement !== beforeLabelInput) beforeLabelInput.value = beforeTag.textContent;
        if (document.activeElement !== afterLabelInput) afterLabelInput.value = afterTag.textContent;
        showLabelsInput.checked = labelsVisible;
        if (document.activeElement !== recordDurationInput) recordDurationInput.value = String(value("record_duration", 5));
        if (document.activeElement !== fpsInput) fpsInput.value = String(value("fps", 24));
        setSplit(value("slider_position", 0.5), false);
    }

    function setSplit(raw, save) {
        const position = Math.max(0, Math.min(1, Number(raw) || 0));
        splitPosition = position;
        const percent = position * 100;
        afterLayer.style.clipPath = `inset(0 0 0 ${percent}%)`;
        divider.style.left = `${percent}%`;
        grip.setAttribute("aria-valuenow", String(Math.round(percent)));
        if (save) writeValue("slider_position", Math.round(position * 100) / 100);
    }

    function updateClock() {
        const current = Math.max(0, Math.min(duration || Infinity, Number(before.currentTime) || 0));
        if (document.activeElement !== timeline) timeline.value = String(current);
        clock.textContent = `${timeText(current)} / ${timeText(duration)}`;
    }

    function updateDuration() {
        const lengths = [before.duration, after.duration]
            .map(Number)
            .filter(item => Number.isFinite(item) && item > 0);
        duration = lengths.length ? Math.min(...lengths) : 0;
        timeline.max = String(duration);
        updateClock();
    }

    function seek(raw) {
        const target = Math.max(0, Math.min(duration || Number(raw) || 0, Number(raw) || 0));
        try {
            before.currentTime = target;
            after.currentTime = target;
        } catch {
            return;
        }
        updateClock();
    }

    function pause() {
        before.pause();
        after.pause();
        play.textContent = "▶ 播放";
        cancelAnimationFrame(syncFrame);
        syncFrame = 0;
    }

    function synchronize() {
        if (before.paused || destroyed) {
            syncFrame = 0;
            return;
        }
        if (duration > 0 && before.currentTime >= duration - 0.03) {
            if (value("loop", true)) {
                seek(0);
            } else {
                seek(duration);
                pause();
                return;
            }
        }
        if (Math.abs(after.currentTime - before.currentTime) > 0.075) {
            try {
                after.currentTime = before.currentTime;
            } catch {
                // The next frame retries after metadata has loaded.
            }
        }
        if (after.playbackRate !== before.playbackRate) {
            after.playbackRate = before.playbackRate;
        }
        updateClock();
        syncFrame = requestAnimationFrame(synchronize);
    }

    async function startPlayback() {
        if (!before.src || !after.src) return false;
        if (duration > 0 && before.currentTime >= duration - 0.03) seek(0);
        before.muted = Boolean(value("muted", true));
        after.muted = true;
        try {
            after.currentTime = before.currentTime;
            await Promise.all([before.play(), after.play()]);
            play.textContent = "Ⅱ 暂停";
            if (!syncFrame) syncFrame = requestAnimationFrame(synchronize);
            return true;
        } catch (error) {
            pause();
            fileStatus.textContent = `播放失败：${error?.message || error}`;
            return false;
        }
    }

    function clearPlayer(player) {
        player.pause();
        player.removeAttribute("src");
        player.load();
    }

    function load(items = [], settings = {}) {
        const beforeInfo = items.find(item => item?.role === "before") || items[0];
        const afterInfo = items.find(item => item?.role === "after") || items[1];
        if (!beforeInfo?.path || !afterInfo?.path) return;
        pause();
        for (const name of [
            "slider_position", "before_label", "after_label", "show_labels",
            "loop", "muted", "record_duration", "fps",
        ]) {
            if (settings[name] !== undefined) writeValue(name, settings[name]);
        }
        duration = 0;
        timeline.max = "0";
        timeline.value = "0";
        before.src = mediaUrl(beforeInfo.path);
        after.src = mediaUrl(afterInfo.path);
        before.load();
        after.load();
        placeholder.hidden = true;
        beforeName.textContent = beforeInfo.name || "原视频";
        afterName.textContent = afterInfo.name || "处理后";
        beforeName.title = beforeName.textContent;
        afterName.title = afterName.textContent;
        fileStatus.classList.remove("h3-vc-error");
        fileStatus.textContent = "";
        applySettings();
    }

    function previewSelected() {
        const beforePath = String(value("before_selected", "") || "");
        const afterPath = String(value("after_selected", "") || "");
        if (beforePath && afterPath) {
            load([
                { role: "before", path: beforePath, name: beforePath.split(/[\\/]/).pop() },
                { role: "after", path: afterPath, name: afterPath.split(/[\\/]/).pop() },
            ]);
        }
    }

    function setZoom(next, x = zoomOrigin.x, y = zoomOrigin.y) {
        zoom = Math.max(1, Math.min(6, Number(next) || 1));
        zoomOrigin = {
            x: Math.max(0, Math.min(100, Number(x) || 0)),
            y: Math.max(0, Math.min(100, Number(y) || 0)),
        };
        for (const player of [before, after]) {
            player.style.transform = `scale(${zoom})`;
            player.style.transformOrigin = `${zoomOrigin.x}% ${zoomOrigin.y}%`;
        }
        if (zoomReadout) zoomReadout.textContent = `${Math.round(zoom * 100)}%`;
    }

    function closeFullscreen(exitNative = true) {
        if (!overlay) return;
        const current = overlay;
        overlay = null;
        if (exitNative && document.fullscreenElement === current) {
            document.exitFullscreen?.().catch(() => {});
        }
        stageHome.appendChild(stage);
        toolbarHome.appendChild(toolbar);
        stage.classList.remove("h3-vc-stage-fullscreen");
        current.remove();
        fullscreen.textContent = "⛶ 全屏";
        zoomReadout = null;
        setZoom(1, 50, 50);
    }

    function openFullscreen() {
        if (overlay) return;
        overlay = element("div", "h3-vc-overlay");
        const header = element("div", "h3-vc-overlay-header");
        const title = element("strong", "", "H3 视频对比滑块");
        const tools = element("div", "h3-vc-overlay-tools");
        zoomReadout = element("span", "h3-vc-zoom", "100%");
        const reset = actionButton("重置缩放", "恢复 100%");
        const close = actionButton("✕ 退出全屏", "返回 ComfyUI 节点");
        tools.append(zoomReadout, reset, close);
        header.append(title, tools);
        overlay.append(header, stage, toolbar);
        stage.classList.add("h3-vc-stage-fullscreen");
        document.body.appendChild(overlay);
        fullscreen.textContent = "✕ 退出全屏";
        listen(reset, "click", () => setZoom(1, 50, 50));
        listen(close, "click", () => closeFullscreen());
        overlay.requestFullscreen?.().catch(() => {});
    }

    function drawContained(context, player, width, height) {
        if (!player.videoWidth || !player.videoHeight) return;
        const scale = Math.min(width / player.videoWidth, height / player.videoHeight);
        const drawWidth = player.videoWidth * scale;
        const drawHeight = player.videoHeight * scale;
        context.drawImage(
            player,
            (width - drawWidth) / 2,
            (height - drawHeight) / 2,
            drawWidth,
            drawHeight,
        );
    }

    function paintRecording(context, width, height) {
        context.fillStyle = "#050505";
        context.fillRect(0, 0, width, height);
        drawContained(context, before, width, height);
        const position = splitPosition;
        context.save();
        context.beginPath();
        context.rect(width * position, 0, width * (1 - position), height);
        context.clip();
        drawContained(context, after, width, height);
        context.restore();
        context.strokeStyle = "#ffffff";
        context.lineWidth = Math.max(2, width / 700);
        context.beginPath();
        context.moveTo(width * position, 0);
        context.lineTo(width * position, height);
        context.stroke();
        if (value("show_labels", true)) {
            context.font = "700 22px Arial, sans-serif";
            const left = beforeTag.textContent;
            const right = afterTag.textContent;
            context.fillStyle = "rgba(0,0,0,.7)";
            context.fillRect(12, 12, context.measureText(left).width + 20, 34);
            context.fillRect(width - context.measureText(right).width - 32, 12, context.measureText(right).width + 20, 34);
            context.fillStyle = "#ffffff";
            context.fillText(left, 22, 37);
            context.fillText(right, width - context.measureText(right).width - 22, 37);
        }
    }

    function stopCapture(stream) {
        for (const track of stream?.getTracks?.() || []) track.stop();
    }

    function stopRecording() {
        const active = recorder;
        if (!active) return;
        clearTimeout(recordTimer);
        cancelAnimationFrame(recordFrame);
        if (active.state !== "inactive") {
            try {
                active.stop();
            } catch {
                if (recorder === active) recorder = null;
            }
        }
        stopCapture(active.stream);
        pause();
        record.disabled = false;
        record.textContent = "● 录制对比视频";
        record.classList.remove("h3-vc-record");
        recordStatus.textContent = "正在整理录制文件…";
    }

    function startRecording() {
        if (recorder || !before.src || !after.src) return;
        if (before.readyState < 2 || after.readyState < 2
                || !before.videoWidth || !after.videoWidth) {
            recordStatus.textContent = "视频尚未加载完成，请稍候再录制。";
            return;
        }
        const canvas = document.createElement("canvas");
        const sourceWidth = before.videoWidth;
        const sourceHeight = before.videoHeight;
        const scale = Math.min(1, 1920 / Math.max(sourceWidth, sourceHeight));
        canvas.width = Math.max(2, Math.round(sourceWidth * scale / 2) * 2);
        canvas.height = Math.max(2, Math.round(sourceHeight * scale / 2) * 2);
        const context = canvas.getContext("2d");
        if (!context || typeof canvas.captureStream !== "function" || typeof MediaRecorder === "undefined") {
            recordStatus.textContent = "当前浏览器不支持录制，请使用最新版 Chrome 或 Edge。";
            return;
        }
        const stream = canvas.captureStream(30);
        const mimeType = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"]
            .find(type => MediaRecorder.isTypeSupported(type));
        if (!mimeType) {
            stopCapture(stream);
            recordStatus.textContent = "当前浏览器不支持录制，请使用最新版 Chrome 或 Edge。";
            return;
        }
        const chunks = [];
        let failed = false;
        let failureMessage = "";
        try {
            recorder = new MediaRecorder(stream, {
                mimeType,
                videoBitsPerSecond: 8_000_000,
            });
        } catch (error) {
            stopCapture(stream);
            recordStatus.textContent = `无法启动录制：${error?.message || error}`;
            return;
        }
        const active = recorder;
        active.ondataavailable = event => {
            if (event.data.size) chunks.push(event.data);
        };
        active.onerror = event => {
            failed = true;
            failureMessage = event.error?.message || "浏览器录制失败。";
            stopRecording();
        };
        active.onstop = async () => {
            stopCapture(active.stream);
            if (recorder === active) recorder = null;
            clearTimeout(recordTimer);
            cancelAnimationFrame(recordFrame);
            record.disabled = false;
            record.textContent = "● 录制对比视频";
            record.classList.remove("h3-vc-record");
            if (destroyed || failed) {
                chunks.length = 0;
                if (failed && !destroyed) recordStatus.textContent = `录制失败：${failureMessage}`;
                return;
            }
            const blob = new Blob(chunks, { type: mimeType });
            chunks.length = 0;
            recordStatus.textContent = "正在保存 MP4 到 ComfyUI output…";
            try {
                const form = new FormData();
                form.append("file", blob, "h3-video-compare.webm");
                const response = await api.fetchApi("/h3_lvm/video_compare/recording", {
                    method: "POST",
                    body: form,
                    signal,
                });
                const data = await response.json();
                if (!response.ok || !data.ok) throw new Error(data.error || "保存失败");
                const link = element("a", "h3-vc-download", `下载 MP4（${data.name}）`);
                link.href = mediaUrl(data.path);
                link.download = data.name;
                recordStatus.replaceChildren(link);
            } catch (error) {
                if (destroyed) return;
                const url = URL.createObjectURL(blob);
                temporaryUrls.add(url);
                const link = element("a", "h3-vc-download h3-vc-error", "MP4 保存失败，下载临时 WebM");
                link.href = url;
                link.download = "h3-video-compare.webm";
                recordStatus.replaceChildren(link);
                console.error("[H3 Video Compare] recording save failed:", error);
            }
        };
        try {
            active.start(1000);
        } catch (error) {
            recorder = null;
            stopCapture(stream);
            recordStatus.textContent = `无法启动录制：${error?.message || error}`;
            return;
        }
        record.disabled = false;
        record.textContent = "■ 停止";
        record.classList.add("h3-vc-record");
        recordStatus.textContent = "录制中，可以拖动分割线";
        void startPlayback().then(playing => {
            if (!playing && recorder === active) {
                failed = true;
                failureMessage = "视频播放失败，录制已停止。";
                stopRecording();
            }
        });
        const started = performance.now();
        const durationMs = Math.max(500, Number(value("record_duration", 5)) * 1000);
        const paint = () => {
            paintRecording(context, canvas.width, canvas.height);
            if (recorder === active && performance.now() - started < durationMs) {
                recordFrame = requestAnimationFrame(paint);
            }
        };
        paint();
        recordTimer = setTimeout(stopRecording, durationMs);
    }

    async function upload(file, role) {
        if (!file) return;
        fileStatus.classList.remove("h3-vc-error");
        fileStatus.textContent = `正在上传 ${file.name}…`;
        const form = new FormData();
        form.append("video", file, file.name);
        try {
            const response = await api.fetchApi("/h3_lvm/video_compare/upload", {
                method: "POST",
                body: form,
                    signal,
            });
            const data = await response.json();
            if (!response.ok || !data.ok || !data.path) {
                throw new Error(data.error || `HTTP ${response.status}`);
            }
            writeValue(role === "before" ? "before_selected" : "after_selected", data.path);
            previewSelected();
        } catch (error) {
            if (destroyed) return;
            fileStatus.classList.add("h3-vc-error");
            fileStatus.textContent = `上传失败：${error?.message || error}`;
        }
    }

    listen(stage, "pointerdown", event => {
        splitDragging = true;
        stage.setPointerCapture?.(event.pointerId);
        const rect = stage.getBoundingClientRect();
        if (rect.width) setSplit((event.clientX - rect.left) / rect.width, true);
    });
    listen(stage, "pointermove", event => {
        if (!splitDragging) return;
        const rect = stage.getBoundingClientRect();
        if (rect.width) setSplit((event.clientX - rect.left) / rect.width, true);
    });
    listen(stage, "pointerup", event => {
        splitDragging = false;
        stage.releasePointerCapture?.(event.pointerId);
    });
    listen(stage, "pointercancel", () => { splitDragging = false; });
    listen(stage, "wheel", event => {
        if (!overlay) return;
        event.preventDefault();
        const rect = stage.getBoundingClientRect();
        const x = rect.width ? (event.clientX - rect.left) / rect.width * 100 : 50;
        const y = rect.height ? (event.clientY - rect.top) / rect.height * 100 : 50;
        setZoom(zoom * (event.deltaY < 0 ? 1.12 : 1 / 1.12), x, y);
    }, { passive: false });
    listen(grip, "keydown", event => {
        let next = splitPosition;
        if (event.key === "ArrowLeft") next -= 0.01;
        else if (event.key === "ArrowRight") next += 0.01;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = 1;
        else return;
        event.preventDefault();
        setSplit(next, true);
    });
    listen(timeline, "input", () => seek(timeline.value));
    listen(play, "click", () => before.paused ? startPlayback() : pause());
    listen(restart, "click", () => {
        const resume = !before.paused;
        seek(0);
        if (resume) void startPlayback();
    });
    listen(mute, "click", () => {
        const next = !before.muted;
        before.muted = next;
        writeValue("muted", next);
        applySettings();
    });
    listen(loop, "click", () => {
        writeValue("loop", !Boolean(value("loop", true)));
        applySettings();
    });
    listen(beforeLabelInput, "input", () => {
        writeValue("before_label", beforeLabelInput.value);
        applySettings();
    });
    listen(afterLabelInput, "input", () => {
        writeValue("after_label", afterLabelInput.value);
        applySettings();
    });
    listen(showLabelsInput, "change", () => {
        writeValue("show_labels", showLabelsInput.checked);
        applySettings();
    });
    listen(recordDurationInput, "change", () => {
        writeValue("record_duration", Number(recordDurationInput.value));
    });
    listen(fpsInput, "change", () => {
        writeValue("fps", Number(fpsInput.value));
    });
    listen(record, "click", () => recorder ? stopRecording() : startRecording());
    listen(fullscreen, "click", () => overlay ? closeFullscreen() : openFullscreen());
    listen(chooseBefore, "click", () => beforePicker.click());
    listen(chooseAfter, "click", () => afterPicker.click());
    listen(beforePicker, "change", () => upload(beforePicker.files?.[0], "before"));
    listen(afterPicker, "change", () => upload(afterPicker.files?.[0], "after"));
    listen(before, "loadedmetadata", updateDuration);
    listen(after, "loadedmetadata", updateDuration);
    listen(before, "ended", () => {
        if (value("loop", true)) {
            seek(0);
            void startPlayback();
        } else {
            pause();
        }
    });
    listen(document, "fullscreenchange", () => {
        if (overlay && document.fullscreenElement !== overlay) closeFullscreen(false);
    });
    for (const player of [before, after]) {
        listen(player, "error", () => {
            placeholder.textContent = "视频读取失败，请检查文件格式或 ComfyUI 控制台";
            placeholder.hidden = false;
        });
    }

    applySettings();
    return {
        root,
        applySettings,
        previewSelected,
        load,
        destroy() {
            destroyed = true;
            closeFullscreen();
            if (recorder) stopRecording();
            pause();
            clearPlayer(before);
            clearPlayer(after);
            for (const url of temporaryUrls) URL.revokeObjectURL(url);
            temporaryUrls.clear();
            lifetime.abort();
        },
    };
}

try {
    for (const [id, path] of [
        ["h3lvm-styles", "./h3lvm_picker.css"],
        ["h3-videocompare-styles", "./video_compare.css"],
    ]) {
        if (document.getElementById(id)) continue;
        const link = document.createElement("link");
        link.id = id;
        link.rel = "stylesheet";
        link.href = new URL(path, import.meta.url).href;
        document.head.appendChild(link);
    }
} catch (error) {
    console.warn("[H3 Video Compare] CSS injection failed:", error);
}

app.registerExtension({
    name: "H3.LongVideoManager.VideoCompare",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) return;
        const originalCreate = nodeType.prototype.onNodeCreated;
        const originalConfigure = nodeType.prototype.onConfigure;
        const originalExecuted = nodeType.prototype.onExecuted;
        const originalRemoved = nodeType.prototype.onRemoved;

        nodeType.prototype.onNodeCreated = function () {
            const result = originalCreate?.apply(this, arguments);
            this.serialize_widgets = true;
            this.size = [
                Math.max(620, this.size?.[0] || 0),
                Math.max(620, this.size?.[1] || 0),
            ];
            const view = createCompareView(this);
            this._h3VideoCompare = view;
            addPanel(this, "h3_video_compare_panel", view.root, PANEL_MIN_HEIGHT);
            for (const item of this.widgets || []) {
                if (LABELS[item.name]) {
                    item.label = LABELS[item.name];
                    item.options = item.options || {};
                    item.options.hidden = true;
                    item.serialize = true;
                }
                if (item.name === "before_selected" || item.name === "after_selected") {
                    item.options = item.options || {};
                    item.options.hidden = true;
                    item.serialize = true;
                    continue;
                }
                const callback = item.callback;
                item.callback = function () {
                    const callbackResult = callback?.apply(this, arguments);
                    view.applySettings();
                    return callbackResult;
                };
            }
            return result;
        };

        nodeType.prototype.onConfigure = function () {
            const result = originalConfigure?.apply(this, arguments);
            this._h3VideoCompare?.applySettings();
            this._h3VideoCompare?.previewSelected();
            return result;
        };

        nodeType.prototype.onExecuted = function (message) {
            const result = originalExecuted?.apply(this, arguments);
            const output = message?.output || message?.ui || message || {};
            this._h3VideoCompare?.load(
                output.h3_video_compare || [],
                output.h3_video_compare_settings || {},
            );
            return result;
        };

        nodeType.prototype.onRemoved = function () {
            this._h3VideoCompare?.destroy();
            this._h3VideoCompare = null;
            return originalRemoved?.apply(this, arguments);
        };
    },
});
