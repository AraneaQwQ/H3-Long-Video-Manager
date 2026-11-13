import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
// The repo has no package.json; import this pure ES module as a data URL.
const source = readFileSync(new URL("../web/guide_state.js", import.meta.url), "utf8");
const { parseDocument, serializeDocument, normalizeRelease } = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
assert.equal(JSON.parse(serializeDocument(parseDocument("{}"))).keyframe_release, undefined);
const config = { enabled: true, threshold: 0.9 };
const doc = parseDocument(JSON.stringify({ guides: [], keyframe_release: config }));
assert.deepEqual(JSON.parse(serializeDocument(doc)).keyframe_release, config);
doc.view_state.zoom = 2;
assert.deepEqual(JSON.parse(serializeDocument(doc)).keyframe_release, config);
for (const threshold of [0, 0.9, 1]) assert.equal(normalizeRelease({ enabled: true, threshold }).threshold, threshold);
for (const threshold of [null, true, "", -1, 2, Infinity, NaN]) assert.throws(() => normalizeRelease({ threshold }));
assert.throws(() => normalizeRelease({ enabled: "true" }));
console.log("Guide release document: 14 assertions passed");
