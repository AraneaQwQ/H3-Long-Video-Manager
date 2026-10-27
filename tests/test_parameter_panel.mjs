import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

async function importSource(relativePath) {
    const source = await readFile(path.join(repo, relativePath), "utf8");
    return import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
}

const { MANAGER_SETTINGS_SECTIONS } = await importSource("web/manager_settings.js");
const { SMART_SPLIT_SETTINGS_SECTIONS } = await importSource("web/smart_settings.js");
const {
    MANAGER_V2_SETTINGS_SECTIONS,
    SMART_V2_SETTINGS_SECTIONS,
} = await importSource("web/v2_settings.js");
const {
    fieldIsEnabled,
    hideParameterWidgets,
    normalizeNumericValue,
    parameterPanelMinHeight,
    presetNumberChoice,
} = await importSource("web/parameter_panel.js");

test("manager parameters are grouped by their task", () => {
    assert.deepEqual(
        MANAGER_SETTINGS_SECTIONS.map(section => [
            section.title,
            section.fields.map(field => field.name),
        ]),
        [
            ["视频输入与慢放", ["fps", "playback_speed", "playback_speed_custom"]],
            ["分段规则", ["segment_duration", "motion_context_frames", "align_to_h3_grid"]],
            ["画面处理", ["scale_percent", "person_crop", "person_crop_expand_percent"]],
            ["输出与保存", ["save_enabled", "save_preview_mp4", "save_dtype"]],
        ],
    );
});

test("every managed field appears once and storage-only fields stay outside", () => {
    const names = MANAGER_SETTINGS_SECTIONS.flatMap(section => section.fields.map(field => field.name));
    assert.equal(new Set(names).size, names.length);
    assert.equal(names.length, 12);
    assert.equal(names.includes("segment_id"), false);
    assert.equal(names.includes("project_name"), false);
    assert.equal(names.includes("final_align"), false);
});

test("smart and v2 presets contain only their own node parameters", () => {
    assert.deepEqual(
        SMART_SPLIT_SETTINGS_SECTIONS.map(section => section.fields.map(field => field.name)),
        [
            ["fps", "playback_speed", "playback_speed_custom"],
            ["detection_sensitivity", "motion_context_frames"],
            ["scale_percent"],
            ["save_enabled", "save_preview_mp4", "save_dtype"],
        ],
    );
    assert.deepEqual(
        MANAGER_V2_SETTINGS_SECTIONS.map(section => section.fields.map(field => field.name)),
        [
            ["playback_speed", "playback_speed_custom"],
            ["segment_duration", "motion_context_frames", "align_to_h3_grid"],
            ["scale_percent"],
            ["save_enabled", "save_preview_mp4", "save_dtype"],
        ],
    );
    assert.deepEqual(
        SMART_V2_SETTINGS_SECTIONS.map(section => section.fields.map(field => field.name)),
        [
            ["playback_speed", "playback_speed_custom"],
            ["detection_sensitivity", "motion_context_frames"],
            ["scale_percent"],
            ["save_enabled", "save_preview_mp4", "save_dtype"],
        ],
    );
});

test("hiding canvas controls never reorders the native widget array", () => {
    const widgets = [
        { name: "fps", options: {} },
        { name: "segment_duration", options: {} },
        { name: "project_name", options: {} },
        { name: "playback_speed", options: {} },
        { name: "playback_speed_custom", options: {} },
        { name: "segment_id", options: {} },
    ];
    const node = { widgets };
    const before = widgets.map(widget => widget.name);
    hideParameterWidgets(node, MANAGER_SETTINGS_SECTIONS, ["segment_id"]);
    assert.deepEqual(widgets.map(widget => widget.name), before);
    assert.equal(widgets[0].options.hidden, true);
    assert.equal(widgets[1].options.hidden, true);
    assert.equal(widgets[2].options.hidden, undefined);
    assert.equal(widgets[3].options.hidden, true);
    assert.equal(widgets[4].options.hidden, true);
    assert.equal(widgets[5].options.hidden, true);
});

test("dependent controls only enable with their parent setting", () => {
    const custom = MANAGER_SETTINGS_SECTIONS[0].fields[2];
    assert.equal(fieldIsEnabled(custom, { playback_speed: "1.0x" }), false);
    assert.equal(fieldIsEnabled(custom, { playback_speed: "custom" }), true);

    const expand = MANAGER_SETTINGS_SECTIONS[2].fields[2];
    assert.equal(fieldIsEnabled(expand, { person_crop: false }), false);
    assert.equal(fieldIsEnabled(expand, { person_crop: true }), true);

    for (const field of MANAGER_SETTINGS_SECTIONS[3].fields.slice(2)) {
        assert.equal(fieldIsEnabled(field, { save_enabled: false }), false);
        assert.equal(fieldIsEnabled(field, { save_enabled: true }), true);
    }
});

test("numeric controls clamp and use their declared steps", () => {
    const custom = MANAGER_SETTINGS_SECTIONS[0].fields[2];
    assert.equal(normalizeNumericValue(custom, "0.64", 1), 0.6);
    assert.equal(normalizeNumericValue(custom, "0", 1), 0.1);
    assert.equal(normalizeNumericValue(custom, "4", 1), 1);
    assert.equal(normalizeNumericValue(custom, "invalid", 0.8), 0.8);

    const fps = MANAGER_SETTINGS_SECTIONS[0].fields[0];
    assert.equal(normalizeNumericValue(fps, "23.6", 24), 24);
});

test("scale presets and custom keep using the existing scale_percent value", () => {
    const sections = [
        MANAGER_SETTINGS_SECTIONS,
        SMART_SPLIT_SETTINGS_SECTIONS,
        MANAGER_V2_SETTINGS_SECTIONS,
        SMART_V2_SETTINGS_SECTIONS,
    ];
    for (const sectionSet of sections) {
        const scale = sectionSet.flatMap(section => section.fields)
            .find(field => field.name === "scale_percent");
        assert.equal(scale.type, "presetNumber");
        assert.deepEqual(scale.presets, [100, 75, 50, 25]);
        assert.equal(presetNumberChoice(scale, 100), "100");
        assert.equal(presetNumberChoice(scale, "75"), "75");
        assert.equal(presetNumberChoice(scale, 63), "custom");
        assert.equal(presetNumberChoice(scale, "invalid"), "custom");
        assert.equal(normalizeNumericValue(scale, "63.4", 100), 63);
        assert.equal(normalizeNumericValue(scale, "0", 100), 10);
        assert.equal(normalizeNumericValue(scale, "120", 100), 100);
    }
});

test("panel minimum height includes every section and field", () => {
    const height = parameterPanelMinHeight(MANAGER_SETTINGS_SECTIONS);
    assert.equal(height, 537);
    assert.ok(height > 12 * 30);
});
