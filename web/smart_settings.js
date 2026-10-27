export const SMART_SPLIT_SETTINGS_SECTIONS = [
    {
        id: "source",
        title: "视频输入与慢放",
        fields: [
            { name: "fps", type: "integer", min: 1, max: 240, step: 1 },
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
        ],
    },
    {
        id: "segments",
        title: "镜头检测与分段",
        fields: [
            { name: "detection_sensitivity", type: "combo" },
            { name: "motion_context_frames", type: "combo" },
        ],
    },
    {
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
    },
    {
        id: "output",
        title: "输出与保存",
        fields: [
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
        ],
    },
];
