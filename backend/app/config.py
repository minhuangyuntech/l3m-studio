from __future__ import annotations

import json
import os
import platform
import shutil
from pathlib import Path
from typing import Any, List, Optional
from pydantic import BaseModel, Field


def _resolve_app_home() -> Path:
    env_home = os.environ.get("LOCMODEL_HOME")
    project_data = Path(__file__).resolve().parent.parent.parent / "data"
    candidates = [
        Path(env_home) if env_home else project_data,
        Path.home() / ".locmodel-studio",
    ]
    for cand in candidates:
        try:
            cand.mkdir(parents=True, exist_ok=True)
            test_file = cand / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            return cand
        except OSError:
            continue
    return project_data


APP_HOME = _resolve_app_home()
CONFIG_PATH = APP_HOME / "config.json"
ENGINES_DIR = APP_HOME / "engines"
CHATS_DIR = APP_HOME / "chats"
DEFAULT_MODELS_DIR = APP_HOME / "models"


def _discover_default_model_dirs() -> List[str]:
    shared_d = Path("D:/AI-Models")
    if shared_d.exists() and shared_d.is_dir():
        return [str(shared_d.resolve())]

    dirs: List[str] = []
    for p in (Path.home() / "AI-Models", DEFAULT_MODELS_DIR):
        if p.exists() and p.is_dir():
            resolved = str(p.resolve())
            if resolved not in dirs:
                dirs.append(resolved)
    if not dirs:
        DEFAULT_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        dirs.append(str(DEFAULT_MODELS_DIR.resolve()))
    return dirs


def _discover_llama_server() -> str:
    exe = "llama-server.exe" if platform.system() == "Windows" else "llama-server"
    in_path = shutil.which("llama-server")
    if in_path:
        return str(Path(in_path).resolve())

    # Check managed engines folder
    if ENGINES_DIR.exists():
        for match in ENGINES_DIR.rglob(exe):
            if match.is_file():
                return str(match.resolve())

    # Check common local build locations
    common_candidates = [
        Path("D:/projects/llama.cpp/install/bin") / exe,
        Path("D:/projects/llama.cpp/build/bin") / exe,
        Path.home() / "llama.cpp" / "build" / "bin" / exe,
        Path("/opt/homebrew/bin") / exe,
        Path("/usr/local/bin") / exe,
    ]
    for cand in common_candidates:
        if cand.exists() and cand.is_file():
            return str(cand.resolve())
    return ""


class AppConfig(BaseModel):
    model_dirs: List[str] = Field(default_factory=_discover_default_model_dirs)
    primary_download_dir: str = ""
    llama_server_path: str = Field(default_factory=_discover_llama_server)
    api_host: str = "127.0.0.1"
    api_port: int = 11435
    lan_access: bool = False
    hf_endpoint: str = "https://huggingface.co"
    hf_token: str = ""
    reserve_ram_gb: float = 4.0
    auto_recovery: bool = True
    language: str = "zh-TW"
    default_context: str = "auto"  # auto | 8192 | 16384 | 32768 | 65536
    default_flash_attn: bool = True
    default_kv_cache_q8: bool = True
    default_thinking: bool = True
    default_no_mmap: bool = False
    external_api_base: str = ""
    external_api_key: str = ""
    external_api_model: str = ""
    sd_cli_path: str = ""
    comfyui_url: str = "http://127.0.0.1:8188"
    custom_image_api: str = ""
    theme: str = "dark"


class ConfigManager:
    def __init__(self) -> None:
        APP_HOME.mkdir(parents=True, exist_ok=True)
        ENGINES_DIR.mkdir(parents=True, exist_ok=True)
        CHATS_DIR.mkdir(parents=True, exist_ok=True)
        self._config = self._load()

    def _load(self) -> AppConfig:
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                cfg = AppConfig(**raw)
            except Exception:
                cfg = AppConfig()
        else:
            cfg = AppConfig()

        # Ensure discovered defaults are present and prioritize D:\AI-Models when available
        if not cfg.model_dirs:
            cfg.model_dirs = _discover_default_model_dirs()
        elif Path("D:/AI-Models").exists():
            d_ai = str(Path("D:/AI-Models").resolve())
            # Remove any stale C:\...\.gemini\antigravity\scratch\locmodel-studio paths
            cfg.model_dirs = [
                x for x in cfg.model_dirs
                if ".gemini\\antigravity\\scratch\\locmodel-studio" not in x.lower()
            ]
            if all(Path(x).resolve() != Path(d_ai) for x in cfg.model_dirs if Path(x).exists()):
                cfg.model_dirs.insert(0, d_ai)

        if not cfg.primary_download_dir or cfg.primary_download_dir not in cfg.model_dirs:
            cfg.primary_download_dir = cfg.model_dirs[0]

        if not cfg.llama_server_path or not Path(cfg.llama_server_path).exists():
            discovered = _discover_llama_server()
            if discovered:
                cfg.llama_server_path = discovered

        self._save(cfg)
        return cfg

    def _save(self, cfg: AppConfig) -> None:
        CONFIG_PATH.write_text(
            cfg.model_dump_json(indent=2),
            encoding="utf-8",
        )

    @property
    def config(self) -> AppConfig:
        return self._config

    def update(self, patch: dict[str, Any]) -> AppConfig:
        data = self._config.model_dump()
        for k, v in patch.items():
            if k in data and v is not None:
                data[k] = v
        # Normalize model_dirs
        cleaned_dirs: List[str] = []
        for d in data.get("model_dirs", []):
            d_str = str(d).strip()
            if d_str and d_str not in cleaned_dirs:
                cleaned_dirs.append(d_str)
        data["model_dirs"] = cleaned_dirs or _discover_default_model_dirs()
        if not data.get("primary_download_dir") or data["primary_download_dir"] not in data["model_dirs"]:
            data["primary_download_dir"] = data["model_dirs"][0]

        self._config = AppConfig(**data)
        self._save(self._config)
        return self._config


config_manager = ConfigManager()
