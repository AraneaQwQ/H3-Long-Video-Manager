"""Import this plugin's own modules without ComfyUI.

Every module under ``comfyui/`` uses package-relative imports
(``from ..core import ...``), so ``from comfyui import server_api`` fails with
"attempted relative import beyond top-level package". Loading the repo folder as a
package named ``h3lvm`` gives those relative imports something to resolve against.

Only the root package is registered by hand; ``comfyui`` and ``core`` are found
through it by the normal import machinery. The root ``__init__.py`` is NOT executed,
which is the point: it needs ``comfy_api``, and these tests are about HTTP handlers.
"""
from __future__ import annotations

import importlib
import os
import sys
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = "h3lvm"


def load(relative_name: str):
    """Import ``<repo>/<relative_name>`` as a submodule of the plugin package."""
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    if sys.modules.get(PACKAGE) is None:
        package = types.ModuleType(PACKAGE)
        package.__path__ = [REPO]
        sys.modules[PACKAGE] = package
    return importlib.import_module(PACKAGE + "." + relative_name)
