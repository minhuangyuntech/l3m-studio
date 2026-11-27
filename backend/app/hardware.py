from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from .config import config_manager


def _run_cmd(args: List[str], timeout: float = 4.0) -> Optional[str]:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return None


def _detect_cpu_name() -> str:
    sys_name = platform.system()
    if sys_name == "Windows":
        try:
            import winreg  # type: ignore

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            if name:
                return str(name).strip()
        except Exception:
            pass
    elif sys_name == "Darwin":
        out = _run_cmd(["sysctl", "-n", "machdep.cpu.brand_string"])
        if out:
            return out
    elif sys_name == "Linux":
        try:
            for line in Path("/proc/cpuinfo").read_text(errors="ignore").splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
    return platform.processor() or "Unknown CPU"


def _detect_nvidia_gpus() -> List[Dict[str, Any]]:
    if not shutil.which("nvidia-smi"):
        return []
    out = _run_cmd(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    if not out:
        return []
    gpus: List[Dict[str, Any]] = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue

        def _f(idx: int, default: float = 0.0) -> float:
            try:
                return float(parts[idx])
            except Exception:
                return default

        total_mb = _f(2)
        used_mb = _f(3)
        free_mb = _f(4, max(0.0, total_mb - used_mb))
        gpus.append(
            {
                "index": int(_f(0, 0)),
                "vendor": "NVIDIA",
                "backend": "cuda",
                "name": parts[1],
                "vram_total_gb": round(total_mb / 1024.0, 2),
                "vram_used_gb": round(used_mb / 1024.0, 2),
                "vram_free_gb": round(free_mb / 1024.0, 2),
                "utilization_pct": round(_f(5), 1),
                "temperature_c": round(_f(6), 1),
                "power_w": round(_f(7), 1),
                "driver_version": parts[8] if len(parts) > 8 else "",
                "unified_memory": False,
            }
        )
    return gpus


def _detect_apple_gpu() -> List[Dict[str, Any]]:
    if platform.system() != "Darwin":
        return []
    chip = _run_cmd(["sysctl", "-n", "machdep.cpu.brand_string"]) or "Apple Silicon"
    mem = psutil.virtual_memory()
    # macOS Metal typically exposes ~75% of unified memory to GPU
    total_gb = round((mem.total / (1024**3)) * 0.75, 2)
    used_gb = round((mem.used / (1024**3)) * 0.5, 2)
    return [
        {
            "index": 0,
            "vendor": "Apple",
            "backend": "metal",
            "name": chip,
            "vram_total_gb": total_gb,
            "vram_used_gb": used_gb,
            "vram_free_gb": round(max(0.0, total_gb - used_gb), 2),
            "utilization_pct": 0.0,
            "temperature_c": 0.0,
            "power_w": 0.0,
            "driver_version": f"macOS {platform.mac_ver()[0]}",
            "unified_memory": True,
        }
    ]


def _detect_disks(paths: List[str]) -> List[Dict[str, Any]]:
    seen_roots = set()
    disks: List[Dict[str, Any]] = []
    for raw in paths:
        p = Path(raw)
        target = p if p.exists() else p.parent
        while not target.exists() and target != target.parent:
            target = target.parent
        try:
            usage = psutil.disk_usage(str(target))
            root_key = target.anchor or "/"
            if root_key in seen_roots:
                continue
            seen_roots.add(root_key)
            disks.append(
                {
                    "path": raw,
                    "mount": root_key,
                    "total_gb": round(usage.total / (1024**3), 1),
                    "used_gb": round(usage.used / (1024**3), 1),
                    "free_gb": round(usage.free / (1024**3), 1),
                    "percent": round(usage.percent, 1),
                }
            )
        except Exception:
            continue
    return disks


def get_hardware_info() -> Dict[str, Any]:
    mem = psutil.virtual_memory()
    gpus = _detect_nvidia_gpus()
    if not gpus and platform.system() == "Darwin":
        gpus = _detect_apple_gpu()

    recommended_backend = "cpu"
    if gpus:
        recommended_backend = gpus[0]["backend"]
    elif platform.system() in ("Windows", "Linux"):
        recommended_backend = "vulkan"

    total_vram_gb = round(sum(g["vram_total_gb"] for g in gpus), 2)
    free_vram_gb = round(sum(g["vram_free_gb"] for g in gpus), 2)
    ram_total_gb = round(mem.total / (1024**3), 2)
    ram_available_gb = round(mem.available / (1024**3), 2)
    ram_used_gb = round((mem.total - mem.available) / (1024**3), 2)

    disks = _detect_disks(config_manager.config.model_dirs)

    return {
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "cpu": {
            "name": _detect_cpu_name(),
            "physical_cores": psutil.cpu_count(logical=False) or 1,
            "logical_threads": psutil.cpu_count(logical=True) or 1,
            "usage_pct": round(psutil.cpu_percent(interval=0.1), 1),
        },
        "memory": {
            "total_gb": ram_total_gb,
            "used_gb": ram_used_gb,
            "available_gb": ram_available_gb,
            "percent": round(mem.percent, 1),
        },
        "gpus": gpus,
        "total_vram_gb": total_vram_gb,
        "free_vram_gb": free_vram_gb,
        "recommended_backend": recommended_backend,
        "disks": disks,
        "timestamp": time.time(),
    }


def get_realtime_metrics(engine_pid: Optional[int] = None) -> Dict[str, Any]:
    mem = psutil.virtual_memory()
    gpus = _detect_nvidia_gpus()
    if not gpus and platform.system() == "Darwin":
        gpus = _detect_apple_gpu()

    engine_stats: Optional[Dict[str, Any]] = None
    if engine_pid:
        try:
            proc = psutil.Process(engine_pid)
            with proc.oneshot():
                engine_stats = {
                    "pid": engine_pid,
                    "status": proc.status(),
                    "cpu_pct": round(proc.cpu_percent(interval=None), 1),
                    "rss_gb": round(proc.memory_info().rss / (1024**3), 2),
                    "threads": proc.num_threads(),
                }
        except Exception:
            engine_stats = None

    return {
        "timestamp": time.time(),
        "cpu_pct": round(psutil.cpu_percent(interval=None), 1),
        "ram_total_gb": round(mem.total / (1024**3), 2),
        "ram_used_gb": round((mem.total - mem.available) / (1024**3), 2),
        "ram_available_gb": round(mem.available / (1024**3), 2),
        "ram_percent": round(mem.percent, 1),
        "gpus": gpus,
        "engine_process": engine_stats,
    }
