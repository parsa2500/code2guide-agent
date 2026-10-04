"""Local, bounded chat sessions for the independent Contracts Guide lab."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from threading import RLock
from typing import Any, Mapping
import uuid


SESSION_ID = re.compile(r"^[a-f0-9]{32}$")
MAX_MESSAGES = 40
MAX_SESSIONS = 100
ALLOWED_PAGE_KEYS = {
    "page_route",
    "page_title",
    "entity_type",
    "entity_id",
    "tab",
    "form_id",
    "record_id",
    "data",
}
SENSITIVE_KEYS = {
    "tenant",
    "tenant_id",
    "user",
    "user_id",
    "role",
    "roles",
    "token",
    "access_token",
    "password",
    "secret",
    "cookie",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _safe_data(value: Any, depth: int = 0) -> Any:
    """Keep page data useful while bounding size and excluding nested secrets."""
    if depth > 2:
        return _text(value, 240)
    if isinstance(value, Mapping):
        result = {}
        for key, item in list(value.items())[:20]:
            key_text = _text(key, 64).lower()
            if key_text in SENSITIVE_KEYS or any(token in key_text for token in SENSITIVE_KEYS):
                continue
            result[key_text] = _safe_data(item, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_safe_data(item, depth + 1) for item in list(value)[:20]]
    if isinstance(value, (str, int, float, bool)):
        return _text(value, 500) if isinstance(value, str) else value
    return _text(value, 240)


def sanitize_page_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key, item in value.items():
        key_text = _text(key, 64).lower()
        if key_text not in ALLOWED_PAGE_KEYS:
            continue
        if key_text == "data":
            if isinstance(item, Mapping):
                result[key_text] = _safe_data(item)
            continue
        result[key_text] = _text(item, 240)
    return result


class GuideSessionStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.lock = RLock()

    def _path(self, session_id: str) -> Path:
        if not SESSION_ID.fullmatch(session_id):
            raise ValueError("invalid_session_id")
        return self.directory / f"{session_id}.json"

    def _write(self, session: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.directory / f"{session['id']}.tmp"
        temporary.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._path(session["id"]))

    def create(self, page_context: Any = None) -> dict[str, Any]:
        with self.lock:
            session = {
                "id": uuid.uuid4().hex,
                "title": "گفت‌وگوی جدید",
                "created_at": now(),
                "updated_at": now(),
                "page_context": sanitize_page_context(page_context),
                "messages": [],
            }
            self._write(session)
            self._trim()
            return session

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self.lock:
            try:
                data = json.loads(self._path(session_id).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            return data if isinstance(data, dict) else None

    def get_or_create(self, session_id: str | None, page_context: Any = None) -> dict[str, Any]:
        if session_id:
            existing = self.get(session_id)
            if existing is not None:
                context = sanitize_page_context(page_context)
                if context:
                    existing["page_context"] = context
                    existing["updated_at"] = now()
                    with self.lock:
                        self._write(existing)
                return existing
        return self.create(page_context)

    def append_user(self, session_id: str, text: str, page_context: Any = None) -> dict[str, Any]:
        with self.lock:
            session = self.get(session_id)
            if session is None:
                raise KeyError(session_id)
            context = sanitize_page_context(page_context)
            if context:
                session["page_context"] = context
            message = {"role": "user", "text": _text(text, 1200), "at": now()}
            if context:
                message["page_context"] = context
            session.setdefault("messages", []).append(message)
            session["messages"] = session["messages"][-MAX_MESSAGES:]
            if session["title"] == "گفت‌وگوی جدید":
                session["title"] = _text(text, 70) or session["title"]
            session["updated_at"] = now()
            self._write(session)
            return session

    def append_assistant(self, session_id: str, response: Mapping[str, Any]) -> dict[str, Any]:
        with self.lock:
            session = self.get(session_id)
            if session is None:
                raise KeyError(session_id)
            message = {
                "role": "assistant",
                "text": _text(response.get("answer"), 5000),
                "status": _text(response.get("status"), 40),
                "trace_id": _text(response.get("trace_id"), 80),
                "at": now(),
            }
            steps = response.get("steps")
            if isinstance(steps, list):
                message["steps"] = [
                    {"text": _text(item.get("text"), 800)}
                    for item in steps[:20]
                    if isinstance(item, Mapping)
                ]
            citations = response.get("citations")
            if isinstance(citations, list):
                message["citations"] = [
                    {
                        "id": _text(item.get("id"), 120),
                        "title": _text(item.get("title"), 240),
                        "uri": _text(item.get("uri"), 500),
                        "url": _text(item.get("url"), 500),
                    }
                    for item in citations[:40]
                    if isinstance(item, Mapping)
                ]
            session.setdefault("messages", []).append(message)
            session["messages"] = session["messages"][-MAX_MESSAGES:]
            session["updated_at"] = now()
            self._write(session)
            return session

    def list(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = []
            for path in self.directory.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(data, dict) and SESSION_ID.fullmatch(str(data.get("id", ""))):
                    rows.append({key: data.get(key) for key in ("id", "title", "created_at", "updated_at")})
            return sorted(rows, key=lambda item: item.get("updated_at", ""), reverse=True)[:MAX_SESSIONS]

    def _trim(self) -> None:
        paths = sorted(self.directory.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in paths[MAX_SESSIONS:]:
            try:
                path.unlink()
            except OSError:
                pass


def context_for_prompt(context: Any) -> str:
    safe = sanitize_page_context(context)
    if not safe:
        return ""
    return json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
