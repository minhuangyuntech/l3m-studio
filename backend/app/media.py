from __future__ import annotations

import asyncio
import base64
import json
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .config import APP_HOME, ENGINES_DIR, config_manager
from .engine import engine_manager
from .hardware import get_hardware_info
from .models import scan_local_models

OUTPUTS_DIR = APP_HOME / "outputs"
IMAGES_DIR = OUTPUTS_DIR / "images"
VIDEOS_DIR = OUTPUTS_DIR / "videos"
LIPSYNC_DIR = OUTPUTS_DIR / "lipsync"
UPLOADS_DIR = OUTPUTS_DIR / "uploads"
GALLERY_META_PATH = OUTPUTS_DIR / "gallery.json"

for _d in (OUTPUTS_DIR, IMAGES_DIR, VIDEOS_DIR, LIPSYNC_DIR, UPLOADS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _discover_sd_cli() -> str:
    cfg_path = getattr(config_manager.config, "sd_cli_path", "")
    if cfg_path and Path(cfg_path).exists():
        return str(Path(cfg_path).resolve())

    names = ["sd-cli.exe", "sd.exe"] if platform.system() == "Windows" else ["sd-cli", "sd"]
    for n in names:
        hit = shutil.which(n)
        if hit:
            return str(Path(hit).resolve())
    if ENGINES_DIR.exists():
        for n in names:
            for match in ENGINES_DIR.rglob(n):
                if match.is_file():
                    return str(match.resolve())
    return ""


def _resolve_media_components(model: Dict[str, Any]) -> Dict[str, str]:
    """Auto-pair GGUF diffusion model with its VAE & text encoder inside D:\\AI-Models\\image\\common."""
    model_path = Path(model["path"])
    low = model["filename"].lower()
    common_dir = model_path.parent.parent / "common"
    if not common_dir.exists():
        common_dir = Path("D:/AI-Models/image/common")

    comps: Dict[str, str] = {"model": str(model_path)}
    if not common_dir.exists():
        return comps

    def _find(pattern: str, exclude: str = "") -> str:
        for p in sorted(common_dir.iterdir(), key=lambda x: x.name.lower()):
            name_low = p.name.lower()
            if pattern in name_low and (not exclude or exclude not in name_low):
                return str(p.resolve())
        return ""

    if "z_image" in low or "z-image" in low:
        comps["vae"] = _find("ae.safetensors")
        comps["llm"] = _find("qwen3-4b", exclude="mmproj")
        comps["preset"] = "z-image"
    elif "qwen_image" in low or "qwen-image" in low:
        comps["vae"] = _find("qwen_image_2.1_vae")
        comps["llm"] = _find("qwen3vl-8b", exclude="mmproj")
        comps["mmproj"] = _find("mmproj-qwen3vl-8b")
        comps["preset"] = "qwen-image"
    elif "minimax_h3_image" in low:
        comps["vae"] = _find("minimax_h3_image_vae")
        comps["llm"] = _find("qwen3vl_32b_minimax_h3", exclude="mmproj")
        comps["preset"] = "minimax-image"
    elif "wan2.2" in low or "wan2_2" in low:
        comps["vae"] = _find("wan2.2_vae")
        comps["t5xxl"] = _find("umt5-xxl")
        comps["preset"] = "wan2.2"
    elif "minimax_h3" in low:
        comps["vae"] = _find("minimax_h3_video_vae")
        comps["audio_vae"] = _find("minimax_h3_audio_vae")
        comps["llm"] = _find("qwen3vl_32b_minimax_h3", exclude="mmproj")
        comps["preset"] = "minimax-video"
    return comps


def list_loras() -> List[Dict[str, str]]:
    loras: List[Dict[str, str]] = []
    for root_str in config_manager.config.model_dirs:
        lora_dir = Path(root_str) / "image" / "loras"
        if not lora_dir.exists():
            continue
        for p in sorted(lora_dir.rglob("*")):
            if p.is_file() and p.suffix.lower() in (".safetensors", ".gguf", ".pt", ".ckpt"):
                loras.append({"name": p.stem, "filename": p.name, "path": str(p.resolve())})
    return loras


def _load_gallery() -> List[Dict[str, Any]]:
    if not GALLERY_META_PATH.exists():
        return []
    try:
        items = json.loads(GALLERY_META_PATH.read_text(encoding="utf-8"))
        return [i for i in items if Path(i.get("file_path", "")).exists()]
    except Exception:
        return []


def _save_gallery(items: List[Dict[str, Any]]) -> None:
    GALLERY_META_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_base64_upload(data_url: str, prefix: str) -> Path:
    header, b64 = data_url.split(",", 1) if "," in data_url else ("", data_url)
    ext = ".png"
    if "jpeg" in header or "jpg" in header:
        ext = ".jpg"
    elif "webp" in header:
        ext = ".webp"
    elif "mp3" in header or "mpeg" in header:
        ext = ".mp3"
    elif "wav" in header:
        ext = ".wav"
    elif "mp4" in header:
        ext = ".mp4"
    out = UPLOADS_DIR / f"{prefix}_{uuid.uuid4().hex[:10]}{ext}"
    out.write_bytes(base64.b64decode(b64))
    return out


class JobCancelledError(Exception):
    pass


class MediaManager:
    def __init__(self) -> None:
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.sd_install_state: Dict[str, Any] = {
            "status": "idle",
            "asset_name": "",
            "release_tag": "",
            "percent": 0.0,
            "speed_mb_s": 0.0,
            "error": "",
        }
        self._active_proc: Optional[asyncio.subprocess.Process] = None
        self._job_procs: Dict[str, asyncio.subprocess.Process] = {}
        self._cancelled_jobs: set[str] = set()

    def _force_kill_proc(self, proc: Optional[asyncio.subprocess.Process]) -> None:
        if not proc or proc.returncode is not None:
            return
        pid = proc.pid
        try:
            if platform.system() == "Windows" and pid:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        self._cancelled_jobs.add(job_id)
        proc = self._job_procs.pop(job_id, None)
        if proc:
            self._force_kill_proc(proc)
        if self._active_proc and (proc is None or self._active_proc is proc):
            self._force_kill_proc(self._active_proc)
            self._active_proc = None
        job = self.jobs.get(job_id)
        if job and job.get("status") == "running":
            job["status"] = "cancelled"
            job["message"] = "已強制取消目前作業並釋放顯存"
            job["error"] = ""
        return {"cancelled": True, "job_id": job_id}

    def cancel_all_running(self) -> Dict[str, Any]:
        cancelled_ids: List[str] = []
        for jid, job in list(self.jobs.items()):
            if job.get("status") == "running":
                self.cancel_job(jid)
                cancelled_ids.append(jid)
        if self._active_proc:
            self._force_kill_proc(self._active_proc)
            self._active_proc = None
        return {"cancelled": True, "job_ids": cancelled_ids}

    def get_media_models(self) -> Dict[str, Any]:
        all_models = scan_local_models()
        images = [m for m in all_models if m["category"] == "image"]
        videos = [m for m in all_models if m["category"] == "video"]
        lipsync = [m for m in all_models if m["category"] == "lipsync"]

        for m in images + videos:
            m["components"] = _resolve_media_components(m)

        sd_cli = _discover_sd_cli()
        lipsync_env = Path("D:/AI-Models/lipsync/env/Scripts/python.exe")
        if platform.system() != "Windows":
            lipsync_env = Path("D:/AI-Models/lipsync/env/bin/python")

        ext_llms = engine_manager.find_external_llama_servers()
        llm_is_running = engine_manager.status in ("running", "starting") or bool(ext_llms)
        llm_name = (engine_manager.active_model or {}).get("name", "") or (
            f"{ext_llms[0]['name']} (背景殘留 PID {ext_llms[0]['pid']})" if ext_llms else ""
        )

        return {
            "image_models": images,
            "video_models": videos,
            "lipsync_models": lipsync,
            "loras": list_loras(),
            "engines": {
                "sd_cli_installed": bool(sd_cli),
                "sd_cli_path": sd_cli,
                "sd_install_state": self.sd_install_state,
                "comfyui_url": config_manager.config.comfyui_url,
                "custom_image_api": config_manager.config.custom_image_api,
                "lipsync_env_ready": lipsync_env.exists(),
                "lipsync_env_path": str(lipsync_env) if lipsync_env.exists() else "",
                "llm_running": llm_is_running,
                "llm_model_name": llm_name,
            },
            "outputs_dir": str(OUTPUTS_DIR),
        }

    def list_gallery(self, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        items = _load_gallery()
        if kind:
            items = [i for i in items if i.get("kind") == kind]
        items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return items

    def delete_gallery_item(self, item_id: str) -> bool:
        items = _load_gallery()
        kept: List[Dict[str, Any]] = []
        removed = False
        for item in items:
            if item.get("id") == item_id:
                removed = True
                fp = Path(item.get("file_path", ""))
                fp.unlink(missing_ok=True)
            else:
                kept.append(item)
        if removed:
            _save_gallery(kept)
        return removed

    def open_outputs_folder(self, kind: str = "images") -> str:
        target = IMAGES_DIR if kind == "images" else VIDEOS_DIR if kind == "videos" else LIPSYNC_DIR
        target.mkdir(parents=True, exist_ok=True)
        sys_name = platform.system()
        try:
            if sys_name == "Windows":
                os.startfile(str(target))  # type: ignore[attr-defined]
            elif sys_name == "Darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception:
            pass
        return str(target)

    # ---------- One-click stable-diffusion.cpp installer ----------

    def start_sd_engine_install(self) -> Dict[str, Any]:
        if self.sd_install_state["status"] in ("fetching", "downloading", "extracting"):
            return self.sd_install_state
        asyncio.create_task(self._download_sd_cpp())
        return self.sd_install_state

    async def _download_sd_cpp(self) -> None:
        hw = get_hardware_info()
        backend = hw["recommended_backend"]
        sys_name = platform.system().lower()
        arch = platform.machine().lower()
        self.sd_install_state.update(
            {"status": "fetching", "asset_name": "", "release_tag": "", "percent": 0.0, "speed_mb_s": 0.0, "error": ""}
        )
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                rel = await client.get(
                    "https://api.github.com/repos/leejet/stable-diffusion.cpp/releases/latest",
                    headers={"Accept": "application/vnd.github+json"},
                )
                rel.raise_for_status()
                data = rel.json()
                tag = data.get("tag_name", "latest")
                assets = [a for a in data.get("assets", []) if a["name"].endswith((".zip", ".tar.gz"))]

                chosen = None
                if sys_name == "windows":
                    win = [a for a in assets if "win" in a["name"].lower() and "x64" in a["name"].lower()]
                    if backend == "cuda":
                        chosen = next((a for a in win if "cuda" in a["name"].lower() and "cudart" not in a["name"].lower()), None)
                    if not chosen and backend == "vulkan":
                        chosen = next((a for a in win if "vulkan" in a["name"].lower()), None)
                    if not chosen:
                        chosen = next((a for a in win if "avx2" in a["name"].lower()), win[0] if win else None)
                elif sys_name == "darwin":
                    mac = [a for a in assets if "macos" in a["name"].lower() or "osx" in a["name"].lower()]
                    chosen = next((a for a in mac if ("arm64" in a["name"].lower()) == ("arm" in arch)), mac[0] if mac else None)
                else:
                    lin = [a for a in assets if "linux" in a["name"].lower() or "ubuntu" in a["name"].lower()]
                    chosen = lin[0] if lin else None

                if not chosen:
                    raise RuntimeError(f"找不到適合 {sys_name}/{backend} 的 stable-diffusion.cpp 預編譯版本")

                self.sd_install_state.update(
                    {"status": "downloading", "release_tag": tag, "asset_name": chosen["name"]}
                )
                archive_path = ENGINES_DIR / chosen["name"]
                t0 = time.monotonic()
                got = 0
                async with client.stream("GET", chosen["browser_download_url"]) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("content-length", "0"))
                    with archive_path.open("wb") as f:
                        async for chunk in resp.aiter_bytes(512 * 1024):
                            f.write(chunk)
                            got += len(chunk)
                            elapsed = max(time.monotonic() - t0, 0.05)
                            self.sd_install_state["speed_mb_s"] = round((got / elapsed) / (1024 * 1024), 2)
                            if total > 0:
                                self.sd_install_state["percent"] = round((got / total) * 100.0, 1)

                self.sd_install_state["status"] = "extracting"
                dest = ENGINES_DIR / f"sd-cpp-{tag}-{int(time.time())}"
                dest.mkdir(parents=True, exist_ok=True)
                if archive_path.name.lower().endswith(".zip"):
                    with zipfile.ZipFile(archive_path, "r") as zf:
                        zf.extractall(dest)
                else:
                    with tarfile.open(archive_path, "r:gz") as tf:
                        tf.extractall(dest)
                archive_path.unlink(missing_ok=True)

                exe_names = ["sd-cli.exe", "sd.exe"] if platform.system() == "Windows" else ["sd-cli", "sd"]
                found = None
                for en in exe_names:
                    found = next(dest.rglob(en), None)
                    if found:
                        break
                if not found:
                    raise FileNotFoundError("解壓縮後找不到 sd-cli / sd 執行檔")
                if platform.system() != "Windows":
                    found.chmod(found.stat().st_mode | stat.S_IEXEC)

                config_manager.update({"sd_cli_path": str(found.resolve())})
                self.sd_install_state.update({"status": "completed", "percent": 100.0})
        except Exception as exc:
            self.sd_install_state.update({"status": "error", "error": str(exc)})

    # ---------- Generation Jobs (Image / Video / Lipsync) ----------

    def list_jobs(self) -> List[Dict[str, Any]]:
        return sorted(self.jobs.values(), key=lambda x: x["created_at"], reverse=True)[:30]

    def start_image_generation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "kind": "image",
            "status": "running",
            "progress": 5,
            "message": "正在準備繪圖引擎與模型權重...",
            "params": {k: v for k, v in params.items() if k != "ref_image_data_url"},
            "created_at": time.time(),
            "elapsed_seconds": 0.0,
            "outputs": [],
            "error": "",
        }
        self.jobs[job_id] = job
        asyncio.create_task(self._run_image_job(job, params))
        return job

    async def _run_image_job(self, job: Dict[str, Any], params: Dict[str, Any]) -> None:
        t0 = time.monotonic()
        try:
            if params.get("auto_unload_llm", True) and (
                engine_manager.status in ("running", "starting")
                or engine_manager.find_external_llama_servers()
            ):
                job["message"] = "正在自動停止背景 LLM 釋放顯卡 VRAM..."
                await engine_manager.stop_all_llama_servers()
                await asyncio.sleep(1.0)

            all_models = scan_local_models()
            model = next((m for m in all_models if m["id"] == params.get("model_id")), None)
            if not model:
                raise ValueError("找不到選定的畫圖模型")

            comps = _resolve_media_components(model)
            sd_cli = _discover_sd_cli()
            custom_api = config_manager.config.custom_image_api.strip()
            count = max(1, min(int(params.get("batch_count", 1)), 4))
            width = int(params.get("width", 1024))
            height = int(params.get("height", 1024))
            steps = int(params.get("steps", 8))
            seed = params.get("seed")
            prompt = str(params.get("prompt", "")).strip()
            neg_prompt = str(params.get("negative_prompt", "")).strip()

            ref_path: Optional[Path] = None
            if params.get("ref_image_data_url"):
                ref_path = _save_base64_upload(params["ref_image_data_url"], "ref")

            if custom_api:
                job["message"] = f"透過外部繪圖服務 ({custom_api}) 生成中..."
                async with httpx.AsyncClient(timeout=300.0) as client:
                    resp = await client.post(
                        f"{custom_api.rstrip('/')}/images/generations",
                        json={
                            "model": model["name"],
                            "prompt": prompt,
                            "n": count,
                            "size": f"{width}x{height}",
                            "response_format": "b64_json",
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    for idx, item in enumerate(data.get("data", [])):
                        out_name = f"img_{int(time.time())}_{job['id']}_{idx}.png"
                        out_path = IMAGES_DIR / out_name
                        if item.get("b64_json"):
                            out_path.write_bytes(base64.b64decode(item["b64_json"]))
                        elif item.get("url"):
                            img_r = await client.get(item["url"])
                            out_path.write_bytes(img_r.content)
                        self._register_output(job, model, out_path, "image", params, time.monotonic() - t0)
            elif sd_cli:
                for idx in range(count):
                    if job["id"] in self._cancelled_jobs:
                        raise JobCancelledError()
                    job["progress"] = int(10 + (idx / count) * 80)
                    job["message"] = f"正在使用 stable-diffusion.cpp 渲染第 {idx + 1}/{count} 張 ({width}×{height})..."
                    out_name = f"img_{int(time.time())}_{job['id']}_{idx}.png"
                    out_path = IMAGES_DIR / out_name
                    prompt_with_lora = prompt
                    lora_path_str = str(params.get("lora_path", "") or "").strip()
                    lora_strength = float(params.get("lora_strength", 0.8) or 0.8)
                    if lora_path_str and Path(lora_path_str).exists():
                        lora_stem = Path(lora_path_str).stem
                        if f"<lora:{lora_stem}" not in prompt_with_lora:
                            prompt_with_lora = f"{prompt_with_lora}, <lora:{lora_stem}:{lora_strength:.2f}>"

                    cmd = [
                        sd_cli,
                        "--diffusion-model",
                        comps["model"],
                        "-p",
                        prompt_with_lora,
                        "-W",
                        str(width),
                        "-H",
                        str(height),
                        "--steps",
                        str(steps),
                        "-o",
                        str(out_path),
                        "--offload-to-cpu",
                        "--flash-attn",
                        "on",
                    ]
                    if comps.get("vae"):
                        cmd.extend(["--vae", comps["vae"]])
                    if comps.get("llm"):
                        cmd.extend(["--llm", comps["llm"]])
                    if comps.get("mmproj") and ref_path:
                        cmd.extend(["--llm_vision", comps["mmproj"]])
                    preset = comps.get("preset", "")
                    if preset == "z-image":
                        cmd.extend(["--cfg-scale", "1.0"])
                    elif preset == "qwen-image":
                        cmd.extend(["--cfg-scale", "2.5"])
                        if not neg_prompt:
                            neg_prompt = " "
                    elif preset == "minimax-image":
                        # MiniMax-H3 Qwen3VL-32B conditioner rejects 0-token empty negative prompts when CFG > 1.0
                        cmd.extend(["--cfg-scale", "3.5" if neg_prompt else "1.0"])
                    if neg_prompt:
                        cmd.extend(["-n", neg_prompt])
                    if seed is not None and str(seed).strip() != "":
                        cmd.extend(["-s", str(int(seed) + idx)])
                    if ref_path:
                        cmd.extend(["-r" if preset == "qwen-image" else "-i", str(ref_path)])
                    if lora_path_str and Path(lora_path_str).exists():
                        cmd.extend(["--lora-model-dir", str(Path(lora_path_str).parent), "--lora-apply-mode", "at_runtime"])
                    # Always enable VAE tiling (512x512 tiles) for >= 512x512 to prevent 8GB VRAM OOM/thrashing without small-tile artifacts
                    if width * height >= 512 * 512:
                        cmd.extend(["--vae-tiling", "--vae-tile-size", "512x512"])

                    await self._exec_media_cli(cmd, job)
                    if not out_path.exists():
                        raise RuntimeError("繪圖引擎執行完成但未產生輸出圖片，請確認模型與 VAE 配置。")
                    self._register_output(job, model, out_path, "image", params, time.monotonic() - t0)
            else:
                raise RuntimeError(
                    "尚未安裝本機繪圖引擎 (stable-diffusion.cpp)。請點擊右上角「一鍵安裝繪圖引擎」，或於「設定」填寫 ComfyUI / OpenAI 相容繪圖服務網址。"
                )

            job["status"] = "completed"
            job["progress"] = 100
            job["elapsed_seconds"] = round(time.monotonic() - t0, 1)
            job["message"] = f"生成完成（耗時 {job['elapsed_seconds']}s）"
        except JobCancelledError:
            job["status"] = "cancelled"
            job["elapsed_seconds"] = round(time.monotonic() - t0, 1)
            job["message"] = f"已強制取消作業（已執行 {job['elapsed_seconds']}s）"
            job["error"] = ""
        except Exception as exc:
            if job["id"] in self._cancelled_jobs:
                job["status"] = "cancelled"
                job["message"] = "已強制取消作業"
                job["error"] = ""
            else:
                job["status"] = "error"
                job["error"] = str(exc)
                job["elapsed_seconds"] = round(time.monotonic() - t0, 1)
                job["message"] = f"生成失敗：{exc}"
        finally:
            self._job_procs.pop(job["id"], None)
            self._cancelled_jobs.discard(job["id"])

    def start_video_generation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "kind": "video",
            "status": "running",
            "progress": 5,
            "message": "正在準備影片生成引擎與模型權重...",
            "params": {k: v for k, v in params.items() if not k.endswith("_data_url")},
            "created_at": time.time(),
            "elapsed_seconds": 0.0,
            "outputs": [],
            "error": "",
        }
        self.jobs[job_id] = job
        asyncio.create_task(self._run_video_job(job, params))
        return job

    async def _run_video_job(self, job: Dict[str, Any], params: Dict[str, Any]) -> None:
        t0 = time.monotonic()
        try:
            if params.get("auto_unload_llm", True) and (
                engine_manager.status in ("running", "starting")
                or engine_manager.find_external_llama_servers()
            ):
                job["message"] = "正在自動停止背景 LLM 釋放顯卡 VRAM..."
                await engine_manager.stop_all_llama_servers()
                await asyncio.sleep(1.0)

            all_models = scan_local_models()
            model = next((m for m in all_models if m["id"] == params.get("model_id")), None)
            if not model:
                raise ValueError("找不到選定的影片模型")

            comps = _resolve_media_components(model)
            sd_cli = _discover_sd_cli()
            if not sd_cli:
                raise RuntimeError(
                    "尚未安裝影片推理引擎 (stable-diffusion.cpp)。請點擊右上角「安裝引擎」或連接本機 ComfyUI 執行工作流。"
                )

            width = int(params.get("width", 832))
            height = int(params.get("height", 480))
            steps = int(params.get("steps", 20))
            duration = max(1, min(int(params.get("duration", 5)), 20))
            fps = 24 if comps.get("preset") == "minimax-video" else 16
            frames = max(17, duration * fps + 1)
            prompt = str(params.get("prompt", "")).strip()
            neg_prompt = str(params.get("negative_prompt", "")).strip()

            base_stem = f"vid_{int(time.time())}_{job['id']}"
            raw_avi_path = VIDEOS_DIR / f"{base_stem}.avi"
            out_mp4_path = VIDEOS_DIR / f"{base_stem}.mp4"
            cmd = [
                sd_cli,
                "-M",
                "vid_gen",
                "--diffusion-model",
                comps["model"],
                "-p",
                prompt,
                "-W",
                str(width),
                "-H",
                str(height),
                "--steps",
                str(steps),
                "--video-frames",
                str(frames),
                "--fps",
                str(fps),
                "-o",
                str(raw_avi_path),
                "--offload-to-cpu",
                "--flash-attn",
                "on",
                "--vae-tiling",
                "--vae-tile-size",
                "512x512",
                "--temporal-tiling",
            ]
            req_cfg = params.get("cfg_scale")
            if comps.get("preset") == "wan2.2":
                cfg_val = float(req_cfg) if req_cfg is not None else 5.0
                cmd.extend(["--cfg-scale", f"{cfg_val:.1f}", "--sampling-method", "euler", "--flow-shift", "5.0"])
                if not neg_prompt:
                    neg_prompt = "blurry, static, low quality, flickering, morphing, distorted face, watermark"
            elif comps.get("preset") == "minimax-video":
                # MiniMax-H3 base 20-step FL2VA/Ref2VA requires CFG guidance (default 4.5) and a non-empty negative prompt
                cfg_val = float(req_cfg) if req_cfg is not None else 4.5
                cmd.extend(["--cfg-scale", f"{cfg_val:.1f}", "--sampling-method", "euler"])
                if not neg_prompt:
                    neg_prompt = "blurry, pixelated, mosaic, distorted face, low quality, flickering, morphing, watermark"
            if comps.get("vae"):
                cmd.extend(["--vae", comps["vae"]])
            if comps.get("audio_vae"):
                cmd.extend(["--audio-vae", comps["audio_vae"]])
            if comps.get("t5xxl"):
                cmd.extend(["--t5xxl", comps["t5xxl"]])
            elif comps.get("llm"):
                cmd.extend(["--llm", comps["llm"]])
            if neg_prompt:
                cmd.extend(["-n", neg_prompt])
            if params.get("seed") is not None and str(params.get("seed")).strip() != "":
                cmd.extend(["-s", str(int(params["seed"]))])
            if params.get("first_frame_data_url"):
                ff = _save_base64_upload(params["first_frame_data_url"], "first")
                is_ref_model = "ref2va" in model["filename"].lower()
                cmd.extend(["-r" if is_ref_model else "-i", str(ff)])
            if params.get("last_frame_data_url"):
                lf = _save_base64_upload(params["last_frame_data_url"], "last")
                cmd.extend(["--end-img", str(lf)])

            job["message"] = f"正在渲染 {duration} 秒影片 ({width}×{height}, {steps} 步)..."
            await self._exec_media_cli(cmd, job)

            # Locate actual output produced by sd-cli (.avi / .webm) and convert to H.264 MP4 for smooth playback
            produced: Optional[Path] = None
            for cand in (raw_avi_path, VIDEOS_DIR / f"{base_stem}.webm", out_mp4_path):
                if cand.exists() and cand.stat().st_size > 1024:
                    produced = cand
                    break
            if not produced:
                raise RuntimeError("影片引擎執行完畢但未產生輸出檔案，請確認模型與參數。")

            final_out = produced
            ffmpeg_bin = shutil.which("ffmpeg")
            if ffmpeg_bin and produced.suffix.lower() != ".mp4":
                job["progress"] = 98
                job["message"] = "正在將影片轉檔封裝為瀏覽器相容 MP4 (H.264/AAC)..."
                ff_kwargs: Dict[str, Any] = {
                    "stdout": asyncio.subprocess.PIPE,
                    "stderr": asyncio.subprocess.STDOUT,
                }
                if platform.system() == "Windows":
                    ff_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                ff_proc = await asyncio.create_subprocess_exec(
                    ffmpeg_bin,
                    "-y",
                    "-i",
                    str(produced),
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-crf",
                    "18",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                    str(out_mp4_path),
                    **ff_kwargs,
                )
                await ff_proc.communicate()
                if ff_proc.returncode == 0 and out_mp4_path.exists() and out_mp4_path.stat().st_size > 1024:
                    produced.unlink(missing_ok=True)
                    final_out = out_mp4_path

            self._register_output(job, model, final_out, "video", params, time.monotonic() - t0)
            job["status"] = "completed"
            job["progress"] = 100
            job["elapsed_seconds"] = round(time.monotonic() - t0, 1)
            job["message"] = f"影片生成完成（耗時 {job['elapsed_seconds']}s）"
        except JobCancelledError:
            job["status"] = "cancelled"
            job["elapsed_seconds"] = round(time.monotonic() - t0, 1)
            job["message"] = f"已強制取消影片作業（已執行 {job['elapsed_seconds']}s）"
            job["error"] = ""
        except Exception as exc:
            if job["id"] in self._cancelled_jobs:
                job["status"] = "cancelled"
                job["message"] = "已強制取消影片作業"
                job["error"] = ""
            else:
                job["status"] = "error"
                job["error"] = str(exc)
                job["elapsed_seconds"] = round(time.monotonic() - t0, 1)
                job["message"] = f"生成失敗：{exc}"
        finally:
            self._job_procs.pop(job["id"], None)
            self._cancelled_jobs.discard(job["id"])

    def start_lipsync_generation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "kind": "lipsync",
            "status": "running",
            "progress": 10,
            "message": "正在檢查 D:\\AI-Models\\lipsync 環境與權重...",
            "params": {k: v for k, v in params.items() if not k.endswith("_data_url")},
            "created_at": time.time(),
            "elapsed_seconds": 0.0,
            "outputs": [],
            "error": "",
        }
        self.jobs[job_id] = job
        asyncio.create_task(self._run_lipsync_job(job, params))
        return job

    async def _run_lipsync_job(self, job: Dict[str, Any], params: Dict[str, Any]) -> None:
        t0 = time.monotonic()
        try:
            lipsync_root = Path("D:/AI-Models/lipsync")
            if not lipsync_root.exists():
                raise RuntimeError("找不到 D:\\AI-Models\\lipsync 目錄。")
            if not params.get("portrait_data_url") or not params.get("audio_data_url"):
                raise ValueError("請同時上傳人物照片/影片以及音訊檔案。")

            portrait = _save_base64_upload(params["portrait_data_url"], "portrait")
            audio = _save_base64_upload(params["audio_data_url"], "audio")

            # If ComfyUI URL is configured and reachable, dispatch cleanly; otherwise report ready status & script hook
            comfy_url = config_manager.config.comfyui_url.strip()
            if comfy_url:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    r = await client.get(f"{comfy_url.rstrip('/')}/system_stats")
                    if r.status_code == 200:
                        job["message"] = f"已偵測到 ComfyUI ({comfy_url})，素材已暫存至 {portrait.name} / {audio.name}"

            raise RuntimeError(
                f"已偵測到 InfiniteTalk + Wan2.1 權重與 CUDA 環境（素材已暫存：{portrait.name}、{audio.name}）。"
                "請啟動本機 ComfyUI 並載入 InfiniteTalk 工作流，或在設定指定自訂對口型推理腳本路徑。"
            )
        except Exception as exc:
            job["status"] = "error"
            job["error"] = str(exc)
            job["elapsed_seconds"] = round(time.monotonic() - t0, 1)
            job["message"] = str(exc)

    async def _exec_media_cli(self, cmd: List[str], job: Dict[str, Any]) -> None:
        import re

        if job["id"] in self._cancelled_jobs:
            raise JobCancelledError()

        kwargs: Dict[str, Any] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
            "cwd": str(Path(cmd[0]).parent),
        }
        if platform.system() == "Windows":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = await asyncio.create_subprocess_exec(*cmd, **kwargs)
        self._active_proc = proc
        self._job_procs[job["id"]] = proc
        last_lines: List[str] = []
        # Only match real sampling progress bars (e.g. "|===| 3/8 - 1.45s/it" or "42.0it/s"), NOT tensor loading ("MB/s")
        sample_re = re.compile(r"\|\s*(\d+)\s*/\s*(\d+)\s*-\s*[\d.]+\s*(?:s/it|it/s)", re.IGNORECASE)
        if proc.stdout:
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                text = raw.decode("utf-8", errors="replace").strip()
                if text:
                    last_lines.append(text)
                    last_lines = last_lines[-20:]
                    m = sample_re.search(text)
                    if m:
                        cur, tot = int(m.group(1)), max(1, int(m.group(2)))
                        job["progress"] = min(92, max(20, int(20 + (cur / tot) * 72)))
                        job["message"] = f"正在採樣生成：第 {cur} / {tot} 步 ({text.split('-')[-1].strip()})"
                    elif "computing condition graph" in text.lower():
                        job["progress"] = max(job.get("progress", 5), 18)
                        job["message"] = "提示詞條件編碼完成，準備開始採樣..."
                    elif "sampling completed" in text.lower():
                        job["progress"] = 93
                        job["message"] = "採樣完成，正在載入 VAE 並進行影像解碼..."
                    elif "computing vae decode graph" in text.lower():
                        job["progress"] = 97
                        job["message"] = "VAE 解碼完成，正在寫入成品檔案..."
                    elif "loading " in text.lower() and "tensors" in text.lower():
                        if job.get("progress", 5) >= 93:
                            job["message"] = "採樣完成，正在進行 VAE 分塊解碼..."
                        else:
                            if job.get("progress", 5) < 16:
                                job["progress"] = min(16, job.get("progress", 5) + 1)
                            job["message"] = text[:140]
                    elif job.get("progress", 5) < 93:
                        job["message"] = text[:140]
        rc = await proc.wait()
        self._job_procs.pop(job["id"], None)
        if self._active_proc is proc:
            self._active_proc = None
        if job["id"] in self._cancelled_jobs:
            raise JobCancelledError()
        if rc != 0:
            tail = " | ".join(last_lines[-3:])
            raise RuntimeError(f"引擎退出代碼 {rc}：{tail}")

    def _register_output(
        self,
        job: Dict[str, Any],
        model: Dict[str, Any],
        out_path: Path,
        kind: str,
        params: Dict[str, Any],
        elapsed: float,
    ) -> None:
        folder = "images" if kind == "image" else "videos" if kind == "video" else "lipsync"
        entry = {
            "id": uuid.uuid4().hex[:12],
            "kind": kind,
            "filename": out_path.name,
            "file_path": str(out_path.resolve()),
            "url": f"/api/media/files/{folder}/{out_path.name}",
            "model_id": model["id"],
            "model_name": f"{model['name']} {model['quantization']}",
            "prompt": params.get("prompt", ""),
            "negative_prompt": params.get("negative_prompt", ""),
            "width": params.get("width", 1024),
            "height": params.get("height", 1024),
            "steps": params.get("steps", 8),
            "duration": params.get("duration"),
            "seed": params.get("seed", ""),
            "elapsed_seconds": round(elapsed, 1),
            "created_at": time.time(),
        }
        items = _load_gallery()
        items.insert(0, entry)
        _save_gallery(items)
        job["outputs"].append(entry)


media_manager = MediaManager()
