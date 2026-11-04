import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const sourcePath = new URL("../../web/video_compare.js", import.meta.url);

class FakeEventTarget {
    constructor() {
        this.listeners = new Map();
    }

    addEventListener(type, handler) {
        const handlers = this.listeners.get(type) || [];
        handlers.push(handler);
        this.listeners.set(type, handlers);
    }

    fire(type, event = {}) {
        for (const handler of this.listeners.get(type) || []) {
            handler({ target: this, ...event });
        }
    }
}

class FakeElement extends FakeEventTarget {
    constructor(tagName) {
        super();
        this.tagName = tagName;
        this.style = {};
        this.children = [];
        this.classList = { add() {}, remove() {} };
        this.value = "";
        this.textContent = "";
        this.hidden = false;
        this.disabled = false;
        this.attributes = {};
    }

    setAttribute(name, value) { this.attributes[name] = String(value); }
    getAttribute(name) { return this.attributes[name]; }

    appendChild(child) {
        this.children.push(child);
        return child;
    }

    append(...children) {
        this.children.push(...children);
    }

    replaceChildren(...children) {
        this.children = children;
    }

    remove() {}
    load() {}
    click() { this.fire("click"); }
    removeAttribute(name) { if (name === "src") this.src = ""; }
}

class FakeVideo extends FakeElement {
    constructor() {
        super("video");
        this.paused = true;
        this.currentTime = 0;
        this.duration = 0;
        this.readyState = 2;
        this.videoWidth = 64;
        this.videoHeight = 36;
        this.playbackRate = 1;
        this.src = "";
    }

    play() {
        this.paused = false;
        return Promise.resolve();
    }

    pause() {
        this.paused = true;
    }
}

function fakeContext() {
    return {
        drawImage() {}, fillRect() {}, save() {}, beginPath() {}, rect() {},
        clip() {}, restore() {}, moveTo() {}, lineTo() {}, stroke() {}, fillText() {},
        measureText(text) { return { width: String(text).length * 10 }; },
    };
}

async function fixture({ recording = false } = {}) {
    const elements = [];
    const videos = [];
    const streams = [];
    const document = new FakeEventTarget();
    document.activeElement = null;
    document.fullscreenElement = null;
    document.head = new FakeElement("head");
    document.body = new FakeElement("body");
    document.getElementById = () => ({});
    document.createElement = tag => {
        let item;
        if (tag === "video") {
            item = new FakeVideo();
            videos.push(item);
        } else if (tag === "canvas" && recording) {
            item = new FakeElement("canvas");
            item.getContext = () => fakeContext();
            item.captureStream = () => {
                const stream = {
                    tracks: [{ stopped: false, stop() { this.stopped = true; } }],
                    getTracks() { return this.tracks; },
                };
                streams.push(stream);
                return stream;
            };
        } else {
            item = new FakeElement(tag);
        }
        elements.push(item);
        return item;
    };

    class FakeMediaRecorder extends FakeEventTarget {
        static isTypeSupported() { return true; }

        constructor(stream, options) {
            super();
            this.stream = stream;
            this.options = options;
            this.state = "inactive";
        }

        start() { this.state = "recording"; }

        stop() {
            this.state = "inactive";
            queueMicrotask(() => this.onstop?.());
        }
    }

    const context = {
        AbortController,
        Blob,
        console,
        document,
        FormData,
        MediaRecorder: FakeMediaRecorder,
        performance,
        queueMicrotask,
        setTimeout,
        clearTimeout,
        setInterval,
        clearInterval,
        requestAnimationFrame: () => 1,
        cancelAnimationFrame() {},
        app: { registerExtension() {} },
        api: { apiURL: value => value, fetchApi: async () => { throw new Error("not expected"); } },
        addPanel() {},
        URL,
    };
    let source = await readFile(sourcePath, "utf8");
    source = source.replace(/^import .*;\r?\n/gm, "");
    source = source.replaceAll("import.meta.url", '"file:///video_compare.js"');
    source += "\nglobalThis.__createCompareView = createCompareView;";
    vm.runInNewContext(source, context);

    const values = {
        slider_position: 0.5, before_label: "A", after_label: "B", show_labels: true,
        loop: true, muted: true, record_duration: 5, fps: 24,
        before_selected: "", after_selected: "",
    };
    const node = {
        widgets: Object.entries(values).map(([name, value]) => ({ name, value, options: {} })),
        setDirtyCanvas() {},
    };
    const view = context.__createCompareView(node);
    view.load([
        { role: "before", path: "before.mp4", name: "before.mp4" },
        { role: "after", path: "after.mp4", name: "after.mp4" },
    ]);
    const [before, after] = videos;
    before.duration = 0.75;
    after.duration = 0.75;
    before.fire("loadedmetadata");
    after.fire("loadedmetadata");
    return { view, node, before, after, elements, streams };
}

test("loop mode seeks both videos and resumes after the before video ends", async () => {
    const { view, before, after } = await fixture();
    before.currentTime = 0.75;
    after.currentTime = 0.75;
    before.paused = true;
    after.paused = true;
    before.fire("ended");
    await Promise.resolve();
    assert.equal(before.currentTime, 0);
    assert.equal(after.currentTime, 0);
    assert.equal(before.paused, false);
    assert.equal(after.paused, false);
    view.destroy();
});

test("non-loop mode stays paused at the common end", async () => {
    const { view, node, before, after } = await fixture();
    node.widgets.find(item => item.name === "loop").value = false;
    before.currentTime = 0.75;
    after.currentTime = 0.75;
    before.paused = true;
    after.paused = true;
    before.fire("ended");
    assert.equal(before.currentTime, 0.75);
    assert.equal(after.currentTime, 0.75);
    assert.equal(before.paused, true);
    assert.equal(after.paused, true);
    view.destroy();
});

test("removing a node during recording stops every capture track", async () => {
    const { view, elements, streams } = await fixture({ recording: true });
    const record = elements.find(item => item.tagName === "button" && item.textContent === "● 录制对比视频");
    assert.ok(record);
    record.click();
    assert.equal(streams.length, 1);
    assert.equal(streams[0].tracks[0].stopped, false);
    view.destroy();
    await Promise.resolve();
    assert.equal(streams[0].tracks[0].stopped, true);
});

test("the stage and its keyboard grip share one split value without a duplicate slider", async () => {
    const { view, node, elements } = await fixture();
    assert.equal(elements.some(item => item.className === "h3-vc-split-row"), false);
    const stage = elements.find(item => item.className === "h3-vc-stage");
    stage.getBoundingClientRect = () => ({ left: 0, width: 200 });
    stage.fire("pointerdown", { clientX: 150, pointerId: 1 });
    stage.fire("pointerup", { pointerId: 1 });
    assert.equal(node.widgets.find(item => item.name === "slider_position").value, 0.75);
    const grip = elements.find(item => item.className === "h3-vc-grip");
    grip.fire("keydown", { key: "ArrowLeft", preventDefault() {} });
    assert.equal(node.widgets.find(item => item.name === "slider_position").value, 0.74);
    assert.equal(grip.getAttribute("aria-valuenow"), "74");
    view.destroy();
});

test("toolbar and detail settings stay bound to the serialized widgets", async () => {
    const { view, node, elements } = await fixture();
    const loop = elements.find(item => item.tagName === "button" && item.textContent === "🔁 循环");
    assert.equal(elements.find(item => item.className === "h3-vc-settings").open, true);
    assert.ok(loop.className.includes("h3lvm-refresh-btn"));
    loop.click();
    assert.equal(node.widgets.find(item => item.name === "loop").value, false);
    assert.equal(loop.getAttribute("aria-pressed"), "false");
    const label = elements.find(item => item.name === "before_label");
    label.value = "原始画面";
    label.fire("input");
    assert.equal(node.widgets.find(item => item.name === "before_label").value, "原始画面");
    assert.equal(elements.find(item => item.className === "h3-vc-tag h3-vc-before-tag").textContent, "原始画面");
    const visible = elements.find(item => item.name === "show_labels");
    visible.checked = false;
    visible.fire("change");
    assert.equal(node.widgets.find(item => item.name === "show_labels").value, false);
    assert.equal(elements.find(item => item.className === "h3-vc-tag h3-vc-before-tag").hidden, true);
    view.destroy();
});

test("fullscreen carries the playback toolbar and returns it to the node", async () => {
    const { view, elements } = await fixture();
    const fullscreen = elements.find(item => item.tagName === "button" && item.textContent === "⛶ 全屏");
    fullscreen.click();
    const overlay = elements.find(item => item.className === "h3-vc-overlay");
    const toolbar = elements.find(item => item.className === "h3-vc-toolbar");
    assert.ok(overlay.children.includes(toolbar));
    const close = elements.filter(item => item.tagName === "button" && item.textContent === "✕ 退出全屏").at(-1);
    close.click();
    const home = elements.find(item => item.className === "h3-vc-toolbar-home");
    assert.ok(home.children.includes(toolbar));
    view.destroy();
});
