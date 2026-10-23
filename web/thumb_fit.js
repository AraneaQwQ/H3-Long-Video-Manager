// RAFOLIE 2026-10-03: one thumbnail builder for both card decks.
//
// A thumbnail box is wide (card width x --thumb-h). Landscape frames fill it and
// object-fit: cover looks fine. A 9:16 frame in that same box shows only about a
// third of the picture, so portrait frames are displayed whole with object-fit:
// contain and the empty side space gets a blurred copy of the same frame instead
// of flat black. The box - and therefore the card - is exactly the same size in
// both cases; only the fit changes.
//
// Display only. No new node inputs and no new saved workflow fields.

export function portraitFromMeta(seg) {
    const w = Number(seg?.width);
    const h = Number(seg?.height);
    if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return null;
    return h > w;
}

function markPortrait(thumbWrap, img, dragSource) {
    if (thumbWrap.classList.contains("is-portrait")) return;
    thumbWrap.classList.add("is-portrait");
    img.classList.add("is-portrait");

    const bg = document.createElement("img");
    bg.className = "h3lvm-thumb-bg";
    bg.src = img.src;
    bg.alt = "";
    bg.draggable = false;
    bg.draggable = Boolean(dragSource);
    bg.setAttribute("aria-hidden", "true");
    thumbWrap.insertBefore(bg, img);
}

// dragSource: false (the default) keeps the picture out of the drag, because on a draggable
// card the browser would use the small picture as the drag ghost instead of the card. A panel
// whose card is NOT draggable - the Guide pool, where only the media area may start a drag -
// passes true, otherwise the picture itself would swallow the gesture.
export function appendThumbnail(thumbWrap, seg, { dragSource = false } = {}) {
    if (!seg?.thumbnail_url) {
        thumbWrap.innerHTML = '<div class="h3lvm-thumb-placeholder">🎬</div>';
        return null;
    }

    const img = document.createElement("img");
    img.className = "h3lvm-thumb";
    img.src = seg.thumbnail_url;
    img.loading = "lazy";
    img.draggable = Boolean(dragSource);
    thumbWrap.appendChild(img);

    const portrait = portraitFromMeta(seg);
    if (portrait === true) {
        markPortrait(thumbWrap, img, dragSource);
    } else if (portrait === null) {
        // Index entries without width/height: fall back to the image itself.
        img.addEventListener("load", () => {
            if (img.naturalHeight > img.naturalWidth) markPortrait(thumbWrap, img, dragSource);
        }, { once: true });
    }
    return img;
}
