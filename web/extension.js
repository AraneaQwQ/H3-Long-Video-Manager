// H3 Long Video Manager — Web Extension
// Panels and pickers live in the other .js files; this file migrates the
// "H3 Long Video Manager" widget layout saved by older plugin versions.
//
// Why: ComfyUI restores a workflow's widgets_values BY POSITION, and the
// Manager's tail fields changed order between releases (person_crop /
// person_crop_expand_percent / save_dtype were shuffled when final_align was
// introduced). A workflow saved by an old version lands its values on the
// wrong widgets (e.g. "int8" on the INT person_crop_expand_percent), which the
// frontend flags as "无效输入". The migration below rebuilds the mapping from
// what each value IS, not where it sits, so every shipped layout loads clean.

import { app } from "../../scripts/app.js";

const MANAGER_TYPE = "H3 Long Video Manager";

// Widget order of the current backend schema, sockets excluded.
const WIDGET_ORDER = [
    "fps", "segment_duration", "motion_context_frames", "segment_id",
    "scale_percent", "align_to_h3_grid", "project_name", "save_enabled",
    "save_preview_mp4", "final_align", "person_crop", "person_crop_expand_percent",
    "save_dtype", "playback_speed", "playback_speed_custom",
];

// The first 9 widgets never moved across shipped versions, so their values
// stay positional. Everything after them is remapped by signature below.
const HEAD_COUNT = 9;

// Tail widgets, in schema order, with a recognizer and the schema default.
// Values are consumed in order: the first still-unassigned field whose
// recognizer accepts a value takes it, so a real layout can never leapfrog
// a field it cannot belong to.
const TAIL_FIELDS = [
    { name: "final_align", def: "down",
      match: (v) => v === "down" || v === "up" },
    { name: "person_crop", def: false,
      match: (v) => typeof v === "boolean" },
    { name: "person_crop_expand_percent", def: 0,
      match: (v) => typeof v === "number" && Number.isFinite(v) },
    { name: "save_dtype", def: "int8",
      match: (v) => v === "int8" || v === "fp16" },
    { name: "playback_speed", def: "1.0x",
      match: (v) => v === "1.0x" || v === "0.75x" || v === "0.5x" || v === "custom" },
    { name: "playback_speed_custom", def: 1.0,
      match: (v) => typeof v === "number" && Number.isFinite(v) },
];

function remapManagerValues(values) {
    const mapped = new Map();
    values.slice(0, HEAD_COUNT).forEach((value, index) => {
        if (index < WIDGET_ORDER.length) mapped.set(WIDGET_ORDER[index], value);
    });

    const assigned = new Map();
    let dropped = 0;
    for (const value of values.slice(HEAD_COUNT)) {
        const field = TAIL_FIELDS.find(
            (f) => !assigned.has(f.name) && f.match(value));
        if (field) {
            assigned.set(field.name, value);
        } else {
            dropped += 1;
        }
    }
    for (const field of TAIL_FIELDS) {
        mapped.set(field.name, assigned.has(field.name) ? assigned.get(field.name) : field.def);
    }
    return { mapped, dropped };
}

function applyManagerWidgets(node, mapped) {
    const byName = new Map();
    for (const widget of node.widgets ?? []) byName.set(widget.name, widget);
    for (const [name, value] of mapped) {
        const widget = byName.get(name);
        if (widget) widget.value = value;
    }
}

app.registerExtension({
    name: "H3.LongVideoManager",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== MANAGER_TYPE) return;
        // configure() applies widgets_values before onConfigure runs, so the
        // chained hook below sees the (possibly misaligned) values already on
        // the widgets and simply writes the corrected ones back, by name.
        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            const result = originalOnConfigure?.apply(this, arguments);
            try {
                const values = info?.widgets_values;
                if (Array.isArray(values) && values.length < WIDGET_ORDER.length) {
                    // Layouts that already line up (a plain 13-value workflow,
                    // a bare 9-value one) are left untouched; only a value that
                    // cannot belong to the widget it landed on triggers the
                    // remap.
                    const tail = values.slice(HEAD_COUNT);
                    const aligned = tail.every(
                        (value, index) => TAIL_FIELDS[index] && TAIL_FIELDS[index].match(value));
                    if (!aligned) {
                        const { mapped, dropped } = remapManagerValues(values);
                        applyManagerWidgets(this, mapped);
                        console.info("[H3 LVM] restored legacy widget layout for " +
                            MANAGER_TYPE + " (" + values.length + " values" +
                            (dropped ? ", " + dropped + " unrecognized" : "") + ")");
                    }
                }
            } catch (err) {
                console.warn("[H3 LVM] legacy widget migration failed:", err);
            }
            return result;
        };
    },
});
