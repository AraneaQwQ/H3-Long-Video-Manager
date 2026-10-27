const METRICS = {
    rowHeight: 30,
    titleHeight: 26,
    sectionBorder: 2,
    fieldsPadding: 6,
    sectionGap: 8,
    panelBottom: 8,
    panelBorder: 1,
    panelMargin: 8,
};

export function parameterPanelMinHeight(sections) {
    const sectionCount = sections.length;
    const fieldCount = sections.reduce((total, section) => total + section.fields.length, 0);
    const sectionHeight = METRICS.titleHeight + METRICS.sectionBorder + METRICS.fieldsPadding;
    return sectionCount * sectionHeight
        + fieldCount * METRICS.rowHeight
        + Math.max(0, sectionCount - 1) * METRICS.sectionGap
        + METRICS.panelBottom
        + METRICS.panelBorder
        + METRICS.panelMargin;
}

export function fieldIsEnabled(field, values) {
    if (!field.enabledWhen) return true;
    return values[field.enabledWhen.field] === field.enabledWhen.equals;
}

export function normalizeNumericValue(field, value, fallback) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return fallback;
    const step = Number(field.step) || 1;
    const stepped = Math.round(numeric / step) * step;
    const clamped = Math.min(field.max, Math.max(field.min, stepped));
    return Number(clamped.toFixed(6));
}

export function presetNumberChoice(field, value) {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) {
        const preset = (field.presets ?? []).find(option => Number(option) === numeric);
        if (preset !== undefined) return String(preset);
    }
    return "custom";
}

function widgetFor(node, name) {
    return node.widgets?.find(widget => widget.name === name);
}

export function hideParameterWidgets(node, sections, storageOnly = []) {
    for (const section of sections) {
        for (const field of section.fields) {
            const widget = widgetFor(node, field.name);
            if (widget?.options) widget.options.hidden = true;
        }
    }
    for (const name of storageOnly) {
        const widget = widgetFor(node, name);
        if (widget?.options) widget.options.hidden = true;
    }
}

function widgetIsConnected(node, name) {
    return (node.inputs ?? []).some(input => input.link != null
        && (input.name === name || input.widget?.name === name));
}

function comboValues(widget, field, optionLabels) {
    const configured = widget.options?.values;
    const values = Array.isArray(configured)
        ? [...configured]
        : Object.keys(optionLabels[field.name] ?? {});
    if (!values.length || widget.value == null) return values;
    if (!values.some(value => String(value) === String(widget.value))) values.push(widget.value);
    return values;
}

function decimalPlaces(step) {
    const text = String(step ?? 1);
    return (text.split(".")[1] ?? "").length;
}

export function createParameterPanel(node, {
    sections,
    labels,
    tooltips,
    optionLabels,
    signal,
}) {
    const element = document.createElement("div");
    element.className = "h3lvm-parameter-panel";
    const records = [];
    const managedWidgets = [];

    sections.forEach((section, sectionIndex) => {
        const sectionElement = document.createElement("section");
        sectionElement.className = "h3lvm-parameter-section";
        sectionElement.dataset.section = section.id;

        const title = document.createElement("div");
        title.className = "h3lvm-parameter-title";
        const index = document.createElement("span");
        index.className = "h3lvm-parameter-index";
        index.textContent = String(sectionIndex + 1).padStart(2, "0");
        const titleText = document.createElement("span");
        titleText.textContent = section.title;
        title.append(index, titleText);
        sectionElement.appendChild(title);

        const fieldsElement = document.createElement("div");
        fieldsElement.className = "h3lvm-parameter-fields";
        for (const field of section.fields) {
            const widget = widgetFor(node, field.name);
            if (!widget) continue;
            managedWidgets.push(widget);

            const row = document.createElement("label");
            row.className = "h3lvm-parameter-field";
            row.dataset.field = field.name;
            row.title = tooltips[field.name] ?? "";

            const label = document.createElement("span");
            label.className = "h3lvm-parameter-label";
            const labelText = document.createElement("span");
            labelText.textContent = labels[field.name] ?? field.name;
            const note = document.createElement("span");
            note.className = "h3lvm-parameter-note";
            label.append(labelText, note);

            let control;
            let presetControls = null;
            if (field.type === "presetNumber") {
                control = document.createElement("div");
                control.className = "h3lvm-parameter-preset-number";
                const select = document.createElement("select");
                select.className = "h3lvm-parameter-select";
                for (const value of field.presets ?? []) {
                    const option = document.createElement("option");
                    option.value = String(value);
                    option.textContent = Number(value) === 100 ? "100%（原始）" : `${value}%`;
                    select.appendChild(option);
                }
                const customOption = document.createElement("option");
                customOption.value = "custom";
                customOption.textContent = "custom";
                select.appendChild(customOption);

                const number = document.createElement("input");
                number.type = "number";
                number.className = "h3lvm-parameter-number";
                number.min = String(field.min);
                number.max = String(field.max);
                number.step = String(field.step);
                number.title = "custom：自定义缩放百分比";
                control.append(select, number);
                presetControls = { select, number, customSelected: false };

                select.addEventListener("change", () => {
                    presetControls.customSelected = select.value === "custom";
                    if (presetControls.customSelected) {
                        refresh();
                        number.focus();
                    } else {
                        updateWidget(widget, Number(select.value));
                    }
                }, { signal });
                number.addEventListener("change", () => {
                    const next = normalizeNumericValue(field, number.value, widget.value);
                    updateWidget(widget, next);
                }, { signal });
                number.addEventListener("keydown", event => {
                    if (event.key === "Enter") number.blur();
                }, { signal });
            } else if (field.type === "combo") {
                control = document.createElement("select");
                control.className = "h3lvm-parameter-select";
                for (const value of comboValues(widget, field, optionLabels)) {
                    const option = document.createElement("option");
                    option.value = String(value);
                    option.textContent = optionLabels[field.name]?.[String(value)]
                        ?? widget.options?.getOptionLabel?.(value)
                        ?? String(value);
                    control.appendChild(option);
                }
                control.addEventListener("change", () => {
                    updateWidget(widget, control.value);
                }, { signal });
            } else if (field.type === "boolean") {
                control = document.createElement("button");
                control.type = "button";
                control.className = "h3lvm-parameter-switch";
                control.setAttribute("role", "switch");
                const track = document.createElement("span");
                track.className = "h3lvm-parameter-track";
                const thumb = document.createElement("span");
                thumb.className = "h3lvm-parameter-thumb";
                track.appendChild(thumb);
                const state = document.createElement("span");
                state.className = "h3lvm-parameter-switch-text";
                control.append(track, state);
                control.addEventListener("click", () => {
                    updateWidget(widget, !Boolean(widget.value));
                }, { signal });
            } else {
                control = document.createElement("input");
                control.type = "number";
                control.className = "h3lvm-parameter-number";
                control.min = String(field.min);
                control.max = String(field.max);
                control.step = String(field.step);
                control.addEventListener("change", () => {
                    const next = normalizeNumericValue(field, control.value, widget.value);
                    updateWidget(widget, next);
                }, { signal });
                control.addEventListener("keydown", event => {
                    if (event.key === "Enter") control.blur();
                }, { signal });
            }

            row.append(label, control);
            fieldsElement.appendChild(row);
            records.push({ field, widget, row, control, note, presetControls });
        }
        sectionElement.appendChild(fieldsElement);
        element.appendChild(sectionElement);
    });

    function refresh() {
        const values = Object.fromEntries(records.map(record => [record.field.name, record.widget.value]));
        for (const record of records) {
            const { field, widget, row, control, note, presetControls } = record;
            const connected = widgetIsConnected(node, field.name);
            const enabled = fieldIsEnabled(field, values) && !connected;
            row.classList.toggle("is-disabled", !enabled);
            if (presetControls) {
                const choice = presetControls.customSelected
                    ? "custom"
                    : presetNumberChoice(field, widget.value);
                presetControls.select.disabled = !enabled;
                presetControls.number.disabled = !enabled || choice !== "custom";
            } else {
                control.disabled = !enabled;
            }
            note.textContent = connected ? "上游控制" : enabled ? "" : field.disabledNote ?? "";

            if (presetControls) {
                const choice = presetControls.customSelected
                    ? "custom"
                    : presetNumberChoice(field, widget.value);
                if (document.activeElement !== presetControls.select) {
                    presetControls.select.value = choice;
                }
                if (document.activeElement !== presetControls.number) {
                    const numeric = Number(widget.value);
                    presetControls.number.value = Number.isFinite(numeric)
                        ? numeric.toFixed(decimalPlaces(field.step))
                        : String(widget.value ?? "");
                }
            } else if (field.type === "boolean") {
                const checked = Boolean(widget.value);
                control.setAttribute("aria-checked", String(checked));
                control.classList.toggle("is-on", checked);
                control.querySelector(".h3lvm-parameter-switch-text").textContent = checked ? "开启" : "关闭";
            } else if (document.activeElement !== control) {
                if (field.type === "combo") {
                    control.value = String(widget.value ?? "");
                } else {
                    const numeric = Number(widget.value);
                    control.value = Number.isFinite(numeric)
                        ? numeric.toFixed(decimalPlaces(field.step))
                        : String(widget.value ?? "");
                }
            }
        }
    }

    function updateWidget(widget, value) {
        widget.value = value;
        widget.callback?.(value);
        node.setDirtyCanvas?.(true, true);
        refresh();
    }

    for (const widget of new Set(managedWidgets)) {
        const originalCallback = widget.callback;
        widget.callback = function (value) {
            const result = originalCallback?.apply(this, arguments);
            refresh();
            return result;
        };
    }

    refresh();
    return {
        element,
        minHeight: parameterPanelMinHeight(sections),
        refresh,
    };
}
