"""Temporary directories that remain writable in restricted Windows sandboxes."""

import os
import tempfile
import uuid


def make_temp_dir(prefix: str, parent: str | None = None) -> str:
    parent = parent or tempfile.gettempdir()
    for _ in range(20):
        path = os.path.join(parent, prefix + uuid.uuid4().hex[:8])
        try:
            os.mkdir(path)
            return path
        except FileExistsError:
            continue
    raise RuntimeError(f"could not create a temp directory under {parent}")
