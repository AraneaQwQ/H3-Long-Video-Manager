"""H3 Long Video Manager — ComfyUI Custom Node Plugin."""

import os
import sys
import logging

_PLUGIN_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from .comfyui.nodes import (
    NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS,
)

# --- Register HTTP API routes (Phase A) ---
try:
    from .comfyui.server_api import register_h3lvm_routes
    register_h3lvm_routes()
except Exception as exc:
    logging.getLogger(__name__).warning("h3lvm: routes not registered: %s", exc)

# --- Register Visual Cutter nodes (Phase D) ---
try:
    from .comfyui.nodes_cutter import (
        CUTTER_NODE_CLASS_MAPPINGS,
        CUTTER_NODE_DISPLAY_NAME_MAPPINGS,
    )
    NODE_CLASS_MAPPINGS.update(CUTTER_NODE_CLASS_MAPPINGS)
    NODE_DISPLAY_NAME_MAPPINGS.update(CUTTER_NODE_DISPLAY_NAME_MAPPINGS)
except Exception as exc:
    logging.getLogger(__name__).warning("h3lvm: cutter nodes not registered: %s", exc)

# --- Register Visual Cutter API routes (Phase D) ---
try:
    from .comfyui.server_api_cutter import register_h3lvm_cutter_routes
    register_h3lvm_cutter_routes()
except Exception as exc:
    logging.getLogger(__name__).warning("h3lvm: cutter routes not registered: %s", exc)

# --- Web frontend (Phase B2) ---
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
