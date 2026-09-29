"""H3 Long Video Manager — HTTP API routes (Phase A).

Registers routes with ComfyUI's PromptServer:
  GET /h3_lvm/projects       → {"projects": [...]}
  GET /h3_lvm/segments?project=<name> → enriched project index
  POST /h3_lvm/delete → delete one indexed segment

Namespace isolation: uses /h3_lvm/* (clipstream uses /minimax/clip_bin/*).
"""
from __future__ import annotations

import logging
import asyncio

logger = logging.getLogger(__name__)

# RAFOLIE 2026-09-28: package-relative imports; no global search path changes.
from .segment_store import delete_segment, list_project, list_projects, sanitize_project_name, DEFAULT_PROJECT


def register_h3lvm_routes() -> None:
    """Register /h3_lvm/* routes into ComfyUI's PromptServer.

    Safe to call even outside ComfyUI (silently skips if server unavailable).
    """
    try:
        import server
        from aiohttp import web
    except ImportError:
        logger.debug("[H3 LVM API] ComfyUI server or aiohttp not available. Skipping route registration.")
        return

    prompt_server = getattr(server.PromptServer, "instance", None)
    if prompt_server is None or not hasattr(prompt_server, "routes"):
        logger.debug("[H3 LVM API] PromptServer routes not found. Skipping.")
        return

    routes = prompt_server.routes

    @routes.get("/h3_lvm/projects")
    async def handle_projects(request):
        """Return the list of saved projects."""
        projects = list_projects()
        return web.json_response({"projects": projects, "default": DEFAULT_PROJECT})

    @routes.get("/h3_lvm/segments")
    async def handle_segments(request):
        """Return enriched segment list for a project."""
        project = request.rel_url.query.get("project", DEFAULT_PROJECT)
        project = sanitize_project_name(project)
        data = await asyncio.to_thread(list_project, project)
        return web.json_response(data, headers={"Cache-Control": "no-store"})


    @routes.post("/h3_lvm/delete")
    async def handle_delete(request):
        from urllib.parse import urlsplit
        origin = request.headers.get("Origin") or request.headers.get("Referer", "")
        if (request.headers.get("Sec-Fetch-Site") == "cross-site" or
                not origin or urlsplit(origin).netloc.lower() != request.host.lower()):
            return web.json_response({"error": "Only same-origin requests are allowed"}, status=403)
        if request.content_type != "application/json":
            return web.json_response({"error": "Expected JSON"}, status=415)
        try:
            body = await request.json()
            if not isinstance(body, dict) or not isinstance(body.get("project"), str) or not body["project"].strip():
                raise ValueError("A project name is required")
            project, asset_id = body["project"], body["segment_id"]
            removed = await asyncio.to_thread(delete_segment, project, asset_id)
        except (ValueError, TypeError, KeyError):
            return web.json_response({"error": "Invalid project or segment_id"}, status=400)
        except OSError:
            logger.exception("Failed to delete saved asset")
            return web.json_response({"error": "删除失败：文件可能被占用或没有写入权限，请关闭预览后重试。"}, status=409)
        if not removed:
            return web.json_response({"error": "片段已不存在，请刷新列表。"}, status=404)
        prompt_server.send_sync("h3_lvm/changed", {"project": project, "deleted_id": asset_id})
        return web.json_response({"deleted": asset_id})

    logger.info("[H3 LVM API] Successfully registered /h3_lvm/* routes with PromptServer.")


__all__ = ["register_h3lvm_routes"]
