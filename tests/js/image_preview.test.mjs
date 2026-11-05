import assert from "node:assert/strict";
import test from "node:test";

import { imageMetadataPath, imageThumbnailUrl } from "../../web/image_preview.js";

const entry = { filename: "a b.png", subfolder: "refs/story", type: "input" };

test("image cards use the thumbnail route with the same safe media identity", () => {
    const url = new URL(imageThumbnailUrl({}, entry), "http://localhost");
    assert.equal(url.pathname, "/h3_lvm/image_thumbnail");
    assert.equal(url.searchParams.get("filename"), "a b.png");
    assert.equal(url.searchParams.get("subfolder"), "refs/story");
    assert.equal(url.searchParams.get("type"), "input");
});

test("thumbnail URLs receive the host API prefix exactly once", () => {
    const api = { apiURL: path => "/prefix" + path };
    const url = new URL(imageThumbnailUrl(api, entry), "http://localhost");
    assert.equal(url.pathname, "/prefix/h3_lvm/image_thumbnail");
    assert.equal(url.searchParams.get("filename"), "a b.png");
});

test("metadata stays a route for fetchApi, which applies the host prefix itself", () => {
    const url = new URL(imageMetadataPath(entry), "http://localhost");
    assert.equal(url.pathname, "/h3_lvm/image_metadata");
    assert.equal(url.searchParams.get("filename"), "a b.png");
});
