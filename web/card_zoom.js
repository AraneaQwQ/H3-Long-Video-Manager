// RAFOLIE 2026-10-03: card zoom shared by the Segment Picker and the Manager panel.
// One control, one set of steps, so both panels scale cards the same way (100%-400%).
// The sizes are CSS custom properties on the panel container; the deck grid and the
// thumbnail box read them, so nothing here touches the node size - ComfyUI owns that.

const ZOOM_STEPS = [1, 1.5, 2, 3, 4]; // 100%, 150%, 200%, 300%, 400%
const BASE_CARD_MIN = 130; // px
const BASE_THUMB_H = 75;   // px

export function createCardZoom({ container, node }) {
    let stepIndex = 0;

    const sep = document.createElement("span");
    sep.className = "h3lvm-tool-sep";

    const label = document.createElement("span");
    label.className = "h3lvm-tool-label";
    label.textContent = "卡片大小";

    const percent = document.createElement("span");
    percent.className = "h3lvm-zoom-label";

    const zoomOut = document.createElement("button");
    zoomOut.className = "h3lvm-refresh-btn";
    zoomOut.textContent = "−";
    zoomOut.title = "缩小卡片";

    const zoomIn = document.createElement("button");
    zoomIn.className = "h3lvm-refresh-btn";
    zoomIn.textContent = "+";
    zoomIn.title = "放大卡片";

    function apply() {
        const zoom = ZOOM_STEPS[stepIndex];
        container.style.setProperty("--card-min", Math.round(BASE_CARD_MIN * zoom) + "px");
        container.style.setProperty("--thumb-h", Math.round(BASE_THUMB_H * zoom) + "px");
        percent.textContent = Math.round(zoom * 100) + "%";
        zoomOut.disabled = stepIndex === 0;
        zoomIn.disabled = stepIndex === ZOOM_STEPS.length - 1;
        node?.setDirtyCanvas?.(true, true);
    }

    zoomIn.onclick = (event) => {
        event.stopPropagation();
        if (stepIndex < ZOOM_STEPS.length - 1) {
            stepIndex++;
            apply();
        }
    };
    zoomOut.onclick = (event) => {
        event.stopPropagation();
        if (stepIndex > 0) {
            stepIndex--;
            apply();
        }
    };

    apply();

    return {
        mount(toolbar) {
            toolbar.append(sep, label, zoomOut, percent, zoomIn);
        },
    };
}
