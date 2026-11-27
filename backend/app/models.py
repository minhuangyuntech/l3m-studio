from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .config import config_manager
from .gguf_parser import infer_quant_from_name, parse_gguf_metadata
from .hardware import get_hardware_info
from .tiering import plan_auto_tiering


SPLIT_GGUF_RE = re.compile(r"^(.*)-(\d{5})-of-(\d{5})\.gguf$", re.IGNORECASE)

RECOMMENDED_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "unsloth/Qwen3.6-35B-A3B-GGUF",
        "name": "Qwen3.6 35B-A3B (MoE)",
        "repo": "unsloth/Qwen3.6-35B-A3B-GGUF",
        "filename": "Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf",
        "mmproj_filename": "mmproj-F16.gguf",
        "size_gb": 22.1,
        "quantization": "UD-Q4_K_XL",
        "is_moe": True,
        "expert_count": 128,
        "expert_used_count": 8,
        "block_count": 40,
        "context_length": 262144,
        "tags": ["對話", "程式設計", "看圖", "推理"],
        "description": "旗艦級 35B MoE 多模態模型，每次僅啟用 3B 參數，搭配自動分層即可在 8GB 顯卡流暢運行。",
    },
    {
        "id": "Qwen/Qwen3-8B-GGUF",
        "name": "Qwen3 8B",
        "repo": "Qwen/Qwen3-8B-GGUF",
        "filename": "Qwen3-8B-Q4_K_M.gguf",
        "size_gb": 5.03,
        "quantization": "Q4_K_M",
        "is_moe": False,
        "block_count": 36,
        "context_length": 40960,
        "tags": ["對話", "程式設計", "推理"],
        "description": "輕量全能主力模型，支援思考模式切換，8GB 顯存可全層載入極速生成。",
    },
    {
        "id": "unsloth/gemma-3-12b-it-GGUF",
        "name": "Gemma 3 12B Instruct",
        "repo": "unsloth/gemma-3-12b-it-GGUF",
        "filename": "gemma-3-12b-it-Q4_K_M.gguf",
        "mmproj_filename": "mmproj-F16.gguf",
        "size_gb": 7.3,
        "quantization": "Q4_K_M",
        "is_moe": False,
        "block_count": 48,
        "context_length": 131072,
        "tags": ["對話", "看圖"],
        "description": "Google 開源多模態模型，支援 128K 長上下文與視覺理解，中英文寫作自然。",
    },
    {
        "id": "unsloth/Qwen2.5-Coder-7B-Instruct-GGUF",
        "name": "Qwen2.5 Coder 7B",
        "repo": "unsloth/Qwen2.5-Coder-7B-Instruct-GGUF",
        "filename": "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf",
        "size_gb": 4.68,
        "quantization": "Q4_K_M",
        "is_moe": False,
        "block_count": 28,
        "context_length": 32768,
        "tags": ["程式設計", "對話"],
        "description": "專為寫程式、除錯與程式碼重構優化，速度快且極省顯存。",
    },
    {
        "id": "unsloth/DeepSeek-R1-Distill-Qwen-7B-GGUF",
        "name": "DeepSeek-R1 Distill Qwen 7B",
        "repo": "unsloth/DeepSeek-R1-Distill-Qwen-7B-GGUF",
        "filename": "DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
        "size_gb": 4.68,
        "quantization": "Q4_K_M",
        "is_moe": False,
        "block_count": 28,
        "context_length": 131072,
        "tags": ["推理", "程式設計", "對話"],
        "description": "專攻數學邏輯與深度思考鏈推演，適合複雜問答與演算法分析。",
    },
    {
        "id": "unsloth/Qwen3-4B-Instruct-2507-GGUF",
        "name": "Qwen3 4B Instruct",
        "repo": "unsloth/Qwen3-4B-Instruct-2507-GGUF",
        "filename": "Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
        "size_gb": 2.5,
        "quantization": "Q4_K_M",
        "is_moe": False,
        "block_count": 36,
        "context_length": 40960,
        "tags": ["對話", "程式設計"],
        "description": "超輕量 4B 模型，即使是低顯存筆電或純 CPU 也能輕鬆飛快運行。",
    },
]


def _make_model_id(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:16]


def _classify_path(path: Path, gguf_meta: Optional[Dict[str, Any]] = None) -> tuple[str, List[str]]:
    low_full = str(path).lower().replace("\\", "/")
    low_name = path.name.lower()

    if "/lipsync/" in low_full or "infinitetalk" in low_name or "wav2vec" in low_full:
        if low_name.endswith((".safetensors", ".pth", ".th")) and ("infinitetalk" in low_name or "wan2_1" in low_name or "lightx2v" in low_name):
            return "lipsync", ["對嘴型", "影片"]
        return "component", ["組件"]

    if "/loras/" in low_full:
        return "component", ["LoRA"]

    if "/image/common/" in low_full:
        if "vae" in low_name or low_name == "ae.safetensors":
            return "component", ["VAE"]
        if "mmproj" in low_name:
            return "component", ["視覺投影"]
        if "umt5" in low_name or "encoder" in low_name:
            return "component", ["文字編碼器"]
        # Some models inside image/common are actually standalone Qwen3/Qwen3VL GGUFs that can also run as LLMs!
        if low_name.endswith(".gguf") and ("qwen" in low_name or "llama" in low_name or "gemma" in low_name):
            tags = ["對話", "共用編碼器"]
            if "vl" in low_name:
                tags.append("看圖")
            return "llm", tags
        return "component", ["組件"]

    if "/image/" in low_full:
        if "wan2" in low_full or ("minimax-h3/" in low_full) or ("minimax-h3-ref" in low_full):
            return "video", ["影片生成"]
        if "z-image" in low_full or "qwen-image" in low_full or "minimax-h3-image" in low_full or "flux" in low_full:
            return "image", ["畫圖"]

    if low_name.endswith(".gguf"):
        if gguf_meta and gguf_meta.get("is_mmproj"):
            return "component", ["視覺投影"]
        tags = ["對話"]
        if any(k in low_name for k in ("coder", "code", "qwen3", "qwen2.5", "deepseek")):
            tags.append("程式設計")
        if any(k in low_name for k in ("r1", "thinking", "reason", "qwen3")):
            tags.append("推理")
        if any(k in low_name for k in ("vl", "vision")):
            tags.append("看圖")
        return "llm", tags

    return "component", ["檔案"]


def scan_local_models() -> List[Dict[str, Any]]:
    """Scan all configured model directories and return structured inventory."""
    model_dirs = config_manager.config.model_dirs
    hw = get_hardware_info()
    models: List[Dict[str, Any]] = []
    seen_paths = set()

    # Track split shards so we only list part 00001 with combined total size
    split_groups: Dict[str, List[Path]] = {}
    all_files: List[Path] = []

    for root_str in model_dirs:
        root = Path(root_str)
        if not root.exists() or not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip python virtualenvs / git / cache dirs
            dirnames[:] = [
                d for d in dirnames
                if d.lower() not in ("env", ".venv", "venv", ".git", "__pycache__", "node_modules")
            ]
            for fn in filenames:
                low = fn.lower()
                if not low.endswith((".gguf", ".safetensors")):
                    continue
                p = Path(dirpath) / fn
                resolved = str(p.resolve())
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                m = SPLIT_GGUF_RE.match(fn)
                if m:
                    group_key = str(Path(dirpath) / m.group(1))
                    split_groups.setdefault(group_key, []).append(p)
                else:
                    all_files.append(p)

    # Add first shard of split GGUFs
    shard_totals: Dict[str, int] = {}
    for _, shard_list in split_groups.items():
        shard_list.sort()
        first = shard_list[0]
        all_files.append(first)
        shard_totals[str(first.resolve())] = sum(s.stat().st_size for s in shard_list if s.exists())

    # Index mmproj files by parent directory for automatic vision pairing
    mmproj_by_dir: Dict[str, List[Path]] = {}
    for p in all_files:
        if p.name.lower().endswith(".gguf") and "mmproj" in p.name.lower():
            mmproj_by_dir.setdefault(str(p.parent.resolve()), []).append(p)

    for p in sorted(all_files, key=lambda x: x.name.lower()):
        try:
            size_bytes = shard_totals.get(str(p.resolve()), p.stat().st_size)
        except OSError:
            continue
        size_gb = round(size_bytes / (1024**3), 2)
        is_gguf = p.suffix.lower() == ".gguf"
        gguf_meta = parse_gguf_metadata(p) if is_gguf else {}
        category, tags = _classify_path(p, gguf_meta)

        # Pair mmproj vision projector in same folder (strict match inside shared/common dirs)
        mmproj_path = ""
        mmproj_size_gb = 0.0
        if category == "llm" and is_gguf:
            sibling_mmprojs = mmproj_by_dir.get(str(p.parent.resolve()), [])
            chosen_mm: Optional[Path] = None
            in_shared_dir = p.parent.name.lower() in ("common", "models", "imported")
            if len(sibling_mmprojs) == 1 and not in_shared_dir:
                chosen_mm = sibling_mmprojs[0]
            elif sibling_mmprojs:
                norm_model = re.sub(r"[^a-z0-9]", "", p.stem.lower())
                for cand in sibling_mmprojs:
                    # Strip mmproj prefix and quant suffix from projector filename
                    mm_core = re.sub(r"^mmproj[-_]*", "", cand.stem.lower())
                    mm_core = re.sub(r"[-_]*(f16|f32|bf16|q8_0|q4_0)$", "", mm_core)
                    norm_mm = re.sub(r"[^a-z0-9]", "", mm_core)
                    if norm_mm and norm_mm in norm_model:
                        chosen_mm = cand
                        break
            if chosen_mm and chosen_mm.exists():
                mmproj_path = str(chosen_mm.resolve())
                mmproj_size_gb = round(chosen_mm.stat().st_size / (1024**3), 2)
                if "看圖" not in tags:
                    tags.append("看圖")

        display_name = gguf_meta.get("model_name") or p.stem
        if display_name == p.stem and p.parent.name and "__" in p.parent.name:
            display_name = p.parent.name.replace("__", " / ")

        entry: Dict[str, Any] = {
            "id": _make_model_id(p),
            "name": display_name,
            "filename": p.name,
            "path": str(p.resolve()),
            "folder": p.parent.name,
            "format": p.suffix.lstrip(".").upper(),
            "category": category,
            "tags": tags,
            "size_bytes": size_bytes,
            "size_gb": size_gb,
            "quantization": gguf_meta.get("quantization") or infer_quant_from_name(p.name),
            "architecture": gguf_meta.get("architecture", ""),
            "block_count": gguf_meta.get("block_count", 0),
            "context_length": gguf_meta.get("context_length", 0),
            "embedding_length": gguf_meta.get("embedding_length", 0),
            "expert_count": gguf_meta.get("expert_count", 0),
            "expert_used_count": gguf_meta.get("expert_used_count", 0),
            "head_count": gguf_meta.get("head_count", 0),
            "head_count_kv": gguf_meta.get("head_count_kv", 0),
            "is_moe": bool(gguf_meta.get("expert_count", 0) > 1),
            "mmproj_path": mmproj_path,
            "mmproj_size_gb": mmproj_size_gb,
            "has_vision": bool(mmproj_path),
            "modified_at": p.stat().st_mtime,
        }

        if category == "llm":
            entry["tiering"] = plan_auto_tiering(
                entry,
                hw,
                context_setting=config_manager.config.default_context,
                kv_cache_q8=config_manager.config.default_kv_cache_q8,
                flash_attn=config_manager.config.default_flash_attn,
                reserve_ram_gb=config_manager.config.reserve_ram_gb,
            )

        models.append(entry)

    # Sort LLMs first (non-common before common), then image, video, lipsync, component
    order = {"llm": 0, "image": 1, "video": 2, "lipsync": 3, "component": 4}
    models.sort(
        key=lambda m: (
            order.get(m["category"], 9),
            1 if "共用編碼器" in m["tags"] else 0,
            -m["size_gb"],
        )
    )
    return models


def get_recommended_models() -> List[Dict[str, Any]]:
    hw = get_hardware_info()
    installed = scan_local_models()
    installed_names = {m["filename"].lower() for m in installed}
    installed_folders = {m["folder"].lower() for m in installed}

    results: List[Dict[str, Any]] = []
    for item in RECOMMENDED_CATALOG:
        pseudo_model = {
            "size_gb": item["size_gb"],
            "mmproj_size_gb": 0.9 if item.get("mmproj_filename") else 0.0,
            "block_count": item.get("block_count", 32),
            "context_length": item.get("context_length", 32768),
            "expert_count": item.get("expert_count", 0),
            "expert_used_count": item.get("expert_used_count", 0),
        }
        tiering = plan_auto_tiering(
            pseudo_model,
            hw,
            reserve_ram_gb=config_manager.config.reserve_ram_gb,
        )
        repo_slug = item["repo"].replace("/", "__").lower()
        is_installed = (
            item["filename"].lower() in installed_names
            or repo_slug in installed_folders
        )
        results.append(
            {
                **item,
                "installed": is_installed,
                "tiering": tiering,
                "fits_hardware": tiering["compatibility"] in ("optimal", "good", "playable"),
            }
        )
    return results


async def search_huggingface_gguf(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    base = config_manager.config.hf_endpoint.rstrip("/")
    headers = {}
    if config_manager.config.hf_token:
        headers["Authorization"] = f"Bearer {config_manager.config.hf_token}"

    params = {
        "search": query.strip() or "gguf",
        "filter": "gguf",
        "sort": "downloads",
        "direction": "-1",
        "limit": str(min(max(limit, 1), 40)),
    }
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(f"{base}/api/models", params=params, headers=headers)
        resp.raise_for_status()
        items = resp.json()

    results: List[Dict[str, Any]] = []
    for m in items:
        repo_id = m.get("id") or m.get("modelId")
        if not repo_id:
            continue
        results.append(
            {
                "repo": repo_id,
                "downloads": m.get("downloads", 0),
                "likes": m.get("likes", 0),
                "last_modified": m.get("lastModified", ""),
                "tags": m.get("tags", [])[:8],
            }
        )
    return results


async def list_huggingface_repo_files(repo: str) -> List[Dict[str, Any]]:
    base = config_manager.config.hf_endpoint.rstrip("/")
    headers = {}
    if config_manager.config.hf_token:
        headers["Authorization"] = f"Bearer {config_manager.config.hf_token}"

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(f"{base}/api/models/{repo}/tree/main", headers=headers)
        resp.raise_for_status()
        items = resp.json()

    files: List[Dict[str, Any]] = []
    for item in items:
        path = item.get("path", "")
        if item.get("type") != "file" or not path.lower().endswith(".gguf"):
            continue
        size = int(item.get("size") or (item.get("lfs") or {}).get("size") or 0)
        files.append(
            {
                "filename": path,
                "size_bytes": size,
                "size_gb": round(size / (1024**3), 2),
                "quantization": infer_quant_from_name(path),
                "is_mmproj": "mmproj" in path.lower(),
            }
        )
    files.sort(key=lambda x: (x["is_mmproj"], x["size_bytes"]))
    return files


class DownloadTask:
    def __init__(self, task_id: str, repo: str, filename: str, dest_path: Path) -> None:
        self.task_id = task_id
        self.repo = repo
        self.filename = filename
        self.dest_path = dest_path
        self.status = "queued"  # queued | downloading | completed | paused | cancelled | error
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.speed_mb_s = 0.0
        self.eta_seconds = 0
        self.error = ""
        self._cancel_event = asyncio.Event()
        self._asyncio_task: Optional[asyncio.Task] = None

    def to_dict(self) -> Dict[str, Any]:
        pct = round((self.downloaded_bytes / self.total_bytes) * 100.0, 1) if self.total_bytes > 0 else 0.0
        return {
            "task_id": self.task_id,
            "repo": self.repo,
            "filename": self.filename,
            "dest_path": str(self.dest_path),
            "status": self.status,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "percent": pct,
            "speed_mb_s": round(self.speed_mb_s, 2),
            "eta_seconds": self.eta_seconds,
            "error": self.error,
        }


class DownloadManager:
    def __init__(self) -> None:
        self.tasks: Dict[str, DownloadTask] = {}

    def list_tasks(self) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self.tasks.values()]

    def start_hf_download(self, repo: str, filename: str) -> Dict[str, Any]:
        task_id = hashlib.sha1(f"{repo}/{filename}".encode("utf-8")).hexdigest()[:12]
        existing = self.tasks.get(task_id)
        if existing and existing.status == "downloading":
            return existing.to_dict()

        base_dir = Path(config_manager.config.primary_download_dir)
        repo_dir = base_dir / repo.replace("/", "__")
        repo_dir.mkdir(parents=True, exist_ok=True)
        dest_path = repo_dir / Path(filename).name

        task = DownloadTask(task_id, repo, filename, dest_path)
        self.tasks[task_id] = task
        task._asyncio_task = asyncio.create_task(self._run_download(task))
        return task.to_dict()

    def cancel_task(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if not task:
            return False
        task._cancel_event.set()
        task.status = "cancelled"
        return True

    async def _run_download(self, task: DownloadTask) -> None:
        base = config_manager.config.hf_endpoint.rstrip("/")
        url = f"{base}/{task.repo}/resolve/main/{task.filename}"
        part_path = task.dest_path.with_suffix(task.dest_path.suffix + ".part")
        existing_size = part_path.stat().st_size if part_path.exists() else 0

        headers: Dict[str, str] = {}
        if config_manager.config.hf_token:
            headers["Authorization"] = f"Bearer {config_manager.config.hf_token}"
        if existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"

        task.status = "downloading"
        task.downloaded_bytes = existing_size
        start_time = time.monotonic()
        session_bytes = 0

        try:
            async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
                async with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code == 416:
                        # Already complete
                        if part_path.exists():
                            part_path.replace(task.dest_path)
                        task.status = "completed"
                        return
                    resp.raise_for_status()
                    content_len = int(resp.headers.get("content-length", "0"))
                    if resp.status_code == 206:
                        task.total_bytes = existing_size + content_len
                        mode = "ab"
                    else:
                        task.total_bytes = content_len
                        task.downloaded_bytes = 0
                        mode = "wb"

                    with part_path.open(mode) as f:
                        async for chunk in resp.aiter_bytes(chunk_size=1024 * 512):
                            if task._cancel_event.is_set():
                                task.status = "cancelled"
                                return
                            f.write(chunk)
                            n = len(chunk)
                            task.downloaded_bytes += n
                            session_bytes += n
                            elapsed = max(time.monotonic() - start_time, 0.05)
                            bps = session_bytes / elapsed
                            task.speed_mb_s = bps / (1024 * 1024)
                            if task.total_bytes > 0 and bps > 0:
                                task.eta_seconds = int((task.total_bytes - task.downloaded_bytes) / bps)

            part_path.replace(task.dest_path)
            task.status = "completed"
            task.eta_seconds = 0
        except Exception as exc:
            task.status = "error"
            task.error = str(exc)


def import_local_gguf(source_path_str: str, copy_file: bool = False) -> Dict[str, Any]:
    src = Path(source_path_str).expanduser().resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"找不到檔案：{source_path_str}")
    if src.suffix.lower() != ".gguf":
        raise ValueError("僅支援匯入 .gguf 模型檔案")

    if copy_file:
        dest_dir = Path(config_manager.config.primary_download_dir) / "imported"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        return {"imported_path": str(dest), "mode": "copied"}

    parent_dir = str(src.parent)
    dirs = list(config_manager.config.model_dirs)
    if parent_dir not in dirs:
        dirs.append(parent_dir)
        config_manager.update({"model_dirs": dirs})
    return {"imported_path": str(src), "mode": "linked_dir"}


download_manager = DownloadManager()
