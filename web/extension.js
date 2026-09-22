// H3 Long Video Manager — Web Extension (stub)
// Phase 11+ will implement the full UI with segment cards, timeline, etc.
// This stub registers the extension to ensure ComfyUI doesn't error on load.

import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "H3.LongVideoManager",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === "H3 Long Video Manager") {
            // Add a help tooltip
            nodeType.prototype.onNodeCreated = function () {
                this.addTitle("H3 Long Video Manager");
            };
        }
    },
});
