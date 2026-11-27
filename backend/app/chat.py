from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from .config import CHATS_DIR, config_manager
from .engine import engine_manager


class ChatManager:
    def __init__(self) -> None:
        CHATS_DIR.mkdir(parents=True, exist_ok=True)

    def _chat_path(self, chat_id: str) -> Path:
        safe_id = "".join(c for c in chat_id if c.isalnum() or c in ("-", "_"))
        return CHATS_DIR / f"{safe_id}.json"

    def list_chats(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for p in CHATS_DIR.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                items.append(
                    {
                        "id": data["id"],
                        "title": data.get("title", "新對話"),
                        "updated_at": data.get("updated_at", 0),
                        "created_at": data.get("created_at", 0),
                        "message_count": len(data.get("messages", [])),
                        "model_name": data.get("model_name", ""),
                    }
                )
            except Exception:
                continue
        items.sort(key=lambda x: x["updated_at"], reverse=True)
        return items

    def get_chat(self, chat_id: str) -> Dict[str, Any]:
        p = self._chat_path(chat_id)
        if not p.exists():
            raise FileNotFoundError("找不到該對話紀錄")
        return json.loads(p.read_text(encoding="utf-8"))

    def create_chat(self, title: str = "新對話", system_prompt: str = "") -> Dict[str, Any]:
        now = time.time()
        chat = {
            "id": uuid.uuid4().hex[:12],
            "title": title,
            "system_prompt": system_prompt
            or "你是運行在使用者本機電腦上的 AI 助手。請使用繁體中文回答（除非使用者要求其他語言），程式碼請標註正確語言並保持完整可執行。",
            "model_name": (engine_manager.active_model or {}).get("name", ""),
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        self._save_chat(chat)
        return chat

    def _save_chat(self, chat: Dict[str, Any]) -> None:
        chat["updated_at"] = time.time()
        self._chat_path(chat["id"]).write_text(
            json.dumps(chat, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def delete_chat(self, chat_id: str) -> bool:
        p = self._chat_path(chat_id)
        if p.exists():
            p.unlink()
            return True
        return False

    def _build_api_messages(
        self,
        chat: Dict[str, Any],
        user_text: str,
        attachments: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        api_msgs: List[Dict[str, Any]] = []
        sys_p = system_prompt if system_prompt is not None else chat.get("system_prompt", "")
        if sys_p:
            api_msgs.append({"role": "system", "content": sys_p})

        for m in chat.get("messages", []):
            api_msgs.append(self._format_single_msg(m))

        current_msg = {
            "role": "user",
            "content": user_text,
            "attachments": attachments,
        }
        api_msgs.append(self._format_single_msg(current_msg))
        return api_msgs

    def _format_single_msg(self, m: Dict[str, Any]) -> Dict[str, Any]:
        atts = m.get("attachments") or []
        images = [a for a in atts if a.get("type") == "image" and a.get("data_url")]
        text_files = [a for a in atts if a.get("type") == "text" and a.get("content")]

        text_body = m.get("content", "")
        if text_files:
            extra = "\n\n".join(
                f"--- 附件：{tf.get('name', 'file')} ---\n{tf['content']}" for tf in text_files
            )
            text_body = f"{text_body}\n\n{extra}".strip()

        if images and m["role"] == "user":
            parts: List[Dict[str, Any]] = []
            if text_body:
                parts.append({"type": "text", "text": text_body})
            for img in images:
                parts.append({"type": "image_url", "image_url": {"url": img["data_url"]}})
            return {"role": "user", "content": parts}
        return {"role": m["role"], "content": text_body}

    async def stream_completion(
        self,
        chat_id: str,
        user_text: str,
        attachments: List[Dict[str, Any]],
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 4096,
        thinking: bool = True,
        system_prompt: Optional[str] = None,
        use_external_api: bool = False,
    ) -> AsyncGenerator[str, None]:
        try:
            chat = self.get_chat(chat_id)
        except FileNotFoundError:
            chat = self.create_chat(title=user_text[:28] or "新對話")

        if system_prompt is not None:
            chat["system_prompt"] = system_prompt

        cfg = config_manager.config
        if use_external_api and cfg.external_api_base:
            endpoint = f"{cfg.external_api_base.rstrip('/')}/chat/completions"
            headers = {"Content-Type": "application/json"}
            if cfg.external_api_key:
                headers["Authorization"] = f"Bearer {cfg.external_api_key}"
            model_name = cfg.external_api_model or "gpt-4o-mini"
        else:
            if engine_manager.status != "running":
                yield f"data: {json.dumps({'type': 'error', 'error': '目前尚未啟動本地模型，請先前往「執行」分頁啟動模型。'}, ensure_ascii=False)}\n\n"
                return
            port = engine_manager.active_config.get("port", cfg.api_port)
            endpoint = f"http://127.0.0.1:{port}/v1/chat/completions"
            headers = {"Content-Type": "application/json"}
            model_name = (engine_manager.active_model or {}).get("name", "local-model")

        api_messages = self._build_api_messages(chat, user_text, attachments, system_prompt)

        # Save user message first
        if not chat["messages"] and user_text.strip():
            chat["title"] = user_text.strip()[:30]
        chat["model_name"] = model_name
        chat["messages"].append(
            {
                "id": uuid.uuid4().hex[:10],
                "role": "user",
                "content": user_text,
                "attachments": attachments,
                "timestamp": time.time(),
            }
        )
        self._save_chat(chat)

        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": api_messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if not use_external_api:
            payload["chat_template_kwargs"] = {"enable_thinking": thinking}

        assistant_content = ""
        assistant_thinking = ""
        in_think_tag = False
        token_count = 0
        start_time = time.monotonic()
        first_token_time: Optional[float] = None
        final_tps = 0.0

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", endpoint, json=payload, headers=headers) as resp:
                    if resp.status_code != 200:
                        err_body = (await resp.aread()).decode("utf-8", errors="replace")
                        yield f"data: {json.dumps({'type': 'error', 'error': f'推理請求失敗 ({resp.status_code}): {err_body[:300]}'}, ensure_ascii=False)}\n\n"
                        return

                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            chunk = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        # llama-server timings if provided
                        timings = chunk.get("timings")
                        if timings and timings.get("predicted_per_second"):
                            final_tps = float(timings["predicted_per_second"])

                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}

                        r_piece = delta.get("reasoning_content") or ""
                        c_piece = delta.get("content") or ""

                        if r_piece:
                            if first_token_time is None:
                                first_token_time = time.monotonic()
                            token_count += 1
                            assistant_thinking += r_piece
                            elapsed = max(time.monotonic() - (first_token_time or start_time), 0.05)
                            tps = round(token_count / elapsed, 1)
                            yield f"data: {json.dumps({'type': 'thinking', 'delta': r_piece, 'tok_s': tps}, ensure_ascii=False)}\n\n"

                        if c_piece:
                            if first_token_time is None:
                                first_token_time = time.monotonic()
                            token_count += 1

                            # Handle inline <think>...</think> tags gracefully
                            buf = c_piece
                            while buf:
                                if not in_think_tag:
                                    idx = buf.find("<think>")
                                    if idx != -1:
                                        before = buf[:idx]
                                        if before:
                                            assistant_content += before
                                            elapsed = max(time.monotonic() - (first_token_time or start_time), 0.05)
                                            yield f"data: {json.dumps({'type': 'content', 'delta': before, 'tok_s': round(token_count / elapsed, 1)}, ensure_ascii=False)}\n\n"
                                        in_think_tag = True
                                        buf = buf[idx + 7:]
                                    else:
                                        assistant_content += buf
                                        elapsed = max(time.monotonic() - (first_token_time or start_time), 0.05)
                                        yield f"data: {json.dumps({'type': 'content', 'delta': buf, 'tok_s': round(token_count / elapsed, 1)}, ensure_ascii=False)}\n\n"
                                        buf = ""
                                else:
                                    idx = buf.find("</think>")
                                    if idx != -1:
                                        inside = buf[:idx]
                                        if inside:
                                            assistant_thinking += inside
                                            elapsed = max(time.monotonic() - (first_token_time or start_time), 0.05)
                                            yield f"data: {json.dumps({'type': 'thinking', 'delta': inside, 'tok_s': round(token_count / elapsed, 1)}, ensure_ascii=False)}\n\n"
                                        in_think_tag = False
                                        buf = buf[idx + 8:]
                                    else:
                                        assistant_thinking += buf
                                        elapsed = max(time.monotonic() - (first_token_time or start_time), 0.05)
                                        yield f"data: {json.dumps({'type': 'thinking', 'delta': buf, 'tok_s': round(token_count / elapsed, 1)}, ensure_ascii=False)}\n\n"
                                        buf = ""

            total_elapsed = max(time.monotonic() - (first_token_time or start_time), 0.05)
            tok_s = round(final_tps if final_tps > 0 else (token_count / total_elapsed), 1)
            assistant_msg = {
                "id": uuid.uuid4().hex[:10],
                "role": "assistant",
                "content": assistant_content.strip(),
                "thinking": assistant_thinking.strip(),
                "model_name": model_name,
                "tok_s": tok_s,
                "tokens": token_count,
                "timestamp": time.time(),
            }
            chat["messages"].append(assistant_msg)
            self._save_chat(chat)

            yield f"data: {json.dumps({'type': 'done', 'message': assistant_msg, 'chat_title': chat['title']}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)}, ensure_ascii=False)}\n\n"


chat_manager = ChatManager()
