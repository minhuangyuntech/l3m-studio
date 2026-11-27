from __future__ import annotations

import asyncio
import collections
import os
import platform
import shutil
import socket
import stat
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

import httpx
import psutil

from .config import ENGINES_DIR, config_manager
from .hardware import get_hardware_info
from .models import scan_local_models
from .tiering import plan_auto_tiering


def _get_local_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _detect_engine_backend(binary_path: Path) -> str:
    if not binary_path.exists():
        return "unknown"
    parent = binary_path.parent
    names = {p.name.lower() for p in parent.iterdir()} if parent.exists() else set()
    if any("cuda" in n for n in names):
        return "cuda"
    if any("vulkan" in n for n in names):
        return "vulkan"
    if platform.system() == "Darwin":
        return "metal"
    return "cpu"


def _probe_engine_version(binary_path: Path) -> str:
    if not binary_path.exists():
        return ""
    try:
        proc = subprocess.run(
            [str(binary_path), "--version"],
            capture_output=True,
            text=True,
            timeout=5.0,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        out = (proc.stdout + "\n" + proc.stderr).strip()
        for line in out.splitlines():
            if "version:" in line.lower() or "build" in line.lower():
                return line.strip()
        return out.splitlines()[0].strip() if out else ""
    except Exception:
        return ""


class EngineManager:
    def __init__(self) -> None:
        self.process: Optional[asyncio.subprocess.Process] = None
        self.status: str = "stopped"  # stopped | starting | running | error
        self.active_model: Optional[Dict[str, Any]] = None
        self.active_config: Dict[str, Any] = {}
        self.active_tiering: Optional[Dict[str, Any]] = None
        self.started_at: Optional[float] = None
        self.last_error: str = ""
        self.logs: Deque[str] = collections.deque(maxlen=600)
        self._log_subscribers: List[asyncio.Queue[str]] = []
        self._monitor_task: Optional[asyncio.Task] = None
        self._intentional_stop: bool = False
        self._auto_restarts: int = 0

        # Engine installer state
        self.install_state: Dict[str, Any] = {
            "status": "idle",  # idle | fetching | downloading | extracting | completed | cancelled | error
            "asset_name": "",
            "release_tag": "",
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "percent": 0.0,
            "speed_mb_s": 0.0,
            "eta_seconds": 0,
            "error": "",
        }
        self._install_cancel = asyncio.Event()
        self._install_task: Optional[asyncio.Task] = None

    def _append_log(self, line: str) -> None:
        ts = time.strftime("%H:%M:%S")
        formatted = f"[{ts}] {line}"
        self.logs.append(formatted)
        for q in list(self._log_subscribers):
            try:
                q.put_nowait(formatted)
            except asyncio.QueueFull:
                pass

    def subscribe_logs(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=200)
        self._log_subscribers.append(q)
        return q

    def unsubscribe_logs(self, q: asyncio.Queue[str]) -> None:
        if q in self._log_subscribers:
            self._log_subscribers.remove(q)

    def get_engine_info(self) -> Dict[str, Any]:
        bin_str = config_manager.config.llama_server_path
        bin_path = Path(bin_str) if bin_str else Path("")
        installed = bool(bin_str and bin_path.exists() and bin_path.is_file())
        hw = get_hardware_info()
        return {
            "installed": installed,
            "binary_path": str(bin_path) if installed else "",
            "backend": _detect_engine_backend(bin_path) if installed else hw["recommended_backend"],
            "recommended_backend": hw["recommended_backend"],
            "version": _probe_engine_version(bin_path) if installed else "",
            "install_state": self.install_state,
        }

    def get_status(self) -> Dict[str, Any]:
        cfg = config_manager.config
        lan_ip = _get_local_lan_ip()
        port = self.active_config.get("port", cfg.api_port)
        lan = self.active_config.get("lan_access", cfg.lan_access)
        return {
            "status": self.status,
            "pid": self.process.pid if (self.process and self.process.returncode is None) else None,
            "started_at": self.started_at,
            "uptime_seconds": int(time.time() - self.started_at) if (self.started_at and self.status == "running") else 0,
            "active_model": self.active_model,
            "active_config": self.active_config,
            "active_tiering": self.active_tiering,
            "last_error": self.last_error,
            "local_endpoint": f"http://127.0.0.1:{port}/v1",
            "lan_endpoint": f"http://{lan_ip}:{port}/v1" if lan else "",
            "lan_ip": lan_ip,
            "logs": list(self.logs)[-120:],
        }

    async def start_model(
        self,
        model_id: str,
        context_setting: str = "auto",
        thinking: bool = True,
        lan_access: bool = False,
        flash_attn: bool = True,
        kv_cache_q8: bool = True,
        no_mmap: bool = False,
        auto_recovery: bool = True,
        port: Optional[int] = None,
        custom_ngl: Optional[int] = None,
        extra_cli_args: str = "",
    ) -> Dict[str, Any]:
        bin_path = Path(config_manager.config.llama_server_path)
        if not bin_path.exists() or not bin_path.is_file():
            raise RuntimeError("尚未找到 llama-server 執行檔，請先一鍵安裝推理引擎或在設定中指定路徑。")

        models = scan_local_models()
        target = next((m for m in models if m["id"] == model_id), None)
        if not target:
            raise FileNotFoundError("找不到指定的本地模型，請重新掃描模型庫。")

        await self.stop_model()

        hw = get_hardware_info()
        tiering = plan_auto_tiering(
            target,
            hw,
            context_setting=context_setting,
            kv_cache_q8=kv_cache_q8,
            flash_attn=flash_attn,
            reserve_ram_gb=config_manager.config.reserve_ram_gb,
            no_mmap=no_mmap,
        )

        chosen_port = port or config_manager.config.api_port
        host = "0.0.0.0" if lan_access else "127.0.0.1"
        ngl = custom_ngl if custom_ngl is not None else tiering["gpu_layers"]

        cmd: List[str] = [
            str(bin_path),
            "-m",
            target["path"],
            "--host",
            host,
            "--port",
            str(chosen_port),
            "-c",
            str(tiering["context_length"]),
            "-ngl",
            str(ngl),
            "--alias",
            target["name"],
            "-fa",
            "on" if flash_attn else "off",
            "--reasoning",
            "on" if thinking else "off",
        ]

        if kv_cache_q8:
            cmd.extend(["-ctk", "q8_0", "-ctv", "q8_0"])

        if no_mmap:
            cmd.append("--no-mmap")

        if target.get("mmproj_path") and Path(target["mmproj_path"]).exists():
            cmd.extend(["--mmproj", target["mmproj_path"]])

        # Apply smart MoE / hybrid tensor overrides from Auto-Tiering
        if custom_ngl is None and tiering["recommended_args"]["extra_args"]:
            cmd.extend(tiering["recommended_args"]["extra_args"])

        if extra_cli_args.strip():
            import shlex

            cmd.extend(shlex.split(extra_cli_args.strip()))

        self.logs.clear()
        self.last_error = ""
        self.status = "starting"
        self.active_model = target
        self.active_tiering = tiering
        self._intentional_stop = False
        self._auto_restarts = 0
        self.active_config = {
            "model_id": model_id,
            "context_setting": context_setting,
            "context_length": tiering["context_length"],
            "thinking": thinking,
            "lan_access": lan_access,
            "flash_attn": flash_attn,
            "kv_cache_q8": kv_cache_q8,
            "no_mmap": no_mmap,
            "auto_recovery": auto_recovery,
            "port": chosen_port,
            "host": host,
            "custom_ngl": custom_ngl,
            "extra_cli_args": extra_cli_args,
            "command": " ".join(cmd),
        }

        self._append_log(f"啟動推理引擎：{target['name']} ({target['quantization']})")
        self._append_log(f"自動分層策略：{tiering['summary_zh']}")
        self._append_log(f"執行指令：{' '.join(cmd)}")

        await self._spawn_process(cmd, chosen_port)
        return self.get_status()

    async def _spawn_process(self, cmd: List[str], port: int) -> None:
        kwargs: Dict[str, Any] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
            "cwd": str(Path(cmd[0]).parent),
        }
        if platform.system() == "Windows":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        self.process = await asyncio.create_subprocess_exec(*cmd, **kwargs)
        self.started_at = time.time()
        self._monitor_task = asyncio.create_task(self._watch_process(cmd, port))

    async def _watch_process(self, cmd: List[str], port: int) -> None:
        assert self.process is not None
        health_task = asyncio.create_task(self._poll_health(port))

        try:
            if self.process.stdout:
                while True:
                    raw = await self.process.stdout.readline()
                    if not raw:
                        break
                    line = raw.decode("utf-8", errors="replace").rstrip()
                    if line:
                        self._append_log(line)
            rc = await self.process.wait()
        finally:
            health_task.cancel()

        if self._intentional_stop:
            self.status = "stopped"
            self._append_log("推理引擎已正常停止。")
            return

        self._append_log(f"推理引擎非預期退出（exit code={rc}）。")
        if self.active_config.get("auto_recovery") and self._auto_restarts < 2:
            self._auto_restarts += 1
            self.status = "starting"
            self._append_log(f"啟動自動回收重啟（第 {self._auto_restarts}/2 次）...")
            await asyncio.sleep(2.0)
            if not self._intentional_stop:
                await self._spawn_process(cmd, port)
        else:
            self.status = "error"
            self.last_error = f"llama-server 異常終止（代碼 {rc}），請檢視執行日誌。"

    async def _poll_health(self, port: int) -> None:
        url = f"http://127.0.0.1:{port}/health"
        async with httpx.AsyncClient(timeout=2.0) as client:
            for _ in range(300):  # Wait up to 5 minutes for huge models to load
                if self._intentional_stop or not self.process or self.process.returncode is not None:
                    return
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") == "ok":
                            self.status = "running"
                            self._append_log(f"模型載入完成！OpenAI 相容 API 已就緒：http://127.0.0.1:{port}/v1")
                            return
                except Exception:
                    pass
                await asyncio.sleep(1.0)

    def find_external_llama_servers(self) -> List[Dict[str, Any]]:
        found: List[Dict[str, Any]] = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if "llama-server" in name:
                    cmd = proc.info.get("cmdline") or []
                    alias = ""
                    for i, tok in enumerate(cmd):
                        if tok in ("--alias", "-m") and i + 1 < len(cmd):
                            alias = Path(cmd[i + 1]).name
                            if tok == "--alias":
                                break
                    found.append({"pid": proc.info["pid"], "name": alias or "llama-server"})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return found

    async def stop_all_llama_servers(self) -> int:
        await self.stop_model()
        killed = 0
        for item in self.find_external_llama_servers():
            try:
                p = psutil.Process(item["pid"])
                p.terminate()
                try:
                    p.wait(timeout=3)
                except psutil.TimeoutExpired:
                    p.kill()
                killed += 1
            except Exception:
                pass
        return killed

    async def stop_model(self) -> Dict[str, Any]:
        self._intentional_stop = True
        if self.process and self.process.returncode is None:
            self._append_log("正在停止推理引擎...")
            try:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
            except Exception:
                pass
        self.process = None
        self.status = "stopped"
        self.started_at = None
        return self.get_status()

    # ---------- One-click llama.cpp installer & offline archive import ----------

    def start_engine_install(self, backend: Optional[str] = None) -> Dict[str, Any]:
        if self.install_state["status"] in ("fetching", "downloading", "extracting"):
            return self.install_state
        self._install_cancel.clear()
        self._install_task = asyncio.create_task(self._download_official_engine(backend))
        return self.install_state

    def cancel_engine_install(self) -> Dict[str, Any]:
        self._install_cancel.set()
        self.install_state["status"] = "cancelled"
        return self.install_state

    async def _download_official_engine(self, preferred_backend: Optional[str] = None) -> None:
        hw = get_hardware_info()
        backend = preferred_backend or hw["recommended_backend"]
        sys_name = platform.system().lower()
        arch = platform.machine().lower()

        self.install_state.update(
            {
                "status": "fetching",
                "asset_name": "",
                "release_tag": "",
                "downloaded_bytes": 0,
                "total_bytes": 0,
                "percent": 0.0,
                "speed_mb_s": 0.0,
                "eta_seconds": 0,
                "error": "",
            }
        )

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                rel_resp = await client.get(
                    "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest",
                    headers={"Accept": "application/vnd.github+json"},
                )
                rel_resp.raise_for_status()
                release = rel_resp.json()
                tag = release.get("tag_name", "latest")
                assets = release.get("assets", [])

                chosen = self._pick_release_asset(assets, sys_name, arch, backend)
                if not chosen:
                    raise RuntimeError(f"找不到適合 {sys_name}/{arch}/{backend} 的官方 llama.cpp 預編譯版本")

                asset_name = chosen["name"]
                download_url = chosen["browser_download_url"]
                self.install_state.update(
                    {
                        "status": "downloading",
                        "release_tag": tag,
                        "asset_name": asset_name,
                    }
                )

                archive_path = ENGINES_DIR / asset_name
                start_t = time.monotonic()
                got = 0
                async with client.stream("GET", download_url) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("content-length", "0"))
                    self.install_state["total_bytes"] = total
                    with archive_path.open("wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=1024 * 512):
                            if self._install_cancel.is_set():
                                self.install_state["status"] = "cancelled"
                                return
                            f.write(chunk)
                            got += len(chunk)
                            elapsed = max(time.monotonic() - start_t, 0.05)
                            bps = got / elapsed
                            self.install_state["downloaded_bytes"] = got
                            self.install_state["speed_mb_s"] = round(bps / (1024 * 1024), 2)
                            if total > 0:
                                self.install_state["percent"] = round((got / total) * 100.0, 1)
                                self.install_state["eta_seconds"] = int((total - got) / max(bps, 1.0))

                self.install_state["status"] = "extracting"
                installed_bin = self.import_engine_archive(archive_path, tag=f"{tag}-{backend}")
                archive_path.unlink(missing_ok=True)
                self.install_state["status"] = "completed"
                self.install_state["percent"] = 100.0
                self._append_log(f"已安裝 llama.cpp ({tag})：{installed_bin}")
        except Exception as exc:
            self.install_state["status"] = "error"
            self.install_state["error"] = str(exc)

    def _pick_release_asset(
        self, assets: List[Dict[str, Any]], sys_name: str, arch: str, backend: str
    ) -> Optional[Dict[str, Any]]:
        candidates = [a for a in assets if a["name"].endswith((".zip", ".tar.gz"))]
        if sys_name == "windows":
            win_assets = [a for a in candidates if "win-" in a["name"].lower() and "x64" in a["name"].lower()]
            if backend == "cuda":
                for pref in ("cuda-12.4", "cuda-12", "cuda"):
                    hit = next((a for a in win_assets if pref in a["name"].lower() and "cudart" not in a["name"].lower()), None)
                    if hit:
                        return hit
            if backend == "vulkan":
                hit = next((a for a in win_assets if "vulkan" in a["name"].lower()), None)
                if hit:
                    return hit
            return next((a for a in win_assets if "cpu" in a["name"].lower()), win_assets[0] if win_assets else None)

        if sys_name == "darwin":
            is_arm = "arm" in arch or "aarch64" in arch
            mac_assets = [a for a in candidates if "macos-" in a["name"].lower()]
            target_arch = "arm64" if is_arm else "x64"
            return next((a for a in mac_assets if target_arch in a["name"].lower()), mac_assets[0] if mac_assets else None)

        # Linux
        lin_assets = [a for a in candidates if "ubuntu" in a["name"].lower() or "linux" in a["name"].lower()]
        if backend == "vulkan":
            hit = next((a for a in lin_assets if "vulkan" in a["name"].lower()), None)
            if hit:
                return hit
        return next((a for a in lin_assets if "x64" in a["name"].lower()), lin_assets[0] if lin_assets else None)

    def import_engine_archive(self, archive_path: Path, tag: str = "imported") -> str:
        target_dir = ENGINES_DIR / f"llama-{tag}-{int(time.time())}"
        target_dir.mkdir(parents=True, exist_ok=True)
        low = archive_path.name.lower()
        if low.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(target_dir)
        elif low.endswith((".tar.gz", ".tgz")):
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(target_dir)
        else:
            raise ValueError("請上傳 .zip 或 .tar.gz 格式的 llama.cpp 壓縮包")

        exe_name = "llama-server.exe" if platform.system() == "Windows" else "llama-server"
        found = next(target_dir.rglob(exe_name), None)
        if not found:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise FileNotFoundError(f"壓縮包內找不到 {exe_name}")

        if platform.system() != "Windows":
            found.chmod(found.stat().st_mode | stat.S_IEXEC)

        config_manager.update({"llama_server_path": str(found.resolve())})
        return str(found.resolve())


engine_manager = EngineManager()
