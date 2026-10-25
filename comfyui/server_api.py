"""H3 Long Video Manager — HTTP API routes (Phase A).

Registers routes with ComfyUI's PromptServer:
  GET /h3_lvm/projects?scope=segments|uploads|image|audio -> one library's projects + counts
  POST /h3_lvm/project        -> create an empty project (same scope)
  POST /h3_lvm/project/delete -> delete a whole project (same scope)

scope picks the folder, not a filter. "segments" is the cut bin the Manager and the Smart
Split write; "uploads" is the Picker's second library of whole videos the user brought in;
"image" and "audio" are the two reference libraries. Four roots, none of them inside
another: the same project name in two libraries means two independent folders, which is
what the Picker's two mode buttons promise. A write request that names a library we do not
have is refused; a read request without a scope still gets the cut bin, because that is
what every older bookmark meant.
  GET /h3_lvm/uploads?project=<name> -> one upload project's cards, with /view urls
  POST /h3_lvm/uploads/import -> multipart upload of one video file
  POST /h3_lvm/uploads/delete -> remove one uploaded video and its files
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
import os
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
from .uploaded_video_store import (
    MAX_UPLOAD_BYTES,
    create_upload_project,
    delete_upload,
    delete_upload_project,
    import_upload,
    list_upload_projects,
    list_uploads,
    open_partial,
    reorder_uploads,
)
from .video_loader_node import list_video_directory, video_file_info
from .source_preview import (
    create_compatible_source_preview,
    create_source_preview,
    create_upload_preview,
    source_preview_path,
)
from .system_file_picker import choose_system_video



# The four libraries a request can name. "segments" is spelled out as well as implied,
# because the Picker now sends its mode button explicitly instead of relying on a default.
SEGMENT_SCOPE = "segments"
UPLOAD_SCOPE = "uploads"


def _scope(value) -> str:
    """Which library a request means: the cut bin, the upload library, or one reference kind.

    An empty scope is a request from before the Picker had two libraries, and it always
    meant the cut bin. A name that is not a library is refused rather than guessed - a typo
    in the panel must not create a project in a folder the user never looked at.
    """
    text = str(value or "").strip().lower()
    if not text:
        return SEGMENT_SCOPE
    if text in (SEGMENT_SCOPE, UPLOAD_SCOPE) or text in KIND_ROOTS:
        return text
    raise ValueError("未知的素材库类型：" + text + "。")


def _scope_for_read(value) -> str:
    """Reading defaults to the cut bin, so an old bookmark still opens the panel."""
    try:
        return _scope(value)
    except ValueError:
        return SEGMENT_SCOPE


def _project_library(scope: str):
    """(list, create, delete) for one library, so a new library is one entry here.

    Every library answers the same three project calls; the reference kinds carry their
    kind argument with them, which is the only real difference between the four.
    """
    if scope == UPLOAD_SCOPE:
        return list_upload_projects, create_upload_project, delete_upload_project
    if scope in KIND_ROOTS:
        return (lambda: list_reference_projects(scope),
                lambda project: create_reference_project(scope, project),
                lambda project, confirm: delete_reference_project(scope, project, confirm))
    return list_projects_with_counts, create_project, delete_project  # SEGMENT_SCOPE


def _remove_partial(path: str) -> None:
    """Drop a half-received upload; an invisible .partial still costs the disk."""
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError:
        logger.warning("[H3 LVM API] Could not remove leftover upload %s", path)

async def _part_text(part) -> str:
    """Read one multipart text field.

    aiohttp hands back bytes when the part carries no charset, which is what a browser
    sends for a plain form field; str() on that would produce "bytearray(b'show')".
    """
    raw = await part.read(decode=False)
    if isinstance(raw, (bytes, bytearray, memoryview)):
        return bytes(raw or b"").decode("utf-8", "replace")
    return str(raw or "")


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
        """List one library's projects with their counts, for the project menu.

        scope=segments is the cut bin, scope=uploads the Picker's uploaded videos, and
        scope=image / scope=audio one reference library. Each row carries its own count
        key ("segments", "videos", "references") so the menu can say what an entry holds.
        """
        scope = _scope_for_read(request.rel_url.query.get("scope"))
        list_for, _, _ = _project_library(scope)
        data = await asyncio.to_thread(list_for)
        return web.json_response({"projects": data, "scope": scope, "default": DEFAULT_PROJECT},
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
            _, create_for, _ = _project_library(scope)
            result = await asyncio.to_thread(create_for, typed)
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
            _, _, delete_for = _project_library(scope)
            result = await asyncio.to_thread(delete_for, body.get("project"), body.get("confirm"))
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

    # The Picker's second library: whole videos the user brought in, stored as they are.
    # Bytes are streamed into a .partial file and only become a card once FFmpeg has read
    # them, so a card in the panel is always a video the node can actually decode.
    @routes.get("/h3_lvm/uploads")
    async def handle_uploads(request):
        """Return one upload project's cards, with /view urls for covers and previews.

        output_size is the node's current 输出分辨率 value and custom_max_side the number
        typed for the 自定义 entry. The size the decode will really produce is planned here
        rather than in the panel, so a card can never advertise a number the node disagrees
        with; the upload store stays out of it because the setting belongs to the node, not
        to the file.
        """
        from .video_decode import parse_max_side, scale_plan  # local: the API works without torch
        project = request.rel_url.query.get("project", DEFAULT_PROJECT)
        max_side = parse_max_side(request.rel_url.query.get("output_size"),
                                  request.rel_url.query.get("custom_max_side"))
        try:
            data = await asyncio.to_thread(list_uploads, project)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        for video in data.get("videos", []):
            plan = scale_plan(video.get("width"), video.get("height"), max_side)
            video["out_width"] = plan["width"]
            video["out_height"] = plan["height"]
            video["out_scaled"] = plan["scaled"]
        return web.json_response(data, headers={"Cache-Control": "no-store"})

    @routes.post("/h3_lvm/uploads/import")
    async def handle_upload_import(request):
        """Take one video from the browser and register it as a card.

        The form is read in order: a "project" text field first, then the "file" part.
        The bytes are copied chunk by chunk, so a 2 GB clip never has to fit in memory.
        """
        blocked = _csrf_block(request)
        if blocked is not None:
            return blocked
        if request.content_type != "multipart/form-data":
            return web.json_response({"error": "Expected multipart/form-data"}, status=415)
        try:
            reader = await request.multipart()
        except (RuntimeError, ValueError):
            return web.json_response({"error": "上传内容读不出来，请重新选择视频文件。"}, status=400)
        project = None
        video_part = None
        while video_part is None:
            part = await reader.next()
            if part is None:
                break
            if part.name == "project":
                project = await _part_text(part)
            elif part.name == "file":
                video_part = part
        if project is None:
            return web.json_response({"error": "缺少项目名，请先在面板里选择项目。"}, status=400)
        # A browser still sends the file part when the picker was left empty, with no
        # filename and no bytes; that is "no file", not "a zero-byte video".
        if video_part is None or not str(video_part.filename or "").strip():
            return web.json_response({"error": "没有收到视频文件。"}, status=400)
        try:
            _, partial = await asyncio.to_thread(open_partial, project)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except OSError:
            return web.json_response({"error": "建立失败：没有写入权限或文件夹被占用。"}, status=409)
        written = 0
        too_big = False
        try:
            with open(partial, "wb") as stream:
                while True:
                    chunk = await video_part.read_chunk()
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > MAX_UPLOAD_BYTES:
                        too_big = True
                        break
                    stream.write(chunk)
        except (OSError, RuntimeError, ValueError):
            logger.exception("Failed to receive the uploaded video")
            _remove_partial(partial)
            return web.json_response({"error": "上传中断了，请重试。"}, status=400)
        if too_big:
            _remove_partial(partial)
            return web.json_response(
                {"error": "这个视频超过单个文件 %d MB 的上限，请先裁短或缩小再上传。"
                          % (MAX_UPLOAD_BYTES // 1024 ** 2)}, status=413)
        try:
            record = await asyncio.to_thread(
                import_upload, project, partial, video_part.filename or "video.mp4")
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except OSError:
            logger.exception("Failed to store the uploaded video")
            return web.json_response({"error": "保存失败：没有写入权限或文件正被占用。"}, status=409)
        prompt_server.send_sync("h3_lvm/uploads_changed",
                                {"scope": UPLOAD_SCOPE,
                                 "project": sanitize_project_name(project),
                                 "segment_id": record["segment_id"], "action": "import"})
        return web.json_response(record, headers={"Cache-Control": "no-store"})

    @routes.post("/h3_lvm/uploads/delete")
    async def handle_upload_delete(request):
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
            removed = await asyncio.to_thread(delete_upload, project, asset_id)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except (TypeError, KeyError):
            return web.json_response({"error": "Invalid project or segment_id"}, status=400)
        except OSError:
            logger.exception("Failed to delete an uploaded video")
            return web.json_response({"error": "删除失败：文件可能正在预览，请关闭预览后重试。"}, status=409)
        if not removed:
            return web.json_response({"error": "这个视频已不存在，请刷新列表。"}, status=404)
        prompt_server.send_sync("h3_lvm/uploads_changed",
                                {"scope": UPLOAD_SCOPE,
                                 "project": sanitize_project_name(project),
                                 "segment_id": asset_id, "action": "delete"})
        return web.json_response({"deleted": asset_id})

    @routes.post("/h3_lvm/uploads/reorder")
    async def handle_upload_reorder(request):
        """Rewrite the card order of one upload project.

        The panel sends the card ids in the order the user arranged them; the store turns
        that into segment_id 1..N, because the number is how a workflow picks a card.
        """
        blocked = _csrf_block(request)
        if blocked is not None:
            return blocked
        if request.content_type != "application/json":
            return web.json_response({"error": "Expected JSON"}, status=415)
        try:
            body = await request.json()
            if not isinstance(body, dict) or not isinstance(body.get("project"), str) or not body["project"].strip():
                raise ValueError("A project name is required")
            result = await asyncio.to_thread(reorder_uploads, body["project"], body.get("order"))
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except (TypeError, KeyError):
            return web.json_response({"error": "Invalid project or order"}, status=400)
        except OSError:
            logger.exception("Failed to reorder the uploaded videos")
            return web.json_response({"error": "保存失败：没有写入权限或文件正被占用。"}, status=409)
        prompt_server.send_sync("h3_lvm/uploads_changed",
                                {"scope": UPLOAD_SCOPE, "project": result["project"],
                                 "segment_id": None, "action": "reorder"})
        return web.json_response(result, headers={"Cache-Control": "no-store"})
    @routes.get("/h3_lvm/segments")
    async def handle_segments(request):
        """Return enriched segment list for a project."""
        project = request.rel_url.query.get("project", DEFAULT_PROJECT)
        project = sanitize_project_name(project)
        data = await asyncio.to_thread(list_project, project)
        return web.json_response(data, headers={"Cache-Control": "no-store"})

    @routes.get("/h3_lvm/video_files")
    async def handle_video_files(request):
        """List one input directory for H3 Video Loader; no upload or file bytes."""
        try:
            data = await asyncio.to_thread(
                list_video_directory, request.rel_url.query.get("directory", ""))
        except (OSError, ValueError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(data, headers={"Cache-Control": "no-store"})

    @routes.get("/h3_lvm/video_file_info")
    async def handle_video_file_info(request):
        """Probe only the selected file below input, never an arbitrary disk path."""
        try:
            data = await asyncio.to_thread(
                video_file_info, request.rel_url.query.get("path", ""))
        except (OSError, ValueError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(data, headers={"Cache-Control": "no-store"})

    @routes.post("/h3_lvm/source_preview")
    async def handle_source_preview_ticket(request):
        """Create a short-lived ticket for the path explicitly chosen by the user."""
        blocked = _csrf_block(request)
        if blocked is not None:
            return blocked
        if request.content_type != "application/json":
            return web.json_response({"error": "Expected JSON"}, status=415)
        try:
            payload = await request.json()
            data = await asyncio.to_thread(
                create_source_preview,
                payload.get("video", ""), payload.get("custom_path", ""),
            )
        except (OSError, ValueError, TypeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(data, headers={"Cache-Control": "no-store"})

    @routes.post("/h3_lvm/uploads/preview")
    async def handle_upload_preview_ticket(request):
        blocked = _csrf_block(request)
        if blocked is not None:
            return blocked
        if request.content_type != "application/json":
            return web.json_response({"error": "Expected JSON"}, status=415)
        try:
            payload = await request.json()
            data = await asyncio.to_thread(
                create_upload_preview,
                payload.get("project", ""), payload.get("segment_id"),
            )
        except (OSError, ValueError, TypeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(data, headers={"Cache-Control": "no-store"})

    @routes.post("/h3_lvm/system_video_picker")
    async def handle_system_video_picker(request):
        """Open a native dialog on the ComfyUI host, not on a remote browser."""
        blocked = _csrf_block(request)
        if blocked is not None:
            return blocked
        try:
            data = await asyncio.to_thread(choose_system_video)
        except (OSError, ValueError, RuntimeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(data, headers={"Cache-Control": "no-store"})

    @routes.post("/h3_lvm/source_preview_proxy")
    async def handle_source_preview_proxy(request):
        """Build a cached H.264 proxy only for a previously authorized source ticket."""
        blocked = _csrf_block(request)
        if blocked is not None:
            return blocked
        if request.content_type != "application/json":
            return web.json_response({"error": "Expected JSON"}, status=415)
        try:
            data = await asyncio.to_thread(
                create_compatible_source_preview, request.rel_url.query.get("ticket", ""))
        except (OSError, ValueError, RuntimeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(data, headers={"Cache-Control": "no-store"})

    @routes.get("/h3_lvm/source_preview")
    async def handle_source_preview(request):
        """FileResponse streams bytes and handles Range without decoding video."""
        try:
            path = await asyncio.to_thread(
                source_preview_path, request.rel_url.query.get("ticket", ""),
                request.rel_url.query.get("proxy") == "1")
        except (OSError, ValueError) as exc:
            return web.json_response({"error": str(exc)}, status=404)
        return web.FileResponse(path, headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        })



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
