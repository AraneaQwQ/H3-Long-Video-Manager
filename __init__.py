"""H3 Long Video Manager. V3 migration by RAFOLIE, 2026-09-28."""
from comfy_api.latest import ComfyExtension
from .comfyui.nodes import NODE_LIST
from .comfyui.server_api import register_h3lvm_routes

WEB_DIRECTORY = "./web"


class H3LongVideoExtension(ComfyExtension):
    async def get_node_list(self):
        return NODE_LIST


async def comfy_entrypoint():
    register_h3lvm_routes()
    return H3LongVideoExtension()
