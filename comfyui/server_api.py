"""H3 Long Video Manager — HTTP API routes (Phase A).

Registers routes with ComfyUI's PromptServer:
  GET /h3_lvm/projects       → {"projects": [{"name", "segments"}], "default": ...}
  POST /h3_lvm/project       → create an empty project bin
  POST /h3_lvm/project/delete → delete a whole project bin
  GET /h3_lvm/segments?project=<name> → enriched project index
  POST /h3_lvm/delete → delete one indexed segment

Namespace isolation: uses /h3_lvm/* (clipstream uses /minimax/clip_bin/*).
"""
from __future__ import annotations

from urllib.parse import urlsplit

import logging
import asyncio

try:  # aiohttp only exists inside ComfyUI; without it no routes are registered.
    from aiohttp import web
except ImportError:
    web = None

logger = logging.getLogger(__name__)

# RAFOLIE 2026-09-28: package-relative imports; no global search path changes.
from .segment_store import (
    DEFAULT_PROJECT,
    create_project,
    delete_project,
    delete_segment,
    list_project,
    list_projects_with_counts,
    sanitize_project_name,
)


def _csrf_block(request):
    """Rejects a mutating request that is not same-origin; ComfyUI has no CSRF gate."""
    origin = request.headers.get("Origin") or request.headers.get("Referer", "")
    if (request.headers.get("Sec-Fetch-Site") == "cross-site" or
            not origin or urlsplit(origin).netloc.lower() != request.host.lower()):
        return web.json_response({"error": "Only same-origin requests are allowed"}, status=403)
    return None


def register_h3lvm_routes() -> None:
    """Register /h3_lvm/* routes into ComfyUI's PromptServer.

    Safe to call even outside ComfyUI (silently skips if server unavailable).
    """
    try:
        import server
    except ImportError:
        logger.debug("[H3 LVM API] ComfyUI server or aiohttp not available. Skipping route registration.")
        return
    if web is None:
        logger.debug("[H3 LVM API] aiohttp is not importable. Skipping route registration.")
        return

    prompt_server = getattr(server.PromptServer, "instance", None)
    if prompt_server is None or not hasattr(prompt_server, "routes"):
        logger.debug("[H3 LVM API] PromptServer routes not found. Skipping.")
        return

    routes = prompt_server.routes

    @routes.get("/h3_lvm/projects")
    async def handle_projects(request):
        """Return every project bin with its segment count, for the Picker menu."""
        data = await asyncio.to_thread(list_projects_with_counts)
        return web.json_response({"projects": data, "default": DEFAULT_PROJECT},
                                 headers={"Cache-Control": "no-store"})


    @routes.post("/h3_lvm/project")
    async def handle_create_project(request):
        blocked = _csrf_block(request)
        if blocked is not None:
            return blocked
        if request.content_type != "application/json":
            return web.json_response({"error": "Expected JSON"}, status=415)
        try:
            body = await request.json()
            typed = body.get("project") if isinstance(body, dict) else None
            result = await asyncio.to_thread(create_project, typed)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except (TypeError, KeyError):
            return web.json_response({"error": "Invalid project name"}, status=400)
        except OSError:
            logger.exception("Failed to create project")
            return web.json_response({"error": "建立失败：没有写入权限或文件夹被占用，请关闭预览后重试。"}, status=409)
        return web.json_response(result, headers={"Cache-Control": "no-store"})


    @routes.post("/h3_lvm/project/delete")
    async def handle_delete_project(request):
        blocked = _csrf_block(request)
        if blocked is not None:
            return blocked
        if request.content_type != "application/json":
            return web.json_response({"error": "Expected JSON"}, status=415)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Expected an object")
            result = await asyncio.to_thread(delete_project, body.get("project"), body.get("confirm"))
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except (TypeError, KeyError):
            return web.json_response({"error": "Invalid project name"}, status=400)
        except OSError:
            logger.exception("Failed to delete project")
            return web.json_response({"error": "删除失败：文件夹可能正被预览占用，请关闭预览后重试。"}, status=409)
        if not result["deleted"]:
            return web.json_response({"error": "项目已不存在，请刷新列表。"}, status=404)
        return web.json_response(result, headers={"Cache-Control": "no-store"})

    @routes.get("/h3_lvm/segments")
    async def handle_segments(request):
        """Return enriched segment list for a project."""
        project = request.rel_url.query.get("project", DEFAULT_PROJECT)
        project = sanitize_project_name(project)
        data = await asyncio.to_thread(list_project, project)
        return web.json_response(data, headers={"Cache-Control": "no-store"})


    @routes.post("/h3_lvm/delete")
    async def handle_delete(request):
        blocked = _csrf_block(request)
        if blocked is not None:
            return blocked
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
