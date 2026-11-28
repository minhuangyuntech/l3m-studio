from __future__ import annotations

import asyncio
import json
import platform
import random
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import httpx

from .comfy_workflows import (
    convert_ui_workflow_to_api,
    fetch_comfyui_workflow_raw,
    get_comfy_object_info,
    inject_workflow_params,
    list_comfyui_workflows,
    reconcile_workflow_models,
)
from .config import config_manager

# Short TTL cache for ComfyUI status probes so 2.5s UI polling stays instant
_PROBE_CACHE: Dict[str, Any] = {"ts": 0.0, "key": "", "data": None}
_PROBE_TTL = 12.0


def _is_remote_url(url: str) -> bool:
    low = url.strip().lower()
    return bool(low) and not (
        low.startswith("http://127.0.0.1")
        or low.startswith("http://localhost")
        or low.startswith("http://[::1]")
    )


def build_comfyui_headers(url: str, token: str = "") -> Dict[str, str]:
    hdrs: Dict[str, str] = {"User-Agent": "L3M-Studio/1.2"}
    if _is_remote_url(url):
        # Prevent ngrok free-tier browser interstitial warnings when tunnelling ComfyUI
        hdrs["ngrok-skip-browser-warning"] = "true"
    tok = token.strip()
    if tok:
        hdrs["Authorization"] = f"Bearer {tok}"
        hdrs["X-API-Key"] = tok
    return hdrs


def resolve_comfyui_connection(
    base_url: Optional[str] = None,
    mode: Optional[str] = None,
    token: Optional[str] = None,
) -> Tuple[str, str, Dict[str, str], bool]:
    """Return (active_mode, url, headers, is_remote) for local or remote Colab ComfyUI."""
    cfg = config_manager.config
    eff_mode = (mode or cfg.comfyui_mode or "local").strip().lower()
    if eff_mode not in ("local", "remote"):
        eff_mode = "local"
    if base_url is not None and base_url.strip():
        eff_url = base_url.strip().rstrip("/")
        eff_remote = _is_remote_url(eff_url)
        eff_tok = token if token is not None else (cfg.comfyui_remote_token if eff_remote else "")
        return ("remote" if eff_remote else "local"), eff_url, build_comfyui_headers(eff_url, eff_tok), eff_remote

    if eff_mode == "remote":
        eff_url = (cfg.comfyui_remote_url or "").strip().rstrip("/")
        eff_tok = token if token is not None else (cfg.comfyui_remote_token or "")
        return "remote", eff_url, build_comfyui_headers(eff_url, eff_tok), True

    eff_url = (cfg.comfyui_url or "http://127.0.0.1:8000").strip().rstrip("/")
    eff_tok = token or ""
    return "local", eff_url, build_comfyui_headers(eff_url, eff_tok), _is_remote_url(eff_url)


def _pick(items: List[str], *substrings: str) -> str:
    for item in items:
        low = item.lower()
        if all(s.lower() in low for s in substrings):
            return item
    return ""


def _extract_combo_list(node_info: Dict[str, Any], key: str) -> List[str]:
    try:
        spec = node_info.get("input", {}).get("required", {}).get(key)
        if not spec:
            return []
        first = spec[0]
        if isinstance(first, list):
            return [str(x) for x in first]
        if first == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
            opts = spec[1].get("options", [])
            return [str(x) for x in opts]
    except Exception:
        pass
    return []


async def probe_comfyui(
    base_url: Optional[str] = None,
    mode: Optional[str] = None,
    token: Optional[str] = None,
    force: bool = False,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Probe a running local or remote (Colab) ComfyUI server and detect pipelines & workflows."""
    eff_mode, configured, headers, is_remote = resolve_comfyui_connection(base_url=base_url, mode=mode, token=token)
    eff_timeout = timeout if timeout is not None else (10.0 if is_remote else 3.0)
    cache_key = f"{eff_mode}|{configured}|{headers.get('X-API-Key', '')}"
    now = time.monotonic()
    if (
        not force
        and _PROBE_CACHE["data"] is not None
        and _PROBE_CACHE["key"] == cache_key
        and (now - _PROBE_CACHE["ts"]) < _PROBE_TTL
    ):
        return _PROBE_CACHE["data"]

    result: Dict[str, Any] = {
        "online": False,
        "mode": eff_mode,
        "is_remote": is_remote,
        "url": configured,
        "version": "",
        "gpu_name": "",
        "error": "",
        "checkpoints": [],
        "unets": [],
        "clips": [],
        "vaes": [],
        "upscalers": [],
        "loras": [],
        "detected": {},
        "presets": [],
        "image_presets": [],
        "workflows": [],
    }

    if not configured:
        result["error"] = "尚未填寫遠端 Colab ComfyUI 網址（請貼上 Cloudflare Tunnel 產生的 https://*.trycloudflare.com 網址）"
        _PROBE_CACHE.update({"ts": now, "key": cache_key, "data": result})
        return result

    candidates = [configured]
    if not base_url and eff_mode == "local" and not is_remote:
        for fb in ("http://127.0.0.1:8000", "http://127.0.0.1:8188"):
            if fb not in candidates:
                candidates.append(fb)

    async with httpx.AsyncClient(timeout=eff_timeout, headers=headers, follow_redirects=True) as client:
        active_url = ""
        sys_data: Dict[str, Any] = {}
        last_err = ""
        for cand in candidates:
            try:
                r = await client.get(f"{cand}/system_stats")
                if r.status_code == 200:
                    active_url = cand
                    sys_data = r.json()
                    break
                elif r.status_code == 401:
                    last_err = "遠端 ComfyUI 認證失敗 (HTTP 401)，請檢查「遠端認證 Token」是否與 Colab 設定一致"
                    break
                else:
                    last_err = f"HTTP {r.status_code}"
            except Exception as exc:
                last_err = str(exc)

        if not active_url:
            result["error"] = last_err or f"無法連線至 ComfyUI ({configured})"
            _PROBE_CACHE.update({"ts": now, "key": cache_key, "data": result})
            return result

        # Auto-update saved local URL if we discovered local ComfyUI running on the alternate default port
        if not base_url and eff_mode == "local" and active_url != configured and configured in ("http://127.0.0.1:8188", "http://127.0.0.1:8000"):
            config_manager.update({"comfyui_url": active_url})

        result["online"] = True
        result["url"] = active_url
        sys_info = sys_data.get("system", {})
        result["version"] = str(sys_info.get("comfyui_version", ""))
        devices = sys_data.get("devices", [])
        if devices:
            result["gpu_name"] = str(devices[0].get("name", ""))

        node_names = [
            "CheckpointLoaderSimple",
            "UNETLoader",
            "CLIPLoader",
            "VAELoader",
            "LatentUpscaleModelLoader",
            "LoraLoaderModelOnly",
            "MiniMaxH3ImageToVideo",
            "LTXVDualCFGGuider",
            "ModelSamplingAuraFlow",
        ]
        node_infos: Dict[str, Any] = {}
        responses = await asyncio.gather(
            *[client.get(f"{active_url}/object_info/{name}") for name in node_names],
            return_exceptions=True,
        )
        for name, resp in zip(node_names, responses):
            if isinstance(resp, httpx.Response) and resp.status_code == 200:
                try:
                    d = resp.json()
                    if name in d:
                        node_infos[name] = d[name]
                except Exception:
                    pass

        checkpoints = _extract_combo_list(node_infos.get("CheckpointLoaderSimple", {}), "ckpt_name")
        unets = _extract_combo_list(node_infos.get("UNETLoader", {}), "unet_name")
        clips = _extract_combo_list(node_infos.get("CLIPLoader", {}), "clip_name")
        vaes = _extract_combo_list(node_infos.get("VAELoader", {}), "vae_name")
        upscalers = _extract_combo_list(node_infos.get("LatentUpscaleModelLoader", {}), "model_name")
        loras = _extract_combo_list(node_infos.get("LoraLoaderModelOnly", {}), "lora_name")

        # Filter out video-only checkpoints (like ltx-2.3) from image checkpoint selector
        image_checkpoints = [c for c in checkpoints if "ltx-" not in c.lower() and "wan2" not in c.lower()]

        result["checkpoints"] = image_checkpoints
        result["unets"] = unets
        result["clips"] = clips
        result["vaes"] = vaes
        result["upscalers"] = upscalers
        result["loras"] = loras

        # Detect Z-Image-Turbo BF16 image pipeline
        z_unet = _pick(unets, "z_image_turbo") or _pick(unets, "z-image-turbo") or _pick(unets, "z_image")
        z_clip = _pick(clips, "qwen_3_4b") or _pick(clips, "qwen3_4b") or _pick(clips, "qwen-3-4b")
        z_vae = _pick(vaes, "ae.safetensors") or _pick(vaes, "ae.")
        has_z_image = bool(z_unet and z_clip and z_vae)

        # Detect LTX-2.5 22B Distilled INT8 video pipeline
        ltx_unet = _pick(unets, "ltx-2.5") or _pick(unets, "ltx2.5") or _pick(unets, "ltx")
        ltx_clip = _pick(clips, "gemma4", "ltx-2.5") or _pick(clips, "gemma4", "ltx") or _pick(clips, "gemma")
        ltx_v_vae = _pick(vaes, "ltx-2.5", "video") or _pick(vaes, "ltx", "video")
        ltx_a_vae = _pick(vaes, "ltx-2.5", "audio") or _pick(vaes, "ltx", "audio")
        ltx_up = _pick(upscalers, "ltx-2.5") or _pick(upscalers, "ltx")
        has_ltx25 = bool(
            ltx_unet and ltx_clip and ltx_v_vae and ltx_a_vae and ltx_up and "LTXVDualCFGGuider" in node_infos
        )

        # Detect MiniMax-H3 FL2VA INT8 video pipeline
        mm_unet = _pick(unets, "minimax_h3") or _pick(unets, "minimax")
        mm_clip = _pick(clips, "minimax_h3") or _pick(clips, "qwen3vl", "minimax")
        mm_v_vae = _pick(vaes, "minimax_h3", "video") or _pick(vaes, "minimax", "video")
        mm_a_vae = _pick(vaes, "minimax_h3", "audio") or _pick(vaes, "minimax", "audio")
        mm_turbo_lora = _pick(loras, "minimax_h3", "turbo") or _pick(loras, "minimax", "8step")
        has_minimax = bool(mm_unet and mm_clip and mm_v_vae and mm_a_vae and "MiniMaxH3ImageToVideo" in node_infos)

        result["detected"] = {
            "has_z_image": has_z_image,
            "z_image": {
                "unet": z_unet,
                "clip": z_clip,
                "vae": z_vae,
            },
            "has_checkpoints": bool(image_checkpoints),
            "has_ltx25": has_ltx25,
            "ltx25": {
                "unet": ltx_unet,
                "clip": ltx_clip,
                "video_vae": ltx_v_vae,
                "audio_vae": ltx_a_vae,
                "upscaler": ltx_up,
            },
            "has_minimax_h3": has_minimax,
            "has_minimax_turbo_lora": bool(mm_turbo_lora),
            "minimax_h3": {
                "unet": mm_unet,
                "clip": mm_clip,
                "video_vae": mm_v_vae,
                "audio_vae": mm_a_vae,
                "turbo_lora": mm_turbo_lora,
            },
        }

        # Auto-discover installed ComfyUI workflows (user saved + extensions + templates)
        installed_files: Set[str] = set(checkpoints + unets + clips + vaes + loras)
        workflows = await list_comfyui_workflows(
            active_url,
            installed_files=installed_files,
            force=force,
            headers=headers,
            timeout=15.0 if is_remote else 8.0,
        )
        result["workflows"] = workflows

        # Build Image Presets
        image_presets: List[Dict[str, Any]] = []
        if has_z_image:
            image_presets.append({
                "id": "comfy_z_image_turbo",
                "name": "Z-Image-Turbo BF16（ComfyUI 高畫質推薦）",
                "description": "官方 BF16 原版精度 + Qwen3-4B 中文語意理解 + 8步高速採樣（畫質大幅優於 Q3 量化）。",
                "default_steps": 8,
                "badge": "BF16 · 推薦",
            })
        if image_checkpoints:
            image_presets.append({
                "id": "comfy_checkpoint",
                "name": f"ComfyUI Checkpoints（SDXL / SD1.5 · {len(image_checkpoints)} 個模型）",
                "description": "直接使用 ComfyUI 已安裝的 SDXL / SD1.5 / 寫實人像底模，並支援掛載 ComfyUI LoRA。",
                "default_steps": 24,
                "badge": f"{len(image_checkpoints)} 底模",
            })
        image_presets.append({
            "id": "comfy_saved_workflow",
            "name": f"執行 ComfyUI 已安裝工作流（已自動載入 {len(workflows)} 個）",
            "description": "自動載入 ComfyUI 使用者工作流、擴充節點與官方範本，自動轉換並注入提示詞、尺寸與參考圖。",
            "default_steps": 20,
            "badge": "自動載入",
        })
        image_presets.append({
            "id": "comfy_custom_json",
            "name": "匯入自訂 ComfyUI 工作流 (JSON)",
            "description": "支援標準 ComfyUI 工作流 JSON 與 Export (API) JSON（自動轉換執行）。",
            "default_steps": 20,
            "badge": "自訂 JSON",
        })
        result["image_presets"] = image_presets

        # Build Video Presets
        presets: List[Dict[str, Any]] = []
        if has_ltx25:
            presets.append({
                "id": "comfy_ltx25",
                "name": "LTX-2.5 22B Distilled INT8（雙階超分有聲·推薦）",
                "description": "官方 2-Stage 潛空間 x2 超解析管線，高速蒸餾採樣 + 同步音訊，人臉與光影極致清晰。",
                "default_steps": 8,
                "default_duration": 5,
                "supports_first_frame": True,
                "supports_last_frame": False,
                "supports_audio": True,
                "badge": "INT8 · 推薦",
            })
        if has_minimax and mm_turbo_lora:
            presets.append({
                "id": "comfy_minimax_h3_turbo",
                "name": "MiniMax-H3 FL2VA INT8（8步 Turbo 有聲）",
                "description": "INT8 高精度主權重 + 8步 Turbo LoRA + 同步音訊 VAE，支援首尾幀控制與自然中文理解。",
                "default_steps": 8,
                "default_duration": 5,
                "supports_first_frame": True,
                "supports_last_frame": True,
                "supports_audio": True,
                "badge": "INT8 · 8步加速",
            })
        if has_minimax:
            presets.append({
                "id": "comfy_minimax_h3",
                "name": "MiniMax-H3 FL2VA INT8（20步標準有聲）",
                "description": "完整 20 步 res_multistep 採樣 + 首尾幀插值 + 音訊同步生成，品質細膩穩定。",
                "default_steps": 20,
                "default_duration": 5,
                "supports_first_frame": True,
                "supports_last_frame": True,
                "supports_audio": True,
                "badge": "INT8 · 高品質",
            })
        presets.append({
            "id": "comfy_saved_workflow",
            "name": f"執行 ComfyUI 已安裝工作流（已自動載入 {len(workflows)} 個）",
            "description": "自動載入 ComfyUI 內已安裝的影片工作流與官方範本（支援 UI 與 API 格式自動轉換）。",
            "default_steps": 20,
            "default_duration": 5,
            "supports_first_frame": True,
            "supports_last_frame": True,
            "supports_audio": True,
            "badge": "自動載入",
        })
        presets.append({
            "id": "comfy_custom_json",
            "name": "匯入自訂 ComfyUI 工作流 (JSON)",
            "description": "匯入 ComfyUI UI 或 API 格式 JSON（自動注入提示詞、種子與首尾幀圖片）。",
            "default_steps": 20,
            "default_duration": 5,
            "supports_first_frame": True,
            "supports_last_frame": True,
            "supports_audio": True,
            "badge": "自訂 JSON",
        })
        result["presets"] = presets

    _PROBE_CACHE.update({"ts": now, "key": cache_key, "data": result})
    return result


async def interrupt_comfyui(base_url: str, prompt_id: str = "", headers: Optional[Dict[str, str]] = None) -> None:
    if base_url:
        url = base_url.strip().rstrip("/")
        hdrs = headers or build_comfyui_headers(url, config_manager.config.comfyui_remote_token if _is_remote_url(url) else "")
    else:
        _, url, hdrs, _ = resolve_comfyui_connection()
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=hdrs, follow_redirects=True) as client:
            if prompt_id:
                await client.post(f"{url}/queue", json={"delete": [prompt_id]})
            await client.post(f"{url}/interrupt")
    except Exception:
        pass


def _snap(val: int, mult: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(val / mult) * mult)))


# ---------- Built-in ComfyUI Image Workflows ----------


def build_z_image_turbo_workflow(
    detected: Dict[str, str],
    prompt: str,
    width: int,
    height: int,
    steps: int,
    batch_size: int,
    seed: int,
    lora_name: str = "",
    lora_strength: float = 0.8,
    ref_image_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Official ComfyUI v0.46.0 Z-Image-Turbo BF16 workflow (supports optional LoRA & img2img)."""
    w = _snap(width, 64, 512, 2048)
    h = _snap(height, 64, 512, 2048)
    effective_steps = max(4, min(30, int(steps or 8)))
    bs = max(1, min(4, int(batch_size or 1)))

    wf: Dict[str, Any] = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": detected["unet"], "weight_dtype": "default"},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": detected["clip"], "type": "lumina2", "device": "default"},
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": detected["vae"]},
        },
    }

    model_ref: Any = ["1", 0]
    if lora_name:
        wf["4"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["1", 0],
                "lora_name": lora_name,
                "strength_model": float(lora_strength),
            },
        }
        model_ref = ["4", 0]

    wf["5"] = {
        "class_type": "ModelSamplingAuraFlow",
        "inputs": {"model": model_ref, "shift": 3.0},
    }
    wf["6"] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}}
    wf["7"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}}

    denoise = 1.0
    if ref_image_name:
        wf["8"] = {"class_type": "LoadImage", "inputs": {"image": ref_image_name}}
        wf["9"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["8", 0], "vae": ["3", 0]}}
        latent_ref: Any = ["9", 0]
        denoise = 0.72
    else:
        wf["8"] = {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": w, "height": h, "batch_size": bs},
        }
        latent_ref = ["8", 0]

    wf["10"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": ["5", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": latent_ref,
            "seed": int(seed),
            "steps": effective_steps,
            "cfg": 1.0,
            "sampler_name": "res_multistep",
            "scheduler": "simple",
            "denoise": denoise,
        },
    }
    if w * h > 1024 * 1024:
        wf["11"] = {
            "class_type": "VAEDecodeTiled",
            "inputs": {
                "samples": ["10", 0],
                "vae": ["3", 0],
                "tile_size": 512,
                "overlap": 64,
                "temporal_size": 64,
                "temporal_overlap": 8,
            },
        }
    else:
        wf["11"] = {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["3", 0]}}

    wf["12"] = {
        "class_type": "SaveImage",
        "inputs": {"images": ["11", 0], "filename_prefix": f"L3M_ZImage_{int(time.time())}"},
    }
    return wf


def build_checkpoint_image_workflow(
    ckpt_name: str,
    prompt: str,
    neg_prompt: str,
    width: int,
    height: int,
    steps: int,
    batch_size: int,
    seed: int,
    cfg: float = 7.0,
    lora_name: str = "",
    lora_strength: float = 0.8,
    ref_image_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Standard ComfyUI CheckpointLoaderSimple workflow (SDXL / SD1.5 / SD3.5) with optional LoRA & img2img."""
    low = ckpt_name.lower()
    is_sdxl = "sdxl" in low or "sd_xl" in low or "xl" in low or "sd3.5" in low
    w = _snap(width, 64, 512, 2048)
    h = _snap(height, 64, 512, 2048)
    effective_steps = max(4, min(60, int(steps or (24 if is_sdxl else 25))))
    bs = max(1, min(4, int(batch_size or 1)))
    effective_neg = neg_prompt.strip() or "lowres, bad anatomy, bad hands, blurry, worst quality, watermark"

    wf: Dict[str, Any] = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
    }
    model_ref: Any = ["1", 0]
    clip_ref: Any = ["1", 1]
    vae_ref: Any = ["1", 2]

    if lora_name:
        wf["2"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": model_ref,
                "clip": clip_ref,
                "lora_name": lora_name,
                "strength_model": float(lora_strength),
                "strength_clip": float(lora_strength),
            },
        }
        model_ref = ["2", 0]
        clip_ref = ["2", 1]

    wf["3"] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": clip_ref}}
    wf["4"] = {"class_type": "CLIPTextEncode", "inputs": {"text": effective_neg, "clip": clip_ref}}

    denoise = 1.0
    if ref_image_name:
        wf["5"] = {"class_type": "LoadImage", "inputs": {"image": ref_image_name}}
        wf["6"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": vae_ref}}
        latent_ref: Any = ["6", 0]
        denoise = 0.72
    else:
        wf["5"] = {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": w, "height": h, "batch_size": bs},
        }
        latent_ref = ["5", 0]

    wf["7"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": model_ref,
            "positive": ["3", 0],
            "negative": ["4", 0],
            "latent_image": latent_ref,
            "seed": int(seed),
            "steps": effective_steps,
            "cfg": float(cfg or (7.0 if not "sd3.5" in low else 4.5)),
            "sampler_name": "dpmpp_2m" if is_sdxl else "euler_ancestral",
            "scheduler": "karras" if is_sdxl else "normal",
            "denoise": denoise,
        },
    }
    wf["8"] = {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": vae_ref}}
    wf["9"] = {
        "class_type": "SaveImage",
        "inputs": {"images": ["8", 0], "filename_prefix": f"L3M_Ckpt_{int(time.time())}"},
    }
    return wf


# ---------- Built-in ComfyUI Video Workflows ----------


def build_ltx25_workflow(
    detected: Dict[str, str],
    prompt: str,
    neg_prompt: str,
    width: int,
    height: int,
    duration: int,
    seed: int,
    first_frame_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Official ComfyUI v0.46.0 LTX-2.5 22B Distilled INT8 2-stage (x2 latent upscaler) AV workflow."""
    full_w = _snap(width, 64, 512, 1280)
    full_h = _snap(height, 64, 384, 1280)
    half_w = full_w // 2
    half_h = full_h // 2
    fps = 24.0
    frames = max(25, min(241, int(duration) * 24 + 1))
    effective_neg = neg_prompt.strip() or "pc game, console game, video game, cartoon, childish, ugly, blurry, distorted face"

    wf: Dict[str, Any] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": detected["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": detected["clip"], "type": "ltxv", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": detected["video_vae"]}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": detected["audio_vae"]}},
        "5": {"class_type": "LatentUpscaleModelLoader", "inputs": {"model_name": detected["upscaler"]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": effective_neg, "clip": ["2", 0]}},
        "8": {"class_type": "LTXVConditioning", "inputs": {"positive": ["6", 0], "negative": ["7", 0], "frame_rate": fps}},
        "9": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": half_w, "height": half_h, "length": frames, "batch_size": 1}},
        "10": {"class_type": "LTXVEmptyLatentAudio", "inputs": {"frames_number": frames, "frame_rate": fps, "batch_size": 1, "audio_vae": ["4", 0]}},
    }

    stage1_video_latent: Any = ["9", 0]
    if first_frame_name:
        wf["11"] = {"class_type": "LoadImage", "inputs": {"image": first_frame_name}}
        wf["12"] = {"class_type": "LTXVPreprocess", "inputs": {"image": ["11", 0], "img_compression": 18}}
        wf["13"] = {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {"vae": ["3", 0], "image": ["12", 0], "latent": ["9", 0], "strength": 0.7, "bypass": False},
        }
        stage1_video_latent = ["13", 0]

    wf["14"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": stage1_video_latent, "audio_latent": ["10", 0]}}
    wf["15"] = {
        "class_type": "LTXVDualCFGGuider",
        "inputs": {"model": ["1", 0], "positive": ["8", 0], "negative": ["8", 1], "video_cfg": 1.0, "audio_cfg": 1.0},
    }
    wf["16"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}}
    wf["17"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"}}
    wf["18"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": int(seed)}}
    wf["19"] = {
        "class_type": "SamplerCustomAdvanced",
        "inputs": {"noise": ["18", 0], "guider": ["15", 0], "sampler": ["16", 0], "sigmas": ["17", 0], "latent_image": ["14", 0]},
    }
    wf["20"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["19", 0]}}
    wf["21"] = {"class_type": "LTXVLatentUpsampler", "inputs": {"samples": ["20", 0], "upscale_model": ["5", 0], "vae": ["3", 0]}}

    stage2_video_latent: Any = ["21", 0]
    if first_frame_name:
        wf["22"] = {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {"vae": ["3", 0], "image": ["12", 0], "latent": ["21", 0], "strength": 1.0, "bypass": False},
        }
        stage2_video_latent = ["22", 0]

    wf["23"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": stage2_video_latent, "audio_latent": ["20", 1]}}
    wf["24"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": "0.85, 0.7250, 0.4219, 0.0"}}
    wf["25"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}}
    wf["26"] = {
        "class_type": "SamplerCustomAdvanced",
        "inputs": {"noise": ["25", 0], "guider": ["15", 0], "sampler": ["16", 0], "sigmas": ["24", 0], "latent_image": ["23", 0]},
    }
    wf["27"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["26", 0]}}
    wf["28"] = {
        "class_type": "VAEDecodeTiled",
        "inputs": {"samples": ["27", 0], "vae": ["3", 0], "tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 16},
    }
    wf["29"] = {"class_type": "LTXVAudioVAEDecode", "inputs": {"samples": ["27", 1], "audio_vae": ["4", 0]}}
    wf["30"] = {"class_type": "CreateVideo", "inputs": {"images": ["28", 0], "audio": ["29", 0], "fps": fps}}
    wf["31"] = {
        "class_type": "SaveVideo",
        "inputs": {"video": ["30", 0], "filename_prefix": f"video/L3M_LTX25_{int(time.time())}", "format": "auto", "codec": "auto"},
    }
    return wf


def build_minimax_h3_workflow(
    detected: Dict[str, str],
    prompt: str,
    width: int,
    height: int,
    duration: int,
    steps: int,
    seed: int,
    use_turbo: bool = True,
    first_frame_name: Optional[str] = None,
    last_frame_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Official ComfyUI v0.46.0 MiniMax-H3 FL2VA INT8 AV workflow (optional 8-step Turbo LoRA)."""
    w = _snap(width, 32, 320, 1280)
    h = _snap(height, 32, 320, 1280)
    raw = max(5, round(int(duration) * 24))
    length = raw + (5 - (raw % 17)) % 17
    length = max(22, min(243, length))
    effective_steps = max(4, min(40, int(steps or (8 if use_turbo else 20))))

    wf: Dict[str, Any] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": detected["unet"], "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": detected["clip"], "type": "minimax", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": detected["video_vae"]}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": detected["audio_vae"]}},
    }

    model_ref: Any = ["1", 0]
    if use_turbo and detected.get("turbo_lora"):
        wf["5"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"model": ["1", 0], "lora_name": detected["turbo_lora"], "strength_model": 1.0},
        }
        model_ref = ["5", 0]

    mm_inputs: Dict[str, Any] = {"clip": ["2", 0], "vae": ["3", 0], "prompt": prompt, "width": w, "height": h, "length": length}
    if first_frame_name:
        wf["6"] = {"class_type": "LoadImage", "inputs": {"image": first_frame_name}}
        mm_inputs["first_frame"] = ["6", 0]
    if last_frame_name:
        wf["7"] = {"class_type": "LoadImage", "inputs": {"image": last_frame_name}}
        mm_inputs["last_frame"] = ["7", 0]

    wf["8"] = {"class_type": "MiniMaxH3ImageToVideo", "inputs": mm_inputs}
    wf["9"] = {"class_type": "BasicGuider", "inputs": {"model": model_ref, "conditioning": ["8", 0]}}
    wf["10"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": int(seed)}}
    wf["11"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}}
    wf["12"] = {"class_type": "BasicScheduler", "inputs": {"model": model_ref, "scheduler": "simple", "steps": effective_steps, "denoise": 1.0}}
    wf["13"] = {
        "class_type": "SamplerCustomAdvanced",
        "inputs": {"noise": ["10", 0], "guider": ["9", 0], "sampler": ["11", 0], "sigmas": ["12", 0], "latent_image": ["8", 1]},
    }
    wf["14"] = {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["3", 0]}}
    wf["15"] = {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["13", 0], "vae": ["4", 0]}}
    wf["16"] = {"class_type": "CreateVideo", "inputs": {"images": ["14", 0], "audio": ["15", 0], "fps": 24.0}}
    wf["17"] = {
        "class_type": "SaveVideo",
        "inputs": {"video": ["16", 0], "filename_prefix": f"video/L3M_MiniMaxH3_{int(time.time())}", "format": "auto", "codec": "auto"},
    }
    return wf


# ---------- Shared ComfyUI Execution Helpers ----------


async def _upload_image_to_comfyui(client: httpx.AsyncClient, base_url: str, img_path: Path) -> str:
    mime = "image/png"
    ext = img_path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif ext == ".webp":
        mime = "image/webp"
    files = {"image": (img_path.name, img_path.read_bytes(), mime)}
    data = {"type": "input", "overwrite": "true"}
    resp = await client.post(f"{base_url}/upload/image", files=files, data=data)
    resp.raise_for_status()
    info = resp.json()
    name = info.get("name", img_path.name)
    sub = info.get("subfolder", "")
    return f"{sub}/{name}" if sub else name


async def _transcode_to_mp4(src: Path, dst: Path) -> Path:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin or src.suffix.lower() == ".mp4":
        return src
    ff_kwargs: Dict[str, Any] = {"stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.STDOUT}
    if platform.system() == "Windows":
        ff_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    proc = await asyncio.create_subprocess_exec(
        ffmpeg_bin, "-y", "-i", str(src), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst),
        **ff_kwargs,
    )
    await proc.communicate()
    if proc.returncode == 0 and dst.exists() and dst.stat().st_size > 1024:
        src.unlink(missing_ok=True)
        return dst
    return src


async def _submit_and_wait_comfyui(
    client: httpx.AsyncClient,
    base_url: str,
    workflow: Dict[str, Any],
    model_label: str,
    job: Dict[str, Any],
    is_cancelled: Callable[[], bool],
    on_prompt_submitted: Callable[[str, str], None],
    est_scale_sec: float = 40.0,
) -> Dict[str, Any]:
    """Submit API prompt to ComfyUI, wait until completion or error, return history entry."""
    client_id = f"l3m_{uuid.uuid4().hex[:10]}"
    job["progress"] = 14
    job["message"] = f"正在送出 {model_label} 工作流至 ComfyUI ({base_url})..."
    submit_resp = await client.post(
        f"{base_url}/prompt",
        json={"prompt": workflow, "client_id": client_id},
    )
    if submit_resp.status_code != 200:
        raise RuntimeError(f"ComfyUI 拒絕執行工作流 (HTTP {submit_resp.status_code})：{submit_resp.text[:500]}")
    submit_data = submit_resp.json()
    node_errors = submit_data.get("node_errors")
    if node_errors:
        raise RuntimeError(f"ComfyUI 節點參數驗證錯誤：{json.dumps(node_errors, ensure_ascii=False)[:450]}")
    prompt_id = str(submit_data.get("prompt_id", ""))
    if not prompt_id:
        raise RuntimeError("ComfyUI 未回傳 prompt_id。")
    on_prompt_submitted(base_url, prompt_id)

    t_start = time.monotonic()
    while True:
        if is_cancelled():
            await interrupt_comfyui(base_url, prompt_id)
            raise asyncio.CancelledError()

        await asyncio.sleep(1.2)
        elapsed = int(time.monotonic() - t_start)

        hr = await client.get(f"{base_url}/history/{prompt_id}")
        if hr.status_code == 200:
            hdata = hr.json()
            if prompt_id in hdata:
                hist_entry = hdata[prompt_id]
                status_obj = hist_entry.get("status", {})
                status_str = str(status_obj.get("status_str", ""))
                if status_str == "error":
                    msgs = status_obj.get("messages", [])
                    raise RuntimeError(f"ComfyUI 執行發生錯誤：{json.dumps(msgs, ensure_ascii=False)[:450]}")
                if status_obj.get("completed") or hist_entry.get("outputs"):
                    return hist_entry

        try:
            qr = await client.get(f"{base_url}/queue")
            if qr.status_code == 200:
                qdata = qr.json()
                running_ids = [item[1] for item in qdata.get("queue_running", []) if len(item) > 1]
                pending_ids = [item[1] for item in qdata.get("queue_pending", []) if len(item) > 1]
                if prompt_id in pending_ids:
                    pos = pending_ids.index(prompt_id) + 1
                    job["progress"] = 16
                    job["message"] = f"ComfyUI 佇列排隊中（第 {pos} 順位 · 已等待 {elapsed}s）..."
                elif prompt_id in running_ids:
                    est_pct = min(92, int(20 + 72 * (1.0 - (1.0 / (1.0 + elapsed / est_scale_sec)))))
                    job["progress"] = max(job.get("progress", 20), est_pct)
                    job["message"] = f"ComfyUI GPU 渲染中（{model_label} · 已耗時 {elapsed}s）..."
                elif elapsed > 12:
                    job["message"] = f"正在同步 ComfyUI 輸出結果（{elapsed}s）..."
        except Exception:
            pass


async def _prepare_loaded_or_custom_workflow(
    base_url: str,
    raw_wf: Dict[str, Any],
    prompt: str,
    neg_prompt: str,
    width: Optional[int],
    height: Optional[int],
    batch_size: Optional[int],
    steps: Optional[int],
    seed: int,
    first_frame_name: Optional[str],
    last_frame_name: Optional[str],
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    obj_info = await get_comfy_object_info(base_url, headers=headers, timeout=30.0)
    if isinstance(raw_wf.get("nodes"), list):
        api_wf = convert_ui_workflow_to_api(raw_wf, obj_info)
    else:
        api_wf = raw_wf
    injected = inject_workflow_params(
        api_wf,
        prompt=prompt,
        neg_prompt=neg_prompt,
        width=width,
        height=height,
        batch_size=batch_size,
        steps=steps,
        seed=seed,
        first_frame_name=first_frame_name,
        last_frame_name=last_frame_name,
    )
    reconciled, _remaps = reconcile_workflow_models(injected, obj_info)
    return reconciled


# ---------- Run ComfyUI Image Generation ----------


async def run_comfyui_image(
    job: Dict[str, Any],
    params: Dict[str, Any],
    images_dir: Path,
    ref_image_path: Optional[Path],
    is_cancelled: Callable[[], bool],
    on_prompt_submitted: Callable[[str, str], None],
) -> Tuple[List[Path], Dict[str, Any]]:
    """Run image generation on local or remote (Colab) ComfyUI."""
    req_mode = params.get("comfyui_mode")
    status = await probe_comfyui(mode=req_mode, force=True)
    if not status["online"]:
        raise RuntimeError(
            f"無法連線至 ComfyUI（{status['url']}）：{status.get('error') or '請確認本機或 Colab ComfyUI 已啟動'}。"
        )

    base_url = status["url"].rstrip("/")
    _, _, headers, is_remote = resolve_comfyui_connection(base_url=base_url, mode=status.get("mode"))
    preset_id = str(params.get("comfy_preset") or "comfy_z_image_turbo")
    prompt = str(params.get("prompt", "")).strip()
    neg_prompt = str(params.get("negative_prompt", "")).strip()
    width = int(params.get("width", 1024))
    height = int(params.get("height", 1024))
    steps = int(params.get("steps", 8))
    batch_count = max(1, min(4, int(params.get("batch_count", 1))))
    raw_seed = params.get("seed")
    seed = int(raw_seed) if (raw_seed is not None and str(raw_seed).strip() != "") else random.randint(1, 2147483647)
    lora_name = str(params.get("comfy_lora_name") or "").strip()
    lora_strength = float(params.get("lora_strength", 0.8) or 0.8)
    ckpt_name = str(params.get("comfy_checkpoint") or "").strip()
    detected = status["detected"]

    async with httpx.AsyncClient(timeout=300.0 if is_remote else 120.0, headers=headers, follow_redirects=True) as client:
        ref_name: Optional[str] = None
        if ref_image_path and ref_image_path.exists():
            job["progress"] = 8
            job["message"] = "正在上傳參考圖片至 ComfyUI..."
            ref_name = await _upload_image_to_comfyui(client, base_url, ref_image_path)

        if is_cancelled():
            raise asyncio.CancelledError()

        if preset_id == "comfy_saved_workflow":
            wf_id = str(params.get("comfy_workflow_id") or "").strip()
            if not wf_id:
                raise ValueError("請先從下拉選單選擇一個已安裝的 ComfyUI 工作流。")
            job["progress"] = 10
            job["message"] = "正在載入並轉換 ComfyUI 工作流..."
            raw_wf, wf_name = await fetch_comfyui_workflow_raw(base_url, wf_id, headers=headers)
            workflow = await _prepare_loaded_or_custom_workflow(
                base_url, raw_wf, prompt, neg_prompt, width, height, batch_count, steps, seed, ref_name, None, headers=headers
            )
            model_meta = {"id": f"comfy_wf:{wf_id}", "name": f"ComfyUI 工作流 · {wf_name}", "quantization": "Colab" if is_remote else "Workflow"}
        elif preset_id == "comfy_custom_json":
            raw_str = str(params.get("comfy_workflow_json") or "").strip()
            if not raw_str:
                raise ValueError("請先上傳或貼上 ComfyUI JSON 工作流。")
            raw_wf = json.loads(raw_str)
            workflow = await _prepare_loaded_or_custom_workflow(
                base_url, raw_wf, prompt, neg_prompt, width, height, batch_count, steps, seed, ref_name, None, headers=headers
            )
            model_meta = {"id": "comfy_custom_json", "name": "ComfyUI 自訂工作流", "quantization": "Colab" if is_remote else "JSON"}
        elif preset_id == "comfy_checkpoint":
            if not ckpt_name:
                ckpts = status.get("checkpoints") or []
                if not ckpts:
                    raise RuntimeError("ComfyUI 尚未安裝任何 Checkpoint 底模。")
                ckpt_name = ckpts[0]
            workflow = build_checkpoint_image_workflow(
                ckpt_name, prompt, neg_prompt, width, height, steps, batch_count, seed,
                cfg=float(params.get("cfg_scale", 7.0) or 7.0),
                lora_name=lora_name, lora_strength=lora_strength, ref_image_name=ref_name,
            )
            short_ckpt = Path(ckpt_name).stem
            model_meta = {"id": f"comfy_ckpt:{ckpt_name}", "name": f"ComfyUI · {short_ckpt}", "quantization": "Ckpt"}
        else:
            if detected.get("has_z_image"):
                workflow = build_z_image_turbo_workflow(
                    detected["z_image"], prompt, width, height, steps, batch_count, seed,
                    lora_name=lora_name, lora_strength=lora_strength, ref_image_name=ref_name,
                )
                model_meta = {"id": "comfy_z_image_turbo", "name": "ComfyUI · Z-Image-Turbo", "quantization": "BF16"}
            elif status.get("checkpoints"):
                ck = ckpt_name or status["checkpoints"][0]
                workflow = build_checkpoint_image_workflow(
                    ck, prompt, neg_prompt, width, height, steps, batch_count, seed,
                    lora_name=lora_name, lora_strength=lora_strength, ref_image_name=ref_name,
                )
                model_meta = {"id": f"comfy_ckpt:{ck}", "name": f"ComfyUI · {Path(ck).stem}", "quantization": "Ckpt"}
            else:
                raise RuntimeError("ComfyUI 中未偵測到圖片生成模型，請選擇「已安裝工作流」或檢查模型目錄。")

        hist_entry = await _submit_and_wait_comfyui(
            client, base_url, workflow, model_meta["name"], job, is_cancelled, on_prompt_submitted, est_scale_sec=20.0
        )

        # Collect generated images (preferring 'output' saved images over intermediate 'temp' previews)
        outputs = hist_entry.get("outputs", {})
        saved_imgs: List[Dict[str, Any]] = []
        temp_imgs: List[Dict[str, Any]] = []
        for _nid, node_out in outputs.items():
            if not isinstance(node_out, dict):
                continue
            for item in node_out.get("images") or []:
                fn = str(item.get("filename", ""))
                if not fn or fn.lower().endswith((".mp4", ".webm", ".mov", ".avi")):
                    continue
                if item.get("type", "output") == "output":
                    saved_imgs.append(item)
                else:
                    temp_imgs.append(item)

        chosen_imgs = saved_imgs or temp_imgs
        if not chosen_imgs:
            raise RuntimeError("ComfyUI 工作流已執行完畢，但未在節點輸出中找到圖片（請確認包含 SaveImage 或 PreviewImage 節點）。")

        job["progress"] = 95
        job["message"] = f"正在從 ComfyUI 下載 {len(chosen_imgs)} 張高品質成品圖片..."
        out_paths: List[Path] = []
        for idx, info in enumerate(chosen_imgs):
            view_resp = await client.get(
                f"{base_url}/view",
                params={
                    "filename": info["filename"],
                    "subfolder": info.get("subfolder", ""),
                    "type": info.get("type", "output"),
                },
            )
            view_resp.raise_for_status()
            ext = Path(info["filename"]).suffix.lower() or ".png"
            out_path = images_dir / f"comfy_{int(time.time())}_{job['id']}_{idx}{ext}"
            out_path.write_bytes(view_resp.content)
            out_paths.append(out_path)

        return out_paths, model_meta


# ---------- Run ComfyUI Video Generation ----------


async def run_comfyui_video(
    job: Dict[str, Any],
    params: Dict[str, Any],
    videos_dir: Path,
    first_frame_path: Optional[Path],
    last_frame_path: Optional[Path],
    is_cancelled: Callable[[], bool],
    on_prompt_submitted: Callable[[str, str], None],
) -> Tuple[Path, Dict[str, Any]]:
    """Submit a video workflow to local or remote (Colab) ComfyUI, track execution, download & save MP4."""
    req_mode = params.get("comfyui_mode")
    status = await probe_comfyui(mode=req_mode, force=True)
    if not status["online"]:
        raise RuntimeError(
            f"無法連線至 ComfyUI（{status['url']}）：{status.get('error') or '請確認本機或 Colab ComfyUI 已啟動'}。"
        )

    base_url = status["url"].rstrip("/")
    _, _, headers, is_remote = resolve_comfyui_connection(base_url=base_url, mode=status.get("mode"))
    preset_id = str(params.get("comfy_preset") or params.get("model_id") or "comfy_ltx25")
    prompt = str(params.get("prompt", "")).strip()
    neg_prompt = str(params.get("negative_prompt", "")).strip()
    width = int(params.get("width", 832))
    height = int(params.get("height", 480))
    duration = max(1, min(int(params.get("duration", 5)), 15))
    steps = int(params.get("steps", 8))
    raw_seed = params.get("seed")
    seed = int(raw_seed) if (raw_seed is not None and str(raw_seed).strip() != "") else random.randint(1, 2147483647)
    detected = status["detected"]
    node_prefix = "Colab ComfyUI" if is_remote else "ComfyUI"

    async with httpx.AsyncClient(timeout=300.0 if is_remote else 120.0, headers=headers, follow_redirects=True) as client:
        ff_name: Optional[str] = None
        lf_name: Optional[str] = None
        if first_frame_path and first_frame_path.exists():
            job["progress"] = 8
            job["message"] = f"正在上傳首幀圖片至 {node_prefix}..."
            ff_name = await _upload_image_to_comfyui(client, base_url, first_frame_path)
        if last_frame_path and last_frame_path.exists():
            job["progress"] = 10
            job["message"] = f"正在上傳尾幀圖片至 {node_prefix}..."
            lf_name = await _upload_image_to_comfyui(client, base_url, last_frame_path)

        if is_cancelled():
            raise asyncio.CancelledError()

        if preset_id == "comfy_saved_workflow":
            wf_id = str(params.get("comfy_workflow_id") or "").strip()
            if not wf_id:
                raise ValueError("請先從下拉選單選擇一個已安裝的 ComfyUI 工作流。")
            job["progress"] = 12
            job["message"] = f"正在載入並轉換 {node_prefix} 影片工作流..."
            raw_wf, wf_name = await fetch_comfyui_workflow_raw(base_url, wf_id, headers=headers)
            workflow = await _prepare_loaded_or_custom_workflow(
                base_url, raw_wf, prompt, neg_prompt, width, height, 1, steps, seed, ff_name, lf_name, headers=headers
            )
            model_meta = {"id": f"comfy_wf:{wf_id}", "name": f"{node_prefix} 工作流 · {wf_name}", "quantization": "Colab" if is_remote else "Workflow"}
        elif preset_id == "comfy_custom_json":
            custom_json = str(params.get("comfy_workflow_json") or "").strip()
            if not custom_json:
                raise ValueError("請先上傳或貼上 ComfyUI JSON 工作流檔案。")
            raw_wf = json.loads(custom_json)
            workflow = await _prepare_loaded_or_custom_workflow(
                base_url, raw_wf, prompt, neg_prompt, width, height, 1, steps, seed, ff_name, lf_name, headers=headers
            )
            model_meta = {"id": "comfy_custom_json", "name": f"{node_prefix} 自訂工作流", "quantization": "Colab" if is_remote else "JSON"}
        elif preset_id == "comfy_ltx25":
            if not detected.get("has_ltx25"):
                raise RuntimeError("ComfyUI 尚未安裝完整 LTX-2.5 權重（需要 UNET + Gemma4 CLIP + Video/Audio VAE + x2 Upscaler）。")
            workflow = build_ltx25_workflow(detected["ltx25"], prompt, neg_prompt, width, height, duration, seed, ff_name)
            model_meta = {"id": "comfy_ltx25", "name": "ComfyUI · LTX-2.5 22B Distilled", "quantization": "INT8"}
        elif preset_id in ("comfy_minimax_h3_turbo", "comfy_minimax_h3"):
            if not detected.get("has_minimax_h3"):
                raise RuntimeError("ComfyUI 尚未安裝完整 MiniMax-H3 權重（需要 UNET + Qwen3VL CLIP + Video/Audio VAE）。")
            use_turbo = preset_id == "comfy_minimax_h3_turbo" and bool(detected.get("has_minimax_turbo_lora"))
            workflow = build_minimax_h3_workflow(
                detected["minimax_h3"], prompt, width, height, duration,
                steps if steps else (8 if use_turbo else 20), seed,
                use_turbo=use_turbo, first_frame_name=ff_name, last_frame_name=lf_name,
            )
            label = "INT8 · 8步Turbo" if use_turbo else "INT8 · 20步"
            model_meta = {"id": preset_id, "name": "ComfyUI · MiniMax-H3 FL2VA", "quantization": label}
        else:
            if detected.get("has_ltx25"):
                workflow = build_ltx25_workflow(detected["ltx25"], prompt, neg_prompt, width, height, duration, seed, ff_name)
                model_meta = {"id": "comfy_ltx25", "name": "ComfyUI · LTX-2.5 22B Distilled", "quantization": "INT8"}
            elif detected.get("has_minimax_h3"):
                use_turbo = bool(detected.get("has_minimax_turbo_lora"))
                workflow = build_minimax_h3_workflow(
                    detected["minimax_h3"], prompt, width, height, duration, 8 if use_turbo else 20, seed, use_turbo, ff_name, lf_name
                )
                model_meta = {"id": "comfy_minimax_h3_turbo", "name": "ComfyUI · MiniMax-H3 FL2VA", "quantization": "INT8"}
            else:
                raise RuntimeError("ComfyUI 中未偵測到 LTX-2.5 或 MiniMax-H3 影片權重，請使用「已安裝工作流」或檢查模型目錄。")

        hist_entry = await _submit_and_wait_comfyui(
            client, base_url, workflow, model_meta["name"], job, is_cancelled, on_prompt_submitted, est_scale_sec=75.0
        )

        outputs = hist_entry.get("outputs", {})
        video_file_info: Optional[Dict[str, Any]] = None
        for _nid, node_out in outputs.items():
            if not isinstance(node_out, dict):
                continue
            for key in ("videos", "images", "gifs"):
                arr = node_out.get(key)
                if isinstance(arr, list) and arr:
                    for item in arr:
                        fn = str(item.get("filename", ""))
                        if fn.lower().endswith((".mp4", ".webm", ".mov", ".mkv", ".avi", ".gif")):
                            video_file_info = item
                            break
                        if key in ("videos", "gifs") and fn:
                            video_file_info = item
                            break
                if video_file_info:
                    break
            if video_file_info:
                break

        if not video_file_info:
            raise RuntimeError("ComfyUI 工作流已執行完畢，但未在節點輸出中找到影片檔（請確認工作流包含 SaveVideo 節點）。")

        job["progress"] = 95
        job["message"] = "正在從 ComfyUI 下載高品質成品影片..."
        fname = video_file_info["filename"]
        view_resp = await client.get(
            f"{base_url}/view",
            params={
                "filename": fname,
                "subfolder": video_file_info.get("subfolder", ""),
                "type": video_file_info.get("type", "output"),
            },
        )
        view_resp.raise_for_status()

        ext = Path(fname).suffix.lower() or ".mp4"
        base_stem = f"comfy_{int(time.time())}_{job['id']}"
        raw_path = videos_dir / f"{base_stem}{ext}"
        raw_path.write_bytes(view_resp.content)

        final_path = raw_path
        if ext != ".mp4":
            job["progress"] = 98
            job["message"] = "正在封裝為瀏覽器相容 MP4 (H.264/AAC)..."
            final_path = await _transcode_to_mp4(raw_path, videos_dir / f"{base_stem}.mp4")

        return final_path, model_meta


# ---------- Jimeng / Volcengine Ark Seedance Cloud Video API ----------


async def run_jimeng_video(
    job: Dict[str, Any],
    params: Dict[str, Any],
    videos_dir: Path,
    is_cancelled: Callable[[], bool],
) -> Tuple[Path, Dict[str, Any]]:
    """Generate video via Jimeng / ByteDance Volcengine Ark Seedance async task API."""
    cfg = config_manager.config
    api_base = str(params.get("jimeng_api_base") or cfg.jimeng_api_base or "https://ark.cn-beijing.volces.com/api/v3").strip().rstrip("/")
    api_key = str(params.get("jimeng_api_key") or cfg.jimeng_api_key or "").strip()
    model_name = str(params.get("jimeng_model") or cfg.jimeng_model or "doubao-seedance-1-5-pro-251215").strip()
    if not api_key:
        raise RuntimeError("尚未設定「即夢 API Key」。請前往「設定 → 即夢 API（火山方舟 Seedance）」填寫 API Key 後再試。")

    prompt = str(params.get("prompt", "")).strip()
    duration = max(4, min(int(params.get("duration", 5)), 12))
    ratio = str(params.get("ratio") or "adaptive").strip()
    if ratio in ("source", "custom", ""):
        ratio = "adaptive"
    generate_audio = bool(params.get("generate_audio", cfg.jimeng_generate_audio))
    watermark = bool(params.get("watermark", cfg.jimeng_watermark))

    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    if params.get("first_frame_data_url"):
        content.append({
            "type": "image_url",
            "image_url": {"url": params["first_frame_data_url"]},
            "role": "first_frame",
        })
    if params.get("last_frame_data_url"):
        content.append({
            "type": "image_url",
            "image_url": {"url": params["last_frame_data_url"]},
            "role": "last_frame",
        })

    payload: Dict[str, Any] = {
        "model": model_name,
        "content": content,
        "ratio": ratio,
        "duration": duration,
        "generate_audio": generate_audio,
        "watermark": watermark,
    }
    raw_seed = params.get("seed")
    if raw_seed is not None and str(raw_seed).strip() != "":
        payload["seed"] = int(raw_seed)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        job["progress"] = 10
        job["message"] = f"正在送出即夢 API ({model_name}) 影片生成任務..."
        create_resp = await client.post(f"{api_base}/contents/generations/tasks", headers=headers, json=payload)
        if create_resp.status_code >= 400:
            raise RuntimeError(f"即夢 API 建立任務失敗 (HTTP {create_resp.status_code})：{create_resp.text[:400]}")
        create_data = create_resp.json()
        task_id = str(create_data.get("id") or create_data.get("task_id") or "")
        if not task_id:
            raise RuntimeError(f"即夢 API 未回傳任務 ID：{json.dumps(create_data, ensure_ascii=False)[:300]}")

        t0 = time.monotonic()
        video_url = ""
        while True:
            if is_cancelled():
                try:
                    await client.delete(f"{api_base}/contents/generations/tasks/{task_id}", headers=headers)
                except Exception:
                    pass
                raise asyncio.CancelledError()

            await asyncio.sleep(2.5)
            elapsed = int(time.monotonic() - t0)
            poll_resp = await client.get(f"{api_base}/contents/generations/tasks/{task_id}", headers=headers)
            if poll_resp.status_code >= 400:
                raise RuntimeError(f"即夢 API 查詢進度失敗 (HTTP {poll_resp.status_code})：{poll_resp.text[:300]}")
            pdata = poll_resp.json()
            status_val = str(pdata.get("status", "")).lower()
            if status_val in ("succeeded", "success", "completed"):
                content_obj = pdata.get("content") or {}
                if isinstance(content_obj, dict):
                    video_url = str(content_obj.get("video_url") or "")
                if not video_url:
                    video_url = str(pdata.get("video_url") or "")
                break
            elif status_val in ("failed", "error", "cancelled", "expired"):
                err_obj = pdata.get("error") or pdata
                raise RuntimeError(f"即夢 API 任務狀態 {status_val}：{json.dumps(err_obj, ensure_ascii=False)[:400]}")
            else:
                est_pct = min(90, int(18 + 72 * (1.0 - (1.0 / (1.0 + elapsed / 45.0)))))
                job["progress"] = max(job.get("progress", 18), est_pct)
                job["message"] = f"即夢雲端渲染中（狀態：{status_val or 'running'} · 已耗時 {elapsed}s）..."

        if not video_url:
            raise RuntimeError("即夢 API 任務已完成，但回應中未包含 video_url。")

        job["progress"] = 95
        job["message"] = "正在下載即夢 API 生成的成品影片..."
        dl_resp = await client.get(video_url)
        dl_resp.raise_for_status()
        out_path = videos_dir / f"jimeng_{int(time.time())}_{job['id']}.mp4"
        out_path.write_bytes(dl_resp.content)
        model_meta = {"id": f"jimeng:{model_name}", "name": f"即夢 API · {model_name}", "quantization": "Cloud"}
        return out_path, model_meta
