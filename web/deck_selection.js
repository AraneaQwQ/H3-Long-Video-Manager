// Adjacency follows the current library order, including gaps left by deletion.
export function adjacentSelection(selected, available) {
    const wanted = new Set(selected);
    if (!wanted.size) return true;
    const positions = available.flatMap((id, index) => wanted.has(id) ? [index] : []);
    return positions.length === wanted.size
        && positions.at(-1) - positions[0] + 1 === positions.length;
}

export function toggleMergeSelection(selected, id, available) {
    const next = new Set(selected);
    if (!available.includes(id)) return next;
    if (next.has(id)) {
        next.delete(id);
        return next;
    }
    next.add(id);
    return adjacentSelection(next, available) ? next : new Set([id]);
}
