"""H3 Long Video Manager. V3 migration by RAFOLIE, 2026-09-28."""
import logging

from comfy_api.latest import ComfyExtension
from .comfyui.nodes import NODE_LIST
from .comfyui.ref_presets import migrate_input_media
from .comfyui.server_api import register_h3lvm_routes
from .comfyui.video_compare import register_video_compare_routes

logger = logging.getLogger(__name__)

WEB_DIRECTORY = "./web"


class H3LongVideoExtension(ComfyExtension):
    async def get_node_list(self):
        return NODE_LIST


async def comfy_entrypoint():
    # Reference presets from before the dedicated input folder point at the input
    # root. Adopting copies keeps them loadable without breaking workflows that
    # still use the originals; the migration is idempotent and cheap after the
    # first run.
    try:
        report = migrate_input_media()
        if report["entries"]:
            logger.info("[H3 LVM] 参考素材迁移完成：%d 个项目、%d 张卡片已指向 input/%s",
                        report["projects"], report["entries"], "h3-lvm-refs")
    except Exception:
        logger.warning("[H3 LVM] 参考素材迁移失败（节点仍可使用）", exc_info=True)
    register_h3lvm_routes()
    register_video_compare_routes()
    return H3LongVideoExtension()
