import assert from "node:assert/strict";
import test from "node:test";

import { fetchJsonShared } from "../../web/json_request.js";

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((yes, no) => {
        resolve = yes;
        reject = no;
    });
    return { promise, resolve, reject };
}

test("identical simultaneous GETs share one request and one JSON read", async () => {
    const pending = deferred();
    let calls = 0;
    let jsonCalls = 0;
    const api = {
        fetchApi(path, options) {
            calls++;
            assert.equal(path, "/cards?project=story");
            assert.deepEqual(options, { cache: "no-store" });
            return pending.promise;
        },
    };
    const first = fetchJsonShared(api, "/cards?project=story");
    const second = fetchJsonShared(api, "/cards?project=story");
    assert.equal(calls, 1);
    pending.resolve({
        ok: true,
        status: 200,
        async json() {
            jsonCalls++;
            return { segments: [1, 2] };
        },
    });
    const [a, b] = await Promise.all([first, second]);
    assert.equal(jsonCalls, 1);
    assert.deepEqual(a.data, { segments: [1, 2] });
    assert.equal(a, b);
});

test("settled and failed requests never become a persistent cache", async () => {
    let calls = 0;
    const api = {
        async fetchApi() {
            calls++;
            if (calls === 1) throw new Error("offline");
            return { ok: true, status: 200, async json() { return { ok: true }; } };
        },
    };
    await assert.rejects(fetchJsonShared(api, "/cards"), /offline/);
    const retry = await fetchJsonShared(api, "/cards");
    assert.equal(retry.data.ok, true);
    await fetchJsonShared(api, "/cards");
    assert.equal(calls, 3);
});
