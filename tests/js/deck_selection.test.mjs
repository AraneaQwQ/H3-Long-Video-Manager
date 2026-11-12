import assert from "node:assert/strict";
import test from "node:test";
import { adjacentSelection, toggleMergeSelection } from "../../web/deck_selection.js";

test("deleted card gaps do not prevent merging neighbours", () => {
    assert.deepEqual([...toggleMergeSelection([1], 3, [1, 3, 4])], [1, 3]);
    assert.deepEqual([...toggleMergeSelection([3], 1, [1, 3, 4])], [3, 1]);
    assert.equal(adjacentSelection([1, 3, 4], [1, 3, 4]), true);
});
test("an existing unselected card still prevents merging across it", () => {
    assert.equal(adjacentSelection([1, 3], [1, 2, 3]), false);
    assert.deepEqual([...toggleMergeSelection([1], 3, [1, 2, 3])], [3]);
});
test("deselecting the middle disables merge until the gap is selected again", () => {
    const picked = toggleMergeSelection([1, 3, 4], 3, [1, 3, 4]);
    assert.equal(adjacentSelection(picked, [1, 3, 4]), false);
    assert.equal(adjacentSelection(toggleMergeSelection(picked, 3, [1, 3, 4]), [1, 3, 4]), true);
});
test("stale selections fail validation", () => {
    assert.equal(adjacentSelection([1, 2], [1, 3]), false);
});
