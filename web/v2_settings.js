const SPEED_FIELDS = [
    { name: "playback_speed", type: "combo" },
    {
        name: "playback_speed_custom",
        type: "number",
        min: 0.1,
        max: 1,
        step: 0.1,
        enabledWhen: { field: "playback_speed", equals: "custom" },
        disabledNote: "仅 custom",
    },
];

const OUTPUT_FIELDS = [
    { name: "save_enabled", type: "boolean" },
    {
        name: "save_preview_mp4",
        type: "boolean",
        enabledWhen: { field: "save_enabled", equals: true },
        disabledNote: "先开启保存",
    },
    {
        name: "save_dtype",
        type: "combo",
        enabledWhen: { field: "save_enabled", equals: true },
        disabledNote: "先开启保存",
    },
];

const IMAGE_SECTION = {
    id: "image",
    title: "画面处理",
    fields: [
        {
            name: "scale_percent",
            type: "presetNumber",
            presets: [100, 75, 50, 25],
            min: 10,
            max: 100,
            step: 1,
        },
    ],
};

export const MANAGER_V2_SETTINGS_SECTIONS = [
    { id: "source", title: "视频输入与慢放", fields: SPEED_FIELDS },
    {
        id: "segments",
        title: "分段规则",
        fields: [
            { name: "segment_duration", type: "number", min: 0.5, max: 120, step: 0.001 },
            { name: "motion_context_frames", type: "combo" },
            { name: "align_to_h3_grid", type: "boolean" },
        ],
    },
    IMAGE_SECTION,
    { id: "output", title: "输出与保存", fields: OUTPUT_FIELDS },
];

export const SMART_V2_SETTINGS_SECTIONS = [
    { id: "source", title: "视频输入与慢放", fields: SPEED_FIELDS },
    {
        id: "segments",
        title: "镜头检测与分段",
        fields: [
            { name: "detection_sensitivity", type: "combo" },
            { name: "motion_context_frames", type: "combo" },
        ],
    },
    IMAGE_SECTION,
    { id: "output", title: "输出与保存", fields: OUTPUT_FIELDS },
];
