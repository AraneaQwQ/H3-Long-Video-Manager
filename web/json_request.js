const inFlight = new Map();

// Share only simultaneous reads. Once a reply settles it is removed, so the next
// refresh always asks the server again and cannot reuse stale project data.
export function fetchJsonShared(api, path) {
    const existing = inFlight.get(path);
    if (existing) return existing;
    const request = (async () => {
        const response = await api.fetchApi(path, { cache: "no-store" });
        const data = await response.json().catch(() => ({}));
        return { ok: response.ok, status: response.status, data };
    })();
    inFlight.set(path, request);
    const clear = () => {
        if (inFlight.get(path) === request) inFlight.delete(path);
    };
    request.then(clear, clear);
    return request;
}
