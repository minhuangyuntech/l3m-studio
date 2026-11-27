from __future__ import annotations

import asyncio
import json
import platform
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .config import APP_HOME, config_manager
from .engine import engine_manager
from .hardware import get_realtime_metrics

SCHEDULES_PATH = APP_HOME / "schedules.json"


class SchedulerManager:
    def __init__(self) -> None:
        self._tasks: List[Dict[str, Any]] = self._load()
        self._loop_task: Optional[asyncio.Task] = None

    def _load(self) -> List[Dict[str, Any]]:
        if not SCHEDULES_PATH.exists():
            return []
        try:
            return json.loads(SCHEDULES_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self) -> None:
        SCHEDULES_PATH.write_text(json.dumps(self._tasks, ensure_ascii=False, indent=2), encoding="utf-8")

    def start_background_loop(self) -> None:
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._tick_loop())

    def stop_background_loop(self) -> None:
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()

    def list_tasks(self) -> List[Dict[str, Any]]:
        return list(self._tasks)

    def create_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        task = {
            "id": uuid.uuid4().hex[:10],
            "name": str(data.get("name", "未命名排程")).strip() or "未命名排程",
            "task_type": data.get("task_type", "llm_prompt"),  # llm_prompt | shell_command | hardware_report
            "schedule_mode": data.get("schedule_mode", "interval"),  # interval | daily
            "interval_minutes": max(1, int(data.get("interval_minutes", 60))),
            "daily_time": str(data.get("daily_time", "09:00")),
            "payload": str(data.get("payload", "")),
            "webhook_url": str(data.get("webhook_url", "")).strip(),
            "enabled": bool(data.get("enabled", True)),
            "last_run_at": 0.0,
            "last_status": "idle",
            "last_output": "",
            "history": [],
            "created_at": time.time(),
        }
        self._tasks.insert(0, task)
        self._save()
        return task

    def update_task(self, task_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        for t in self._tasks:
            if t["id"] == task_id:
                for k in ("name", "task_type", "schedule_mode", "interval_minutes", "daily_time", "payload", "webhook_url", "enabled"):
                    if k in patch:
                        t[k] = patch[k]
                self._save()
                return t
        raise FileNotFoundError("找不到指定的排程任務")

    def delete_task(self, task_id: str) -> bool:
        before = len(self._tasks)
        self._tasks = [t for t in self._tasks if t["id"] != task_id]
        if len(self._tasks) != before:
            self._save()
            return True
        return False

    async def run_now(self, task_id: str) -> Dict[str, Any]:
        task = next((t for t in self._tasks if t["id"] == task_id), None)
        if not task:
            raise FileNotFoundError("找不到指定的排程任務")
        await self._execute_task(task)
        return task

    async def _tick_loop(self) -> None:
        while True:
            try:
                now = time.time()
                now_dt = datetime.now()
                hhmm = now_dt.strftime("%H:%M")
                for task in list(self._tasks):
                    if not task.get("enabled"):
                        continue
                    due = False
                    if task.get("schedule_mode") == "daily":
                        last_day = datetime.fromtimestamp(task.get("last_run_at", 0)).strftime("%Y-%m-%d") if task.get("last_run_at") else ""
                        if hhmm == task.get("daily_time") and last_day != now_dt.strftime("%Y-%m-%d"):
                            due = True
                    else:
                        interval_sec = max(60, int(task.get("interval_minutes", 60)) * 60)
                        if now - float(task.get("last_run_at", 0)) >= interval_sec:
                            due = True
                    if due:
                        asyncio.create_task(self._execute_task(task))
            except Exception:
                pass
            await asyncio.sleep(20.0)

    async def _execute_task(self, task: Dict[str, Any]) -> None:
        task["last_run_at"] = time.time()
        task["last_status"] = "running"
        self._save()
        output = ""
        status = "success"
        try:
            t_type = task.get("task_type")
            if t_type == "hardware_report":
                m = get_realtime_metrics()
                gpu_str = (
                    f"{m['gpus'][0]['name']} VRAM {m['gpus'][0]['vram_used_gb']}/{m['gpus'][0]['vram_total_gb']}GB ({m['gpus'][0]['utilization_pct']}%)"
                    if m["gpus"]
                    else "無 GPU"
                )
                output = f"CPU {m['cpu_pct']}% · RAM {m['ram_used_gb']}/{m['ram_total_gb']}GB · {gpu_str}"
            elif t_type == "shell_command":
                cmd = task.get("payload", "").strip()
                shell_cmd = ["powershell", "-NoProfile", "-Command", cmd] if platform.system() == "Windows" else ["bash", "-lc", cmd]
                kwargs: Dict[str, Any] = {"stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.STDOUT}
                if platform.system() == "Windows":
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                proc = await asyncio.create_subprocess_exec(*shell_cmd, **kwargs)
                raw, _ = await asyncio.wait_for(proc.communicate(), timeout=60.0)
                output = raw.decode("utf-8", errors="replace").strip()[:3000]
                if proc.returncode != 0:
                    status = "error"
            else:
                # llm_prompt
                cfg = config_manager.config
                if engine_manager.status == "running":
                    port = engine_manager.active_config.get("port", cfg.api_port)
                    endpoint = f"http://127.0.0.1:{port}/v1/chat/completions"
                    headers = {"Content-Type": "application/json"}
                    model = (engine_manager.active_model or {}).get("name", "local-model")
                elif cfg.external_api_base:
                    endpoint = f"{cfg.external_api_base.rstrip('/')}/chat/completions"
                    headers = {"Content-Type": "application/json"}
                    if cfg.external_api_key:
                        headers["Authorization"] = f"Bearer {cfg.external_api_key}"
                    model = cfg.external_api_model or "gpt-4o-mini"
                else:
                    raise RuntimeError("尚未啟動本地模型且未設定外部 API。")

                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(
                        endpoint,
                        headers=headers,
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": task.get("payload", "")}],
                            "temperature": 0.5,
                            "max_tokens": 1024,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    output = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()

            # Optional webhook push
            webhook = task.get("webhook_url", "").strip()
            if webhook and output:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(
                            webhook,
                            json={"app": "L3M Studio", "task": task["name"], "status": status, "output": output},
                        )
                except Exception:
                    pass
        except Exception as exc:
            status = "error"
            output = str(exc)

        task["last_status"] = status
        task["last_output"] = output
        hist = task.get("history", [])
        hist.insert(0, {"timestamp": time.time(), "status": status, "output": output[:500]})
        task["history"] = hist[:15]
        self._save()


scheduler_manager = SchedulerManager()
