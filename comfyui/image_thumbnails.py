from __future__ import annotations

import hashlib
import os
import tempfile
import threading

from PIL import Image, ImageOps

from ..core.ref_media import media_kind, parse_media_list, resolve_media_path

THUMBNAIL_MAX_EDGE = 512
_RESAMPLING = getattr(Image, "Resampling", Image)
_locks = {}
_locks_guard = threading.Lock()


def _media_roots():
    import folder_paths

    roots = {"input": folder_paths.get_input_directory()}
    for name in ("output", "temp"):
        folder = folder_paths.get_directory_by_type(name)
        if folder:
            roots[name] = folder
    return roots


def _cache_dir():
    import folder_paths

    try:
        root = folder_paths.get_directory_by_type("temp")
    except Exception:
        root = None
    return os.path.join(root or tempfile.gettempdir(), "h3_lvm_image_thumbnails")


def _source(entry, roots):
    cleaned = parse_media_list([entry], 1)[0]
    if media_kind(cleaned["filename"]) != "image":
        raise ValueError("只有图片文件可以生成缩略图。")
    path = resolve_media_path(roots or _media_roots(), cleaned)
    return path, os.stat(path)


def image_metadata(entry, roots=None):
    path, _stat = _source(entry, roots)
    with Image.open(path) as image:
        width, height = image.size
        orientation = image.getexif().get(274, 1)
    if orientation in (5, 6, 7, 8):
        width, height = height, width
    return {"width": int(width), "height": int(height)}


def thumbnail_path(entry, roots=None, cache_dir=None):
    path, stat = _source(entry, roots)
    identity = "\0".join((
        os.path.normcase(os.path.realpath(path)),
        str(stat.st_size),
        str(stat.st_mtime_ns),
        str(THUMBNAIL_MAX_EDGE),
        "jpeg-v1",
    )).encode("utf-8")
    key = hashlib.sha256(identity).hexdigest()
    folder = cache_dir or _cache_dir()
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, key + ".jpg")
    if os.path.isfile(target) and os.path.getsize(target):
        return target

    with _locks_guard:
        lock = _locks.setdefault(target, threading.Lock())
    with lock:
        if os.path.isfile(target) and os.path.getsize(target):
            return target
        with Image.open(path) as source:
            frame = ImageOps.exif_transpose(source)
            frame.thumbnail((THUMBNAIL_MAX_EDGE, THUMBNAIL_MAX_EDGE), _RESAMPLING.LANCZOS)
            has_alpha = frame.mode in ("RGBA", "LA") or (
                frame.mode == "P" and "transparency" in frame.info)
            if has_alpha:
                rgba = frame.convert("RGBA")
                background = Image.new("RGBA", rgba.size, (24, 26, 32, 255))
                output = Image.alpha_composite(background, rgba).convert("RGB")
            else:
                output = frame.convert("RGB")
        handle, temporary = tempfile.mkstemp(prefix=".thumb_", suffix=".jpg", dir=folder)
        os.close(handle)
        try:
            output.save(temporary, format="JPEG", quality=86, optimize=True)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
    return target
