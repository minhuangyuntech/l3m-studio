from __future__ import annotations

import asyncio
import copy
import json
import platform
import random
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from .config import config_manager

# Short TTL cache for ComfyUI status probes so 2.5s UI polling stays instant
_PROBE_CACHE: Dict[str, Any] = {"ts": 0.0, "url": "", "data": None}
_PROBE_TTL = 12.0


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


async def probe_comfyui(base_url: Optional[str] = None, force: bool = False, timeout: float = 3.0) -> Dict[str, Any]:
    """Probe a running ComfyUI server and detect available high-precision video pipelines."""
    configured = (base_url or config_manager.config.comfyui_url or "http://127.0.0.1:8000").strip().rstrip("/")
    now = time.monotonic()
    if (
        not force
        and _PROBE_CACHE["data"] is not None
        and _PROBE_CACHE["url"] == configured
        and (now - _PROBE_CACHE["ts"]) < _PROBE_TTL
    ):
        return _PROBE_CACHE["data"]

    candidates = [configured]
    if not base_url:
        for fb in ("http://127.0.0.1:8000", "http://127.0.0.1:8188"):
            if fb not in candidates:
                candidates.append(fb)

    result: Dict[str, Any] = {
        "online": False,
        "url": configured,
        "version": "",
        "gpu_name": "",
        "error": "",
        "unets": [],
        "clips": [],
        "vaes": [],
        "upscalers": [],
        "loras": [],
        "detected": {},
        "presets": [],
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
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
            except Exception as exc:
                last_err = str(exc)

        if not active_url:
            result["error"] = last_err or f"無法連線至 ComfyUI ({configured})"
            _PROBE_CACHE.update({"ts": now, "url": configured, "data": result})
            return result

        # Auto-update saved URL if we discovered ComfyUI running on the alternate default port
        if not base_url and active_url != configured and configured in ("http://127.0.0.1:8188", "http://127.0.0.1:8000"):
            config_manager.update({"comfyui_url": active_url})

        result["online"] = True
        result["url"] = active_url
        sys_info = sys_data.get("system", {})
        result["version"] = str(sys_info.get("comfyui_version", ""))
        devices = sys_data.get("devices", [])
        if devices:
            result["gpu_name"] = str(devices[0].get("name", ""))

        # Query only the specific loader/video nodes we need (fast & lightweight)
        node_names = [
            "UNETLoader",
            "CLIPLoader",
            "VAELoader",
            "LatentUpscaleModelLoader",
            "LoraLoaderModelOnly",
            "MiniMaxH3ImageToVideo",
            "LTXVDualCFGGuider",
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

        unets = _extract_combo_list(node_infos.get("UNETLoader", {}), "unet_name")
        clips = _extract_combo_list(node_infos.get("CLIPLoader", {}), "clip_name")
        vaes = _extract_combo_list(node_infos.get("VAELoader", {}), "vae_name")
        upscalers = _extract_combo_list(node_infos.get("LatentUpscaleModelLoader", {}), "model_name")
        loras = _extract_combo_list(node_infos.get("LoraLoaderModelOnly", {}), "lora_name")

        result["unets"] = unets
        result["clips"] = clips
        result["vaes"] = vaes
        result["upscalers"] = upscalers
        result["loras"] = loras

        # Detect LTX-2.5 22B Distilled INT8 pipeline
        ltx_unet = _pick(unets, "ltx-2.5") or _pick(unets, "ltx2.5") or _pick(unets, "ltx")
        ltx_clip = _pick(clips, "gemma4", "ltx-2.5") or _pick(clips, "gemma4", "ltx") or _pick(clips, "gemma")
        ltx_v_vae = _pick(vaes, "ltx-2.5", "video") or _pick(vaes, "ltx", "video")
        ltx_a_vae = _pick(vaes, "ltx-2.5", "audio") or _pick(vaes, "ltx", "audio")
        ltx_up = _pick(upscalers, "ltx-2.5") or _pick(upscalers, "ltx")
        has_ltx25 = bool(
            ltx_unet and ltx_clip and ltx_v_vae and ltx_a_vae and ltx_up and "LTXVDualCFGGuider" in node_infos
        )

        # Detect MiniMax-H3 FL2VA INT8 pipeline
        mm_unet = _pick(unets, "minimax_h3") or _pick(unets, "minimax")
        mm_clip = _pick(clips, "minimax_h3") or _pick(clips, "qwen3vl", "minimax")
        mm_v_vae = _pick(vaes, "minimax_h3", "video") or _pick(vaes, "minimax", "video")
        mm_a_vae = _pick(vaes, "minimax_h3", "audio") or _pick(vaes, "minimax", "audio")
        mm_turbo_lora = _pick(loras, "minimax_h3", "turbo") or _pick(loras, "minimax", "8step")
        has_minimax = bool(mm_unet and mm_clip and mm_v_vae and mm_a_vae and "MiniMaxH3ImageToVideo" in node_infos)

        result["detected"] = {
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
            "id": "comfy_custom_json",
            "name": "自訂 ComfyUI API 工作流 (JSON)",
            "description": "匯入 ComfyUI 匯出的 API 格式 JSON（自動注入提示詞、種子與首尾幀圖片）。",
            "default_steps": 20,
            "default_duration": 5,
            "supports_first_frame": True,
            "supports_last_frame": True,
            "supports_audio": True,
            "badge": "進階自訂",
        })
        result["presets"] = presets

    _PROBE_CACHE.update({"ts": now, "url": configured, "data": result})
    return result


async def interrupt_comfyui(base_url: str, prompt_id: str = "") -> None:
    url = (base_url or config_manager.config.comfyui_url).strip().rstrip("/")
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            if prompt_id:
                await client.post(f"{url}/queue", json={"delete": [prompt_id]})
            await client.post(f"{url}/interrupt")
    except Exception:
        pass


def _snap(val: int, mult: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(val / mult) * mult)))


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
    # Final resolution multiple of 64 so stage-1 half-res is cleanly a multiple of 32
    full_w = _snap(width, 64, 512, 1280)
    full_h = _snap(height, 64, 384, 1280)
    half_w = full_w // 2
    half_h = full_h // 2
    fps = 24.0
    frames = max(25, min(241, int(duration) * 24 + 1))
    effective_neg = neg_prompt.strip() or "pc game, console game, video game, cartoon, childish, ugly, blurry, distorted face"

    wf: Dict[str, Any] = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": detected["unet"], "weight_dtype": "default"},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": detected["clip"], "type": "ltxv", "device": "default"},
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": detected["video_vae"]},
        },
        "4": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": detected["audio_vae"]},
        },
        "5": {
            "class_type": "LatentUpscaleModelLoader",
            "inputs": {"model_name": detected["upscaler"]},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["2", 0]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": effective_neg, "clip": ["2", 0]},
        },
        "8": {
            "class_type": "LTXVConditioning",
            "inputs": {"positive": ["6", 0], "negative": ["7", 0], "frame_rate": fps},
        },
        "9": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {"width": half_w, "height": half_h, "length": frames, "batch_size": 1},
        },
        "10": {
            "class_type": "LTXVEmptyLatentAudio",
            "inputs": {"frames_number": frames, "frame_rate": fps, "batch_size": 1, "audio_vae": ["4", 0]},
        },
    }

    stage1_video_latent: Any = ["9", 0]
    if first_frame_name:
        wf["11"] = {"class_type": "LoadImage", "inputs": {"image": first_frame_name}}
        wf["12"] = {"class_type": "LTXVPreprocess", "inputs": {"image": ["11", 0], "img_compression": 18}}
        wf["13"] = {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {
                "vae": ["3", 0],
                "image": ["12", 0],
                "latent": ["9", 0],
                "strength": 0.7,
                "bypass": False,
            },
        }
        stage1_video_latent = ["13", 0]

    # Stage 1 Distilled 8-step AV sampling
    wf["14"] = {
        "class_type": "LTXVConcatAVLatent",
        "inputs": {"video_latent": stage1_video_latent, "audio_latent": ["10", 0]},
    }
    wf["15"] = {
        "class_type": "LTXVDualCFGGuider",
        "inputs": {
            "model": ["1", 0],
            "positive": ["8", 0],
            "negative": ["8", 1],
            "video_cfg": 1.0,
            "audio_cfg": 1.0,
        },
    }
    wf["16"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}}
    wf["17"] = {
        "class_type": "ManualSigmas",
        "inputs": {"sigmas": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"},
    }
    wf["18"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": int(seed)}}
    wf["19"] = {
        "class_type": "SamplerCustomAdvanced",
        "inputs": {
            "noise": ["18", 0],
            "guider": ["15", 0],
            "sampler": ["16", 0],
            "sigmas": ["17", 0],
            "latent_image": ["14", 0],
        },
    }
    wf["20"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["19", 0]}}

    # Stage 2 Spatial x2 Latent Upscale + 3-step Refinement
    wf["21"] = {
        "class_type": "LTXVLatentUpsampler",
        "inputs": {"samples": ["20", 0], "upscale_model": ["5", 0], "vae": ["3", 0]},
    }
    stage2_video_latent: Any = ["21", 0]
    if first_frame_name:
        wf["22"] = {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {
                "vae": ["3", 0],
                "image": ["12", 0],
                "latent": ["21", 0],
                "strength": 1.0,
                "bypass": False,
            },
        }
        stage2_video_latent = ["22", 0]

    wf["23"] = {
        "class_type": "LTXVConcatAVLatent",
        "inputs": {"video_latent": stage2_video_latent, "audio_latent": ["20", 1]},
    }
    wf["24"] = {
        "class_type": "ManualSigmas",
        "inputs": {"sigmas": "0.85, 0.7250, 0.4219, 0.0"},
    }
    wf["25"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}}
    wf["26"] = {
        "class_type": "SamplerCustomAdvanced",
        "inputs": {
            "noise": ["25", 0],
            "guider": ["15", 0],
            "sampler": ["16", 0],
            "sigmas": ["24", 0],
            "latent_image": ["23", 0],
        },
    }
    wf["27"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["26", 0]}}

    # Tiled Video Decode (8GB VRAM safe) + Audio Decode + SaveVideo MP4
    wf["28"] = {
        "class_type": "VAEDecodeTiled",
        "inputs": {
            "samples": ["27", 0],
            "vae": ["3", 0],
            "tile_size": 512,
            "overlap": 64,
            "temporal_size": 64,
            "temporal_overlap": 16,
        },
    }
    wf["29"] = {
        "class_type": "LTXVAudioVAEDecode",
        "inputs": {"samples": ["27", 1], "audio_vae": ["4", 0]},
    }
    wf["30"] = {
        "class_type": "CreateVideo",
        "inputs": {"images": ["28", 0], "audio": ["29", 0], "fps": fps},
    }
    wf["31"] = {
        "class_type": "SaveVideo",
        "inputs": {
            "video": ["30", 0],
            "filename_prefix": f"video/L3M_LTX25_{int(time.time())}",
            "format": "auto",
            "codec": "auto",
        },
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
    # Official template frame snapping to 17k + 5 at 24fps (e.g. 5s -> 124 frames)
    raw = max(5, round(int(duration) * 24))
    length = raw + (5 - (raw % 17)) % 17
    length = max(22, min(243, length))
    effective_steps = max(4, min(40, int(steps or (8 if use_turbo else 20))))

    wf: Dict[str, Any] = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": detected["unet"], "weight_dtype": "default"},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": detected["clip"], "type": "minimax", "device": "default"},
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": detected["video_vae"]},
        },
        "4": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": detected["audio_vae"]},
        },
    }

    model_ref: Any = ["1", 0]
    if use_turbo and detected.get("turbo_lora"):
        wf["5"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["1", 0],
                "lora_name": detected["turbo_lora"],
                "strength_model": 1.0,
            },
        }
        model_ref = ["5", 0]

    mm_inputs: Dict[str, Any] = {
        "clip": ["2", 0],
        "vae": ["3", 0],
        "prompt": prompt,
        "width": w,
        "height": h,
        "length": length,
    }
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
    wf["12"] = {
        "class_type": "BasicScheduler",
        "inputs": {"model": model_ref, "scheduler": "simple", "steps": effective_steps, "denoise": 1.0},
    }
    wf["13"] = {
        "class_type": "SamplerCustomAdvanced",
        "inputs": {
            "noise": ["10", 0],
            "guider": ["9", 0],
            "sampler": ["11", 0],
            "sigmas": ["12", 0],
            "latent_image": ["8", 1],
        },
    }
    wf["14"] = {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["3", 0]}}
    wf["15"] = {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["13", 0], "vae": ["4", 0]}}
    wf["16"] = {
        "class_type": "CreateVideo",
        "inputs": {"images": ["14", 0], "audio": ["15", 0], "fps": 24.0},
    }
    wf["17"] = {
        "class_type": "SaveVideo",
        "inputs": {
            "video": ["16", 0],
            "filename_prefix": f"video/L3M_MiniMaxH3_{int(time.time())}",
            "format": "auto",
            "codec": "auto",
        },
    }
    return wf


def prepare_custom_workflow(
    raw_json: str,
    prompt: str,
    neg_prompt: str,
    width: int,
    height: int,
    steps: int,
    seed: int,
    first_frame_name: Optional[str],
    last_frame_name: Optional[str],
) -> Dict[str, Any]:
    """Load user-supplied ComfyUI API workflow JSON and inject prompt/seed/frames."""
    try:
        wf = json.loads(raw_json)
    except Exception as exc:
        raise ValueError(f"自訂 ComfyUI API JSON 解析失敗：{exc}")
    if not isinstance(wf, dict) or ("nodes" in wf and "links" in wf):
        raise ValueError("請上傳 ComfyUI「Export (API)」格式的 JSON（而非一般 UI 工作流 JSON）。")

    serialized = json.dumps(wf, ensure_ascii=False)
    had_placeholder = False
    replacements = {
        "{{PROMPT}}": prompt,
        "{{NEGATIVE_PROMPT}}": neg_prompt,
        "{{FIRST_FRAME}}": first_frame_name or "",
        "{{LAST_FRAME}}": last_frame_name or "",
    }
    for token, val in replacements.items():
        if token in serialized:
            had_placeholder = True
            serialized = serialized.replace(token, val.replace('"', '\\"'))
    wf = json.loads(serialized)

    if not had_placeholder:
        wf = copy.deepcopy(wf)
        prompt_set = False
        img_nodes: List[str] = []
        for nid, node in wf.items():
            if not isinstance(node, dict):
                continue
            ctype = str(node.get("class_type", ""))
            inputs = node.get("inputs", {})
            if not isinstance(inputs, dict):
                continue
            if not prompt_set and ctype in ("MiniMaxH3ImageToVideo", "CLIPTextEncode"):
                if "prompt" in inputs and isinstance(inputs["prompt"], str):
                    inputs["prompt"] = prompt
                    prompt_set = True
                elif "text" in inputs and isinstance(inputs["text"], str):
                    inputs["text"] = prompt
                    prompt_set = True
            if ctype == "LoadImage":
                img_nodes.append(nid)
            if "noise_seed" in inputs and isinstance(inputs["noise_seed"], int):
                inputs["noise_seed"] = int(seed)
            elif "seed" in inputs and isinstance(inputs["seed"], int):
                inputs["seed"] = int(seed)
            if ctype in ("BasicScheduler", "KSampler") and "steps" in inputs and isinstance(inputs["steps"], int):
                inputs["steps"] = int(steps)
        if first_frame_name and len(img_nodes) >= 1:
            wf[img_nodes[0]]["inputs"]["image"] = first_frame_name
        if last_frame_name and len(img_nodes) >= 2:
            wf[img_nodes[1]]["inputs"]["image"] = last_frame_name
    return wf


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
    ff_kwargs: Dict[str, Any] = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.STDOUT,
    }
    if platform.system() == "Windows":
        ff_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    proc = await asyncio.create_subprocess_exec(
        ffmpeg_bin,
        "-y",
        "-i",
        str(src),
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
        str(dst),
        **ff_kwargs,
    )
    await proc.communicate()
    if proc.returncode == 0 and dst.exists() and dst.stat().st_size > 1024:
        src.unlink(missing_ok=True)
        return dst
    return src


async def run_comfyui_video(
    job: Dict[str, Any],
    params: Dict[str, Any],
    videos_dir: Path,
    first_frame_path: Optional[Path],
    last_frame_path: Optional[Path],
    is_cancelled: Callable[[], bool],
    on_prompt_submitted: Callable[[str, str], None],
) -> Tuple[Path, Dict[str, Any]]:
    """Submit a video workflow to local ComfyUI, track execution, download & save MP4."""
    status = await probe_comfyui(force=True)
    if not status["online"]:
        raise RuntimeError(
            f"無法連線至 ComfyUI（{status['url']}）。請確認 ComfyUI 已在背景啟動，或於「設定」檢查 ComfyUI 伺服器網址。"
        )

    base_url = status["url"].rstrip("/")
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
    client_id = f"l3m_{uuid.uuid4().hex[:10]}"

    async with httpx.AsyncClient(timeout=120.0) as client:
        ff_name: Optional[str] = None
        lf_name: Optional[str] = None
        if first_frame_path and first_frame_path.exists():
            job["progress"] = 8
            job["message"] = "正在上傳首幀圖片至 ComfyUI..."
            ff_name = await _upload_image_to_comfyui(client, base_url, first_frame_path)
        if last_frame_path and last_frame_path.exists():
            job["progress"] = 10
            job["message"] = "正在上傳尾幀圖片至 ComfyUI..."
            lf_name = await _upload_image_to_comfyui(client, base_url, last_frame_path)

        if is_cancelled():
            raise asyncio.CancelledError()

        if preset_id == "comfy_custom_json":
            custom_json = str(params.get("comfy_workflow_json") or "").strip()
            if not custom_json:
                raise ValueError("請先上傳或貼上 ComfyUI API 格式的 JSON 工作流檔案。")
            workflow = prepare_custom_workflow(
                custom_json, prompt, neg_prompt, width, height, steps, seed, ff_name, lf_name
            )
            model_meta = {"id": "comfy_custom_json", "name": "ComfyUI 自訂工作流", "quantization": "API"}
        elif preset_id == "comfy_ltx25":
            if not detected.get("has_ltx25"):
                raise RuntimeError("ComfyUI 尚未安裝完整 LTX-2.5 權重（需要 UNET + Gemma4 CLIP + Video/Audio VAE + x2 Upscaler）。")
            workflow = build_ltx25_workflow(
                detected["ltx25"], prompt, neg_prompt, width, height, duration, seed, ff_name
            )
            model_meta = {"id": "comfy_ltx25", "name": "ComfyUI · LTX-2.5 22B Distilled", "quantization": "INT8"}
        elif preset_id in ("comfy_minimax_h3_turbo", "comfy_minimax_h3"):
            if not detected.get("has_minimax_h3"):
                raise RuntimeError("ComfyUI 尚未安裝完整 MiniMax-H3 權重（需要 UNET + Qwen3VL CLIP + Video/Audio VAE）。")
            use_turbo = preset_id == "comfy_minimax_h3_turbo" and bool(detected.get("has_minimax_turbo_lora"))
            workflow = build_minimax_h3_workflow(
                detected["minimax_h3"],
                prompt,
                width,
                height,
                duration,
                steps if steps else (8 if use_turbo else 20),
                seed,
                use_turbo=use_turbo,
                first_frame_name=ff_name,
                last_frame_name=lf_name,
            )
            label = "INT8 · 8步Turbo" if use_turbo else "INT8 · 20步"
            model_meta = {"id": preset_id, "name": "ComfyUI · MiniMax-H3 FL2VA", "quantization": label}
        else:
            # Fallback to first available preset
            if detected.get("has_ltx25"):
                workflow = build_ltx25_workflow(
                    detected["ltx25"], prompt, neg_prompt, width, height, duration, seed, ff_name
                )
                model_meta = {"id": "comfy_ltx25", "name": "ComfyUI · LTX-2.5 22B Distilled", "quantization": "INT8"}
            elif detected.get("has_minimax_h3"):
                use_turbo = bool(detected.get("has_minimax_turbo_lora"))
                workflow = build_minimax_h3_workflow(
                    detected["minimax_h3"], prompt, width, height, duration, 8 if use_turbo else 20, seed, use_turbo, ff_name, lf_name
                )
                model_meta = {"id": "comfy_minimax_h3_turbo", "name": "ComfyUI · MiniMax-H3 FL2VA", "quantization": "INT8"}
            else:
                raise RuntimeError("ComfyUI 中未偵測到 LTX-2.5 或 MiniMax-H3 影片權重，請使用「自訂 API JSON」或檢查模型目錄。")

        job["progress"] = 14
        job["message"] = f"正在送出 {model_meta['name']} 工作流至 ComfyUI ({base_url})..."
        submit_resp = await client.post(
            f"{base_url}/prompt",
            json={"prompt": workflow, "client_id": client_id},
        )
        if submit_resp.status_code != 200:
            err_body = submit_resp.text[:500]
            raise RuntimeError(f"ComfyUI 拒絕執行工作流 (HTTP {submit_resp.status_code})：{err_body}")
        submit_data = submit_resp.json()
        node_errors = submit_data.get("node_errors")
        if node_errors:
            raise RuntimeError(f"ComfyUI 節點參數驗證錯誤：{json.dumps(node_errors, ensure_ascii=False)[:400]}")
        prompt_id = str(submit_data.get("prompt_id", ""))
        if not prompt_id:
            raise RuntimeError("ComfyUI 未回傳 prompt_id。")
        on_prompt_submitted(base_url, prompt_id)

        # Poll ComfyUI queue + history until completed
        t_start = time.monotonic()
        hist_entry: Optional[Dict[str, Any]] = None
        while True:
            if is_cancelled():
                await interrupt_comfyui(base_url, prompt_id)
                raise asyncio.CancelledError()

            await asyncio.sleep(1.5)
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
                        err_detail = json.dumps(msgs, ensure_ascii=False)[:400]
                        raise RuntimeError(f"ComfyUI 執行發生錯誤：{err_detail}")
                    if status_obj.get("completed") or hist_entry.get("outputs"):
                        break

            # Inspect queue to show whether we are pending or actively running
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
                        # Smooth asymptotic progress indicator while ComfyUI renders on GPU
                        est_pct = min(92, int(20 + 72 * (1.0 - (1.0 / (1.0 + elapsed / 75.0)))))
                        job["progress"] = max(job.get("progress", 20), est_pct)
                        job["message"] = f"ComfyUI GPU 渲染中（{model_meta['name']} · 已耗時 {elapsed}s）..."
                    elif elapsed > 12:
                        # Not in queue and not in history yet — check once more next iteration
                        job["message"] = f"正在同步 ComfyUI 輸出結果（{elapsed}s）..."
            except Exception:
                pass

        # Extract saved video output from history
        outputs = (hist_entry or {}).get("outputs", {})
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
        sub = video_file_info.get("subfolder", "")
        ftype = video_file_info.get("type", "output")
        view_resp = await client.get(
            f"{base_url}/view",
            params={"filename": fname, "subfolder": sub, "type": ftype},
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

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

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
