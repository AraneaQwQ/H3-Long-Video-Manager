import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const source = readFileSync(new URL('../web/guide_editor_state.js', import.meta.url), 'utf8');
const { localPointerX, sidebarWidthsFor, laneSpaceBonus, referencePosition, releaseFromPosition, referenceDescription, createGuideHistory } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
assert.equal(referencePosition(), 100);
assert.equal(referencePosition({ enabled: false, threshold: .9 }), 100);
assert.ok(Math.abs(referencePosition({ enabled: true, threshold: .9 }) - 10) < 1e-10);
for (const position of [0, 10, 30, 55, 99.9]) {
    const config = releaseFromPosition(position);
    assert.equal(config.enabled, true);
    assert.ok(Math.abs(referencePosition(config) - position) < 1e-8);
}
assert.deepEqual(releaseFromPosition(100, { threshold: .7 }), { enabled: false, threshold: .7 });
assert.equal(referencePosition({ enabled: true, threshold: 0 }), 100);
assert.equal(referencePosition({ enabled: true, threshold: 1 }), 0);
assert.equal(referenceDescription({ enabled: true, threshold: 0 }), '全程保留图片条件');
for (const invalid of [-1, 101, '', NaN, Infinity, true, null]) assert.throws(() => releaseFromPosition(invalid));
const doc = { guides: [{ id: 'i1', frame_index: 0 }], view_state: { selected_id: null } };
const history = createGuideHistory(doc, 3);
assert.equal(history.canUndo, false);
doc.view_state.selected_id = 'i1';
assert.equal(history.record(doc), false); // selection is never an edit
const original = JSON.stringify(doc.guides);
doc.guides[0].frame_index = 96;
assert.equal(history.record(doc), true);
assert.equal(history.record(doc), false);
doc.keyframe_release = { enabled: true, threshold: .9 };
history.record(doc);
assert.equal('keyframe_release' in history.undo(), false); // old docs stay field-free
assert.equal(JSON.stringify(history.undo().guides), original);
assert.equal(history.canUndo, false);
assert.equal(history.redo().guides[0].frame_index, 96);
assert.equal(history.redo().keyframe_release.threshold, .9);
history.undo();
doc.guides[0].frame_index = 120;
delete doc.keyframe_release;
history.record(doc);
assert.equal(history.canRedo, false); // divergent edit clears redo
for (let i = 1; i < 8; i++) { doc.guides[0].frame_index = i; history.record(doc); }
let undos = 0;
while (history.undo()) undos++;
assert.equal(undos, 3);
history.reset(doc);
assert.equal(history.canUndo, false);
assert.equal(history.canRedo, false);
console.log('Guide workbench state: mapping, field absence, document history, branch and limit passed');

assert.deepEqual(laneSpaceBonus(-50), { image: 0, audio: 0 });
assert.deepEqual(laneSpaceBonus(1000), { image: 700, audio: 300 });
for (const spare of [0, 1, 83.7, 1000, 5000]) { const bonus = laneSpaceBonus(spare); assert.equal(bonus.image + bonus.audio, Math.floor(spare)); }

assert.deepEqual(sidebarWidthsFor(1600),{left:280,right:320});
assert.deepEqual(sidebarWidthsFor(2000,{left:999,right:999}),{left:420,right:440});
for(const width of [811,900,1050,1600]){const result=sidebarWidthsFor(width,{left:420,right:440});assert.ok(result.left>=200&&result.right>=250);assert.ok(width-result.left-result.right>=300)}

for(const zoom of [.4,.7,1,1.5,2]){const rect={left:120,width:640*zoom};assert.ok(Math.abs(localPointerX(120+200*zoom,rect,640,1)-199)<1e-8)}
