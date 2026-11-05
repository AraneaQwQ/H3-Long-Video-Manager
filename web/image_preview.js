function apiUrl(api, path) {
    if (typeof api.apiURL === "function") return api.apiURL(path);
    if (typeof api.getFileUrl === "function") return api.getFileUrl(path);
    return path;
}

function imagePath(route, entry) {
    const query = new URLSearchParams({
        filename: entry?.filename ?? "",
        subfolder: entry?.subfolder || "",
        type: entry?.type || "input",
    });
    return `${route}?${query}`;
}

export function imageThumbnailUrl(api, entry) {
    return apiUrl(api, imagePath("/h3_lvm/image_thumbnail", entry));
}

export function imageMetadataPath(entry) {
    return imagePath("/h3_lvm/image_metadata", entry);
}
