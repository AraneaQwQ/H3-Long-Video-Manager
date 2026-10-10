"""H3 Long Video Manager — HTTP API routes (Phase A).

Registers routes with ComfyUI's PromptServer:
  GET /h3_lvm/projects?scope=segments|image|audio → one library’s projects with their counts
  POST /h3_lvm/project       → create an empty project (same scope)
  POST /h3_lvm/project/delete → delete a whole project (same scope)

scope picks the folder, not a filter: "segments" is the video bin root the Picker and the
Manager use, "image" and "audio" are the two reference libraries - separate roots, because a
reference image and a reference audio are different material for different ports.
  GET /h3_lvm/segments?project=<name> → enriched project index
  GET /h3_lvm/ref_plan?w=&h=&mp=&upscale=0|1 → planned size for a reference image
  GET /h3_lvm/ref_presets?project=<name>&kind=image|audio → that kind's preset for one project (paths only)
  POST /h3_lvm/ref_presets → save that kind's preset
  POST /h3_lvm/delete → delete one indexed segment
  POST /h3_lvm/merge → join consecutive segments into one, renumber the rest

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
# RAFOLIE 2026-10-10: /h3_lvm/ref_plan answers the reference-image size question from the one
# implementation that the loader nodes use.
from ..core.ref_size import DEFAULT_UPSCALE_SMALL_IMAGES, plan_reference
from .segment_store import (
    DEFAULT_PROJECT,
    create_project,
    delete_project,
    delete_segment,
    list_project,
    list_projects_with_counts,
    merge_segments,
    sanitize_project_name,
)
from .ref_presets import (
    KIND_ROOTS,
    create_reference_project,
    delete_reference_project,
    list_reference_projects,
    load_references,
    save_references,
)


def _scope(value) -> str:
    """Which library a project request is about: the video bins or one reference kind."""
    text = str(value or "").strip().lower()
    return text if text in KIND_ROOTS else "segments"


def _query_bool(value, default: bool) -> bool:
    """Parse an optional query flag; anything unreadable falls back to the node default."""
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return default


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
        """List one library’s projects with their counts, for the project menu.

        scope=segments (the default) reports saved video segments; scope=image and
        scope=audio list that kind’s own reference library and report its card counts.
        """
        scope = _scope(request.rel_url.query.get("scope"))
        if scope in KIND_ROOTS:
            data = await asyncio.to_thread(list_reference_projects, scope)
        else:
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
            scope = _scope(body.get("scope") if isinstance(body, dict) else None)
            if scope in KIND_ROOTS:
                result = await asyncio.to_thread(create_reference_project, scope, typed)
            else:
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
            scope = _scope(body.get("scope"))
            if scope in KIND_ROOTS:
                result = await asyncio.to_thread(
                    delete_reference_project, scope, body.get("project"), body.get("confirm"))
            else:
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

    # A reference preset is a saved combination of reference cards for one project of one
    # kind. It holds paths into the media folders, never a copy of the media, so a preset
    # costs a few hundred bytes however big the images are, and it lives in that kind's own
    # library - the audio loader never sees the image library and the other way round.
    @routes.get("/h3_lvm/ref_presets")
    async def handle_ref_presets(request):
        """Return one project's saved reference cards for one kind (paths only)."""
        query = request.rel_url.query
        project = sanitize_project_name(query.get("project", DEFAULT_PROJECT))
        try:
            data = await asyncio.to_thread(load_references, query.get("kind"), project)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(data, headers={"Cache-Control": "no-store"})

    @routes.post("/h3_lvm/ref_presets")
    async def handle_save_ref_presets(request):
        blocked = _csrf_block(request)
        if blocked is not None:
            return blocked
        if request.content_type != "application/json":
            return web.json_response({"error": "Expected JSON"}, status=415)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Expected an object")
            result = await asyncio.to_thread(
                save_references, body.get("kind"), body.get("project"), body.get("entries"))
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except (TypeError, KeyError):
            return web.json_response({"error": "Invalid preset"}, status=400)
        except OSError:
            logger.exception("Failed to save reference preset")
            return web.json_response({"error": "保存失败：没有写入权限或文件正被占用，请稍后重试。"}, status=409)
        return web.json_response(result, headers={"Cache-Control": "no-store"})

    @routes.get("/h3_lvm/segments")
    async def handle_segments(request):
        """Return enriched segment list for a project."""
        project = request.rel_url.query.get("project", DEFAULT_PROJECT)
        project = sanitize_project_name(project)
        data = await asyncio.to_thread(list_project, project)
        return web.json_response(data, headers={"Cache-Control": "no-store"})



    # The card UI shows the size a reference image WILL get before the node runs.
    # Asking the planner instead of re-implementing it in JavaScript is what keeps
    # the card and the produced tensor agreeing.
    @routes.get("/h3_lvm/ref_plan")
    async def handle_ref_plan(request):
        """Return the size a reference image gets, for the node's current settings.

        The card shows this, so the answer must come from plan_reference - the same
        function the node runs, including the upscale switch.
        """
        query = request.rel_url.query
        try:
            upscale = _query_bool(query.get("upscale"), DEFAULT_UPSCALE_SMALL_IMAGES)
            plan = await asyncio.to_thread(
                plan_reference, int(query["w"]), int(query["h"]), float(query["mp"]), upscale)
        except (KeyError, TypeError, ValueError) as exc:
            return web.json_response({"error": str(exc) or "w, h and mp are required"}, status=400)
        return web.json_response(plan, headers={"Cache-Control": "no-store"})

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

    @routes.post("/h3_lvm/merge")
    async def handle_merge(request):
        """Join consecutive segments into one card and close the numbering gap."""
        blocked = _csrf_block(request)
        if blocked is not None:
            return blocked
        if request.content_type != "application/json":
            return web.json_response({"error": "Expected JSON"}, status=415)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Expected an object")
            if not isinstance(body.get("project"), str) or not body["project"].strip():
                raise ValueError("A project name is required")
            result = await asyncio.to_thread(merge_segments, body["project"], body.get("segment_ids"))
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except (TypeError, KeyError):
            return web.json_response({"error": "Invalid project or segment_ids"}, status=400)
        except MemoryError:
            logger.exception("Failed to merge segments: out of memory")
            return web.json_response({"error": "合并失败：内存不足，请减少一次合并的片段数量。"}, status=507)
        except OSError:
            logger.exception("Failed to merge segments")
            return web.json_response({"error": "合并失败：文件可能被占用或没有写入权限，请关闭预览后重试。"}, status=409)
        prompt_server.send_sync("h3_lvm/changed", {"project": result["project"], "merged_id": result["merged_id"]})
        return web.json_response(result, headers={"Cache-Control": "no-store"})

    logger.info("[H3 LVM API] Successfully registered /h3_lvm/* routes with PromptServer.")


__all__ = ["register_h3lvm_routes"]
