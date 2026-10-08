// RAFOLIE 2026-10-03: the visual panel of the H3 Long Video Manager node.
//
// What it is for: the node saves every segment it cuts into a project bin, and the
// user picks from that bin. The card deck itself lives in deck_panel.js because the
// Smart Split node writes into the same bin and shows the same cards; this file is
// the Manager-specific part: the project menu and the wording.
//
// It reuses the Segment Picker look on purpose (same container, project row,
// toolbar, card grid, footer) - one plugin, one visual language. The shared pieces
// are project_menu.js, deck_panel.js and h3lvm_picker.css.
//
// Display only. No new node inputs and no new saved workflow fields.

import { addPanel } from "./dom_panel.js";
import { createProjectMenu } from "./project_menu.js";
import { createDeck } from "./deck_panel.js";

const PROJECT_FIELD = "project_name";
const SEGMENT_FIELD = "segment_id";

// Panel height in canvas pixels: project menu + tool row + one card row + the legend.
// The deck is always visible, so this doubles as the widget's minimum height. LiteGraph
// adds it to the parameter rows and grows any node too short to show a card, which is
// also why there is no expand/collapse button and no manual resizing here.
const PANEL_H = 320;

export function installManagerPanel(node) {
    const lifetime = node._h3lvmManagerLifetime ?? new AbortController();
    node._h3lvmManagerLifetime = lifetime;
    const signal = lifetime.signal;

    const container = document.createElement("div");
    container.className = "h3lvm-container";

    function widgetFor(name) {
        return node.widgets?.find(item => item.name === name);
    }

    const deck = createDeck({
        node,
        signal,
        container,
        projectField: PROJECT_FIELD,
        segmentField: SEGMENT_FIELD,
        footerLines: [
            "👉 点卡片＝切换输出片段编号 · ▶＝预览 · 删除片段与卡片大小在「H3 Segment Picker」",
        ],
        onRefresh: () => void menu.refresh(),
    });

    // --- Project menu (same row as the Picker) ---
    const menu = createProjectMenu({
        node,
        widget: widgetFor(PROJECT_FIELD),
        signal,
        onChange: () => void deck.render(),
    });
    container.insertBefore(menu.element, deck.toolbar);
    node._h3lvmRefreshProjects = menu.refresh;

    addPanel(node, "h3lvm_manager_panel", container, PANEL_H);

    // The deck belongs to the bin, not to this page visit: opening the workflow again
    // shows the cards right away. The project name is only restored in configure(),
    // which runs after onNodeCreated, so h3lvm_manager.js calls this hook once the
    // widgets hold their saved values.
    node._h3lvmDeckRefresh = deck.render;

    void deck.render();
}