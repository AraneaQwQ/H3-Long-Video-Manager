"""ComfyUI H3 Long Video Manager — Custom Node Plugin."""

from .nodes import (
    NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS,
)

# Register H3 Visual Cutter
try:
    from .nodes_cutter import (
        CUTTER_NODE_CLASS_MAPPINGS as CUTTER_MAPPINGS,
        CUTTER_NODE_DISPLAY_NAME_MAPPINGS as CUTTER_DISPLAY,
    )
    NODE_CLASS_MAPPINGS.update(CUTTER_MAPPINGS)
    NODE_DISPLAY_NAME_MAPPINGS.update(CUTTER_DISPLAY)
except ImportError as e:
    print(f"[H3 Long Video Manager] Cutter import failed: {e}")

# Register H3 Clip Exporter
try:
    from .nodes_exporter import (
        NODE_CLASS_MAPPINGS as EXPORTER_MAPPINGS,
        NODE_DISPLAY_NAME_MAPPINGS as EXPORTER_DISPLAY,
    )
    NODE_CLASS_MAPPINGS.update(EXPORTER_MAPPINGS)
    NODE_DISPLAY_NAME_MAPPINGS.update(EXPORTER_DISPLAY)
except ImportError as e:
    print(f"[H3 Long Video Manager] Exporter import failed: {e}")

# Register server API routes
try:
    from .server_api import register_h3lvm_routes
    register_h3lvm_routes()
except Exception as e:
    print(f"[H3 LVM API] Failed to register routes: {e}")

try:
    from .server_api_cutter import register_h3lvm_cutter_routes
    register_h3lvm_cutter_routes()
except Exception as e:
    print(f"[H3 LVM Cutter API] Failed to register routes: {e}")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
