from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .agent import agent_manager, list_workspace_files
from .chat import chat_manager
from .config import config_manager
from .engine import engine_manager
from .hardware import get_hardware_info, get_realtime_metrics
from .comfy_workflows import fetch_comfyui_workflow_raw
from .media import IMAGES_DIR, LIPSYNC_DIR, VIDEOS_DIR, media_manager
from .video_backends import probe_comfyui
from .models import (
    download_manager,
    get_recommended_models,
    import_local_gguf,
    list_huggingface_repo_files,
    scan_local_models,
    search_huggingface_gguf,
)
from .prompts import add_custom_prompt, delete_custom_prompt, list_prompt_library
from .scheduler import scheduler_manager
from .tiering import plan_auto_tiering

router = APIRouter(prefix="/api")
SERVER_STARTED_AT = time.time()


# ---------- Health & Hardware ----------

@router.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "app": "L3M Studio",
        "version": "1.2.0",
        "started_at": SERVER_STARTED_AT,
    }


@router.get("/hardware")
async def hardware() -> Dict[str, Any]:
    return get_hardware_info()


@router.get("/monitor")
async def monitor() -> Dict[str, Any]:
    pid = engine_manager.process.pid if (engine_manager.process and engine_manager.process.returncode is None) else None
    return get_realtime_metrics(engine_pid=pid)


# ---------- Config / Settings ----------

@router.get("/settings")
async def get_settings() -> Dict[str, Any]:
    return config_manager.config.model_dump()


@router.put("/settings")
async def update_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    updated = config_manager.update(patch)
    return updated.model_dump()


# ---------- Models & HuggingFace ----------

@router.get("/models/local")
async def models_local() -> Dict[str, Any]:
    items = scan_local_models()
    return {
        "models": items,
        "counts": {
            "total": len(items),
            "llm": sum(1 for m in items if m["category"] == "llm"),
            "image": sum(1 for m in items if m["category"] == "image"),
            "video": sum(1 for m in items if m["category"] == "video"),
            "lipsync": sum(1 for m in items if m["category"] == "lipsync"),
            "component": sum(1 for m in items if m["category"] == "component"),
        },
        "model_dirs": config_manager.config.model_dirs,
    }


@router.get("/models/recommended")
async def models_recommended() -> Dict[str, Any]:
    return {"models": get_recommended_models()}


@router.get("/models/hf/search")
async def hf_search(q: str = Query(default="Qwen3 GGUF"), limit: int = Query(default=20)) -> Dict[str, Any]:
    try:
        results = await search_huggingface_gguf(q, limit=limit)
        return {"results": results}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"搜尋 HuggingFace 失敗：{exc}")


@router.get("/models/hf/files")
async def hf_files(repo: str = Query(...)) -> Dict[str, Any]:
    try:
        files = await list_huggingface_repo_files(repo)
        return {"repo": repo, "files": files}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"讀取模型檔案清單失敗：{exc}")


class DownloadReq(BaseModel):
    repo: str
    filename: str


@router.post("/models/download")
async def start_download(req: DownloadReq) -> Dict[str, Any]:
    return download_manager.start_hf_download(req.repo, req.filename)


@router.get("/models/downloads")
async def list_downloads() -> Dict[str, Any]:
    return {"tasks": download_manager.list_tasks()}


@router.delete("/models/downloads/{task_id}")
async def cancel_download(task_id: str) -> Dict[str, Any]:
    ok = download_manager.cancel_task(task_id)
    return {"cancelled": ok}


class ImportModelReq(BaseModel):
    path: str
    copy_file: bool = False


@router.post("/models/import")
async def import_model(req: ImportModelReq) -> Dict[str, Any]:
    try:
        return import_local_gguf(req.path, copy_file=req.copy_file)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------- Auto-Tiering Preview ----------

class TieringPreviewReq(BaseModel):
    model_id: str
    context_setting: str = "auto"
    kv_cache_q8: bool = True
    flash_attn: bool = True
    no_mmap: bool = False


@router.post("/tiering/preview")
async def tiering_preview(req: TieringPreviewReq) -> Dict[str, Any]:
    models = scan_local_models()
    target = next((m for m in models if m["id"] == req.model_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="找不到指定模型")
    hw = get_hardware_info()
    return plan_auto_tiering(
        target,
        hw,
        context_setting=req.context_setting,
        kv_cache_q8=req.kv_cache_q8,
        flash_attn=req.flash_attn,
        reserve_ram_gb=config_manager.config.reserve_ram_gb,
        no_mmap=req.no_mmap,
    )


# ---------- Engine & Run ----------

@router.get("/engine/info")
async def engine_info() -> Dict[str, Any]:
    return engine_manager.get_engine_info()


@router.get("/engine/status")
async def engine_status() -> Dict[str, Any]:
    return engine_manager.get_status()


class InstallEngineReq(BaseModel):
    backend: Optional[str] = None


@router.post("/engine/install")
async def install_engine(req: InstallEngineReq) -> Dict[str, Any]:
    return engine_manager.start_engine_install(backend=req.backend)


@router.post("/engine/install/cancel")
async def cancel_engine_install() -> Dict[str, Any]:
    return engine_manager.cancel_engine_install()


@router.post("/engine/import-archive")
async def import_engine_archive(file: UploadFile = File(...)) -> Dict[str, Any]:
    suffix = ".tar.gz" if (file.filename or "").lower().endswith(".tar.gz") else ".zip"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        bin_path = engine_manager.import_engine_archive(tmp_path)
        return {"installed": True, "binary_path": bin_path}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        tmp_path.unlink(missing_ok=True)


class StartModelReq(BaseModel):
    model_id: str
    context_setting: str = "auto"
    thinking: bool = True
    lan_access: bool = False
    flash_attn: bool = True
    kv_cache_q8: bool = True
    no_mmap: bool = False
    auto_recovery: bool = True
    port: Optional[int] = None
    custom_ngl: Optional[int] = None
    extra_cli_args: str = ""


@router.post("/engine/start")
async def engine_start(req: StartModelReq) -> Dict[str, Any]:
    try:
        return await engine_manager.start_model(**req.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/engine/stop")
async def engine_stop() -> Dict[str, Any]:
    await engine_manager.stop_all_llama_servers()
    return engine_manager.get_status()


@router.get("/engine/logs/stream")
async def engine_logs_stream() -> StreamingResponse:
    q = engine_manager.subscribe_logs()

    async def gen():
        try:
            for existing in list(engine_manager.logs)[-80:]:
                yield f"data: {json.dumps({'line': existing}, ensure_ascii=False)}\n\n"
            while True:
                try:
                    line = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps({'line': line}, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            engine_manager.unsubscribe_logs(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------- Chat & Code ----------

@router.get("/chats")
async def list_chats() -> Dict[str, Any]:
    return {"chats": chat_manager.list_chats()}


class CreateChatReq(BaseModel):
    title: str = "新對話"
    system_prompt: str = ""


@router.post("/chats")
async def create_chat(req: CreateChatReq) -> Dict[str, Any]:
    return chat_manager.create_chat(title=req.title, system_prompt=req.system_prompt)


@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str) -> Dict[str, Any]:
    try:
        return chat_manager.get_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="找不到對話紀錄")


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str) -> Dict[str, Any]:
    return {"deleted": chat_manager.delete_chat(chat_id)}


class ChatStreamReq(BaseModel):
    message: str
    attachments: List[Dict[str, Any]] = []
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 4096
    thinking: bool = True
    system_prompt: Optional[str] = None
    use_external_api: bool = False


@router.post("/chats/{chat_id}/stream")
async def stream_chat(chat_id: str, req: ChatStreamReq) -> StreamingResponse:
    return StreamingResponse(
        chat_manager.stream_completion(
            chat_id=chat_id,
            user_text=req.message,
            attachments=req.attachments,
            temperature=req.temperature,
            top_p=req.top_p,
            max_tokens=req.max_tokens,
            thinking=req.thinking,
            system_prompt=req.system_prompt,
            use_external_api=req.use_external_api,
        ),
        media_type="text/event-stream",
    )


# ---------- Media Studio (Image / Video / Lipsync) ----------

@router.get("/media/models")
async def media_models() -> Dict[str, Any]:
    return await media_manager.get_media_models_async()


@router.get("/media/comfyui/status")
async def media_comfyui_status(force: bool = Query(default=False)) -> Dict[str, Any]:
    return await probe_comfyui(force=force)


@router.post("/media/comfyui/test")
async def media_comfyui_test(body: Dict[str, Any]) -> Dict[str, Any]:
    url = str(body.get("url") or "").strip() or None
    return await probe_comfyui(base_url=url, force=True, timeout=4.0)


@router.get("/media/comfyui/workflows")
async def media_comfyui_workflows(
    kind: Optional[str] = Query(default=None),
    force: bool = Query(default=False),
) -> Dict[str, Any]:
    status = await probe_comfyui(force=force)
    items = status.get("workflows") or []
    if kind in ("image", "video"):
        items = [w for w in items if w.get("kind") == kind or w.get("source") == "user"]
    return {"online": status.get("online", False), "url": status.get("url", ""), "workflows": items}


@router.get("/media/comfyui/workflows/detail")
async def media_comfyui_workflow_detail(workflow_id: str = Query(...)) -> Dict[str, Any]:
    status = await probe_comfyui()
    if not status.get("online"):
        raise HTTPException(status_code=503, detail="ComfyUI 未連線")
    try:
        raw, name = await fetch_comfyui_workflow_raw(status["url"], workflow_id)
        return {"workflow_id": workflow_id, "name": name, "workflow": raw}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"讀取 ComfyUI 工作流失敗：{exc}")


@router.get("/media/gallery")
async def media_gallery(kind: Optional[str] = Query(default=None)) -> Dict[str, Any]:
    return {"items": media_manager.list_gallery(kind=kind)}


@router.delete("/media/gallery/{item_id}")
async def media_gallery_delete(item_id: str) -> Dict[str, Any]:
    return {"deleted": media_manager.delete_gallery_item(item_id)}


@router.get("/media/files/{folder}/{filename}")
async def media_serve_file(folder: str, filename: str):
    safe_name = Path(filename).name
    base = IMAGES_DIR if folder == "images" else VIDEOS_DIR if folder == "videos" else LIPSYNC_DIR
    target = base / safe_name
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="找不到作品檔案")
    return FileResponse(str(target))


@router.post("/media/open-folder")
async def media_open_folder(body: Dict[str, Any]) -> Dict[str, Any]:
    opened = media_manager.open_outputs_folder(str(body.get("kind", "images")))
    return {"path": opened}


@router.post("/media/engine/install-sd")
async def media_install_sd() -> Dict[str, Any]:
    return media_manager.start_sd_engine_install()


@router.get("/media/jobs")
async def media_jobs() -> Dict[str, Any]:
    return {"jobs": media_manager.list_jobs()}


@router.post("/media/jobs/{job_id}/cancel")
async def media_cancel_job(job_id: str) -> Dict[str, Any]:
    return media_manager.cancel_job(job_id)


@router.post("/media/jobs/cancel-all")
async def media_cancel_all_jobs() -> Dict[str, Any]:
    return media_manager.cancel_all_running()


@router.post("/media/generate/image")
async def media_gen_image(params: Dict[str, Any]) -> Dict[str, Any]:
    return media_manager.start_image_generation(params)


@router.post("/media/generate/video")
async def media_gen_video(params: Dict[str, Any]) -> Dict[str, Any]:
    return media_manager.start_video_generation(params)


@router.post("/media/generate/lipsync")
async def media_gen_lipsync(params: Dict[str, Any]) -> Dict[str, Any]:
    return media_manager.start_lipsync_generation(params)


# ---------- Local Agent ----------

@router.get("/agent/sessions")
async def agent_list_sessions() -> Dict[str, Any]:
    return {"sessions": agent_manager.list_sessions()}


@router.post("/agent/sessions")
async def agent_create_session(body: Dict[str, Any]) -> Dict[str, Any]:
    return agent_manager.create_session(
        workspace=str(body.get("workspace", "")),
        title=str(body.get("title", "新 Agent 任務")),
    )


@router.get("/agent/sessions/{session_id}")
async def agent_get_session(session_id: str) -> Dict[str, Any]:
    try:
        sess = agent_manager.get_session(session_id)
        sess["files"] = list_workspace_files(sess.get("workspace", ""))
        return sess
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="找不到 Agent 任務")


@router.delete("/agent/sessions/{session_id}")
async def agent_delete_session(session_id: str) -> Dict[str, Any]:
    return {"deleted": agent_manager.delete_session(session_id)}


@router.get("/agent/workspace-files")
async def agent_workspace_files(workspace: str = Query(...)) -> Dict[str, Any]:
    return {"files": list_workspace_files(workspace)}


@router.post("/agent/sessions/{session_id}/run")
async def agent_run_stream(session_id: str, body: Dict[str, Any]) -> StreamingResponse:
    return StreamingResponse(
        agent_manager.run_task_stream(
            session_id=session_id,
            prompt=str(body.get("prompt", "")),
            workspace=body.get("workspace"),
            permission_mode=str(body.get("permission_mode", "workspace_only")),
            use_external_api=bool(body.get("use_external_api", False)),
            max_steps=int(body.get("max_steps", 6)),
        ),
        media_type="text/event-stream",
    )


# ---------- Scheduled Tasks (定時) ----------

@router.get("/schedules")
async def schedules_list() -> Dict[str, Any]:
    return {"tasks": scheduler_manager.list_tasks()}


@router.post("/schedules")
async def schedules_create(body: Dict[str, Any]) -> Dict[str, Any]:
    return scheduler_manager.create_task(body)


@router.put("/schedules/{task_id}")
async def schedules_update(task_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return scheduler_manager.update_task(task_id, body)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="找不到排程任務")


@router.delete("/schedules/{task_id}")
async def schedules_delete(task_id: str) -> Dict[str, Any]:
    return {"deleted": scheduler_manager.delete_task(task_id)}


@router.post("/schedules/{task_id}/run")
async def schedules_run_now(task_id: str) -> Dict[str, Any]:
    try:
        return await scheduler_manager.run_now(task_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="找不到排程任務")


# ---------- Prompt Library (提示詞庫 & 實用反向提示詞) ----------

@router.get("/prompts")
async def get_prompts(kind: Optional[str] = Query(default=None)) -> Dict[str, Any]:
    return list_prompt_library(kind=kind)


@router.post("/prompts")
async def create_prompt(body: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return add_custom_prompt(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/prompts/{prompt_id}")
async def remove_prompt(prompt_id: str) -> Dict[str, Any]:
    return {"deleted": delete_custom_prompt(prompt_id)}
