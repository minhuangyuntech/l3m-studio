from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from .config import APP_HOME, config_manager
from .engine import engine_manager

AGENT_SESSIONS_DIR = APP_HOME / "agent_sessions"
AGENT_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


AGENT_SYSTEM_TEMPLATE = """你是 L3M Studio 內建的本機 AI Agent，專注於在指定的工作資料夾內協助使用者完成程式設計、檔案處理與自動化任務。
目前工作資料夾：{workspace}
安全權限模式：{permission_mode}

你可以使用以下工具（若要呼叫工具，請在回覆中單獨輸出一個 ```tool_call JSON 區塊，每次可呼叫一個工具，等工具結果回傳後再繼續下一步；任務完成時直接以繁體中文總結成果，不要輸出 tool_call）：

1. 列出資料夾檔案：
```tool_call
{{"tool": "list_files", "path": "."}}
```
2. 讀取檔案內容：
```tool_call
{{"tool": "read_file", "path": "relative/path.py"}}
```
3. 建立或覆寫檔案：
```tool_call
{{"tool": "write_file", "path": "relative/path.py", "content": "完整檔案內容"}}
```
4. 在工作資料夾內執行終端指令（Python / PowerShell / Bash）：
```tool_call
{{"tool": "run_command", "command": "python script.py"}}
```

請先以簡短的「計劃」條列 2-4 個步驟（格式：`- [ ] 步驟說明`），再逐步執行工具並驗證結果。"""


TOOL_BLOCK_RE = re.compile(r"```tool_call\s*(\{.*?\})\s*```", re.DOTALL)


def _safe_resolve(workspace: Path, rel_path: str) -> Path:
    ws = workspace.resolve()
    target = (ws / rel_path).resolve()
    try:
        target.relative_to(ws)
    except ValueError:
        raise PermissionError(f"安全阻擋：路徑 {rel_path} 超出工作資料夾 {ws}")
    return target


def list_workspace_files(workspace_str: str) -> List[Dict[str, Any]]:
    ws = Path(workspace_str).expanduser().resolve()
    if not ws.exists() or not ws.is_dir():
        return []
    entries: List[Dict[str, Any]] = []
    for item in sorted(ws.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:120]:
        if item.name in (".git", "node_modules", ".venv", "__pycache__"):
            continue
        try:
            st = item.stat()
            entries.append(
                {
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size": st.st_size if item.is_file() else 0,
                    "modified_at": st.st_mtime,
                }
            )
        except OSError:
            continue
    return entries


async def _execute_tool(
    workspace: Path, tool_name: str, args: Dict[str, Any], permission_mode: str
) -> tuple[str, Optional[str]]:
    """Returns (tool_output_text, modified_file_relpath)."""
    if tool_name == "list_files":
        target = _safe_resolve(workspace, str(args.get("path", ".")))
        if not target.exists():
            return f"目錄不存在：{target}", None
        lines = []
        for p in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:80]:
            kind = "[DIR]" if p.is_dir() else f"[{p.stat().st_size} B]"
            lines.append(f"{kind} {p.name}")
        return "\n".join(lines) or "(空資料夾)", None

    if tool_name == "read_file":
        target = _safe_resolve(workspace, str(args.get("path", "")))
        if not target.exists() or not target.is_file():
            return f"找不到檔案：{args.get('path')}", None
        text = target.read_text(encoding="utf-8", errors="replace")
        return text[:12000], None

    if tool_name == "write_file":
        rel = str(args.get("path", "")).strip()
        target = _safe_resolve(workspace, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = str(args.get("content", ""))
        target.write_text(content, encoding="utf-8")
        return f"已成功寫入檔案 {rel}（{len(content)} 字元）", rel

    if tool_name == "run_command":
        cmd = str(args.get("command", "")).strip()
        if not cmd:
            return "指令為空", None
        # Basic safety check in workspace-only mode
        if permission_mode == "workspace_only":
            danger = ("rm -rf /", "format ", "del /s /q c:", "shutdown", "rd /s /q c:")
            if any(d in cmd.lower() for d in danger):
                return "安全權限阻擋：此指令可能影響工作區以外系統檔案。", None

        shell_cmd = ["powershell", "-NoProfile", "-Command", cmd] if platform.system() == "Windows" else ["bash", "-lc", cmd]
        kwargs: Dict[str, Any] = {
            "cwd": str(workspace.resolve()),
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
        }
        if platform.system() == "Windows":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = await asyncio.create_subprocess_exec(*shell_cmd, **kwargs)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=60.0)
            decoded = out.decode("utf-8", errors="replace").strip()
            return f"[exit={proc.returncode}]\n{decoded[:8000]}", None
        except asyncio.TimeoutError:
            proc.kill()
            return "指令執行逾時（超過 60 秒已自動中止）", None

    return f"未知工具：{tool_name}", None


class AgentManager:
    def _session_path(self, session_id: str) -> Path:
        safe = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
        return AGENT_SESSIONS_DIR / f"{safe}.json"

    def list_sessions(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for p in AGENT_SESSIONS_DIR.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                out.append(
                    {
                        "id": d["id"],
                        "title": d.get("title", "新任務"),
                        "workspace": d.get("workspace", ""),
                        "updated_at": d.get("updated_at", 0),
                        "changed_files": d.get("changed_files", []),
                    }
                )
            except Exception:
                continue
        out.sort(key=lambda x: x["updated_at"], reverse=True)
        return out

    def get_session(self, session_id: str) -> Dict[str, Any]:
        p = self._session_path(session_id)
        if not p.exists():
            raise FileNotFoundError("找不到該 Agent 任務")
        return json.loads(p.read_text(encoding="utf-8"))

    def create_session(self, workspace: str, title: str = "新 Agent 任務") -> Dict[str, Any]:
        ws = workspace.strip() or str((APP_HOME / "agent_workspace").resolve())
        Path(ws).mkdir(parents=True, exist_ok=True)
        now = time.time()
        session = {
            "id": uuid.uuid4().hex[:12],
            "title": title,
            "workspace": ws,
            "permission_mode": "workspace_only",
            "created_at": now,
            "updated_at": now,
            "plan": [],
            "changed_files": [],
            "events": [],
        }
        self._save(session)
        return session

    def _save(self, session: Dict[str, Any]) -> None:
        session["updated_at"] = time.time()
        self._session_path(session["id"]).write_text(
            json.dumps(session, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def delete_session(self, session_id: str) -> bool:
        p = self._session_path(session_id)
        if p.exists():
            p.unlink()
            return True
        return False

    async def run_task_stream(
        self,
        session_id: str,
        prompt: str,
        workspace: Optional[str] = None,
        permission_mode: str = "workspace_only",
        use_external_api: bool = False,
        max_steps: int = 6,
    ) -> AsyncGenerator[str, None]:
        try:
            session = self.get_session(session_id)
        except FileNotFoundError:
            session = self.create_session(workspace or "", title=prompt[:28] or "Agent 任務")

        if workspace:
            session["workspace"] = workspace
            Path(workspace).mkdir(parents=True, exist_ok=True)
        session["permission_mode"] = permission_mode
        if not session["events"] and prompt.strip():
            session["title"] = prompt.strip()[:30]

        ws_path = Path(session["workspace"]).resolve()
        cfg = config_manager.config
        if use_external_api and cfg.external_api_base:
            endpoint = f"{cfg.external_api_base.rstrip('/')}/chat/completions"
            headers = {"Content-Type": "application/json"}
            if cfg.external_api_key:
                headers["Authorization"] = f"Bearer {cfg.external_api_key}"
            model_name = cfg.external_api_model or "gpt-4o-mini"
        else:
            if engine_manager.status != "running":
                yield f"data: {json.dumps({'type': 'error', 'error': '請先於「執行」分頁啟動本地模型，或切換至第三方 API。'}, ensure_ascii=False)}\n\n"
                return
            port = engine_manager.active_config.get("port", cfg.api_port)
            endpoint = f"http://127.0.0.1:{port}/v1/chat/completions"
            headers = {"Content-Type": "application/json"}
            model_name = (engine_manager.active_model or {}).get("name", "local-model")

        session["events"].append({"role": "user", "content": prompt, "timestamp": time.time()})
        self._save(session)

        messages: List[Dict[str, str]] = [
            {
                "role": "system",
                "content": AGENT_SYSTEM_TEMPLATE.format(
                    workspace=str(ws_path),
                    permission_mode="僅限工作區（禁止刪改工作區外檔案）"
                    if permission_mode == "workspace_only"
                    else "完整執行",
                ),
            }
        ]
        for ev in session["events"][-12:]:
            if ev["role"] in ("user", "assistant"):
                messages.append({"role": ev["role"], "content": ev["content"]})

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                for step_idx in range(max_steps):
                    yield f"data: {json.dumps({'type': 'status', 'text': f'第 {step_idx + 1} 步：模型思考與規劃中...'}, ensure_ascii=False)}\n\n"
                    resp = await client.post(
                        endpoint,
                        headers=headers,
                        json={
                            "model": model_name,
                            "messages": messages,
                            "temperature": 0.3,
                            "max_tokens": 3072,
                            "stream": False,
                        },
                    )
                    if resp.status_code != 200:
                        raise RuntimeError(f"模型請求失敗 ({resp.status_code}): {resp.text[:250]}")
                    data = resp.json()
                    reply = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                    messages.append({"role": "assistant", "content": reply})

                    # Extract checklist items for right-side Plan progress
                    plan_items = re.findall(r"-\s*\[([ xX])\]\s*(.+)", reply)
                    if plan_items:
                        session["plan"] = [
                            {"done": mark.lower() == "x", "text": txt.strip()} for mark, txt in plan_items
                        ]
                        yield f"data: {json.dumps({'type': 'plan', 'plan': session['plan']}, ensure_ascii=False)}\n\n"

                    tool_match = TOOL_BLOCK_RE.search(reply)
                    clean_text = TOOL_BLOCK_RE.sub("", reply).strip()
                    if clean_text:
                        ev = {"role": "assistant", "content": clean_text, "timestamp": time.time()}
                        session["events"].append(ev)
                        yield f"data: {json.dumps({'type': 'message', 'event': ev}, ensure_ascii=False)}\n\n"

                    if not tool_match:
                        # Mark all plan steps done on final summary
                        if session["plan"]:
                            session["plan"] = [{"done": True, "text": p["text"]} for p in session["plan"]]
                            yield f"data: {json.dumps({'type': 'plan', 'plan': session['plan']}, ensure_ascii=False)}\n\n"
                        self._save(session)
                        yield f"data: {json.dumps({'type': 'done', 'changed_files': session['changed_files'], 'files': list_workspace_files(str(ws_path))}, ensure_ascii=False)}\n\n"
                        return

                    # Execute tool
                    try:
                        tool_req = json.loads(tool_match.group(1))
                    except json.JSONDecodeError as je:
                        tool_out = f"tool_call JSON 解析錯誤：{je}"
                        tool_req = {"tool": "invalid"}
                        modified = None
                    else:
                        t_name = str(tool_req.get("tool", ""))
                        yield f"data: {json.dumps({'type': 'status', 'text': f'執行工具：{t_name} ...'}, ensure_ascii=False)}\n\n"
                        tool_out, modified = await _execute_tool(ws_path, t_name, tool_req, permission_mode)

                    if modified and modified not in session["changed_files"]:
                        session["changed_files"].append(modified)

                    tool_ev = {
                        "role": "tool",
                        "tool": tool_req.get("tool", "unknown"),
                        "args": tool_req,
                        "output": tool_out,
                        "timestamp": time.time(),
                    }
                    session["events"].append(tool_ev)
                    self._save(session)
                    yield f"data: {json.dumps({'type': 'tool', 'event': tool_ev, 'changed_files': session['changed_files'], 'files': list_workspace_files(str(ws_path))}, ensure_ascii=False)}\n\n"

                    messages.append({"role": "user", "content": f"工具執行結果：\n{tool_out}"})

            self._save(session)
            yield f"data: {json.dumps({'type': 'done', 'changed_files': session['changed_files'], 'files': list_workspace_files(str(ws_path))}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)}, ensure_ascii=False)}\n\n"


agent_manager = AgentManager()
