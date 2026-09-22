"""H3 Long Video Manager — HTTP API routes (Phase A).

Registers two routes with ComfyUI's PromptServer:
  GET /h3_lvm/projects       → {"projects": [...]}
  GET /h3_lvm/segments?project=<name> → enriched project index

Namespace isolation: uses /h3_lvm/* (clipstream uses /minimax/clip_bin/*).
"""
from __future__ import annotations

import logging
import sys
import os

logger = logging.getLogger(__name__)

# Ensure the plugin root is importable
_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from .segment_store import list_project, list_projects, sanitize_project_name, DEFAULT_PROJECT


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
        data = list_project(project)
        return web.json_response(data)

    logger.info("[H3 LVM API] Successfully registered /h3_lvm/* routes with PromptServer.")


__all__ = ["register_h3lvm_routes"]
