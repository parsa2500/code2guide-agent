"""Thin HTTP client for Code-KB (my-kb) Hub query — no local index."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


class CodeKbError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


def _default_base_url() -> str:
    try:
        from src.core.config import settings

        return (settings.code_kb_base_url or "http://127.0.0.1:5051").rstrip("/")
    except Exception:
        return (os.getenv("CODE_KB_BASE_URL") or "http://127.0.0.1:5051").rstrip("/")


def _default_token() -> Optional[str]:
    try:
        from src.core.config import settings

        if settings.code_kb_token:
            return settings.code_kb_token
    except Exception:
        pass
    return os.getenv("CODE_KB_TOKEN") or os.getenv("DEV_AUTH_TOKEN")


class CodeKbClient:
    """POST /api/v2/workspaces/{id}/query against a local or remote Hub."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ):
        self.base_url = (base_url or _default_base_url()).rstrip("/")
        self.token = token if token is not None else _default_token()
        self.timeout_seconds = timeout_seconds

    def query(
        self,
        workspace_id: str,
        text: str,
        *,
        brain: str = "guide",
        revision_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.token:
            raise CodeKbError(
                "CODE_KB_TOKEN (or DEV_AUTH_TOKEN) is not set; refuse unauthenticated Hub call"
            )
        payload: Dict[str, Any] = {"brain": brain, "text": text}
        if revision_id:
            payload["revisionId"] = revision_id
        path = f"/api/v2/workspaces/{workspace_id}/query"
        return self._request_json("POST", path, payload)

    def status(self, workspace_id: str) -> Dict[str, Any]:
        path = f"/api/v2/workspaces/{workspace_id}/status"
        return self._request_json("GET", path)

    def _request_json(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/json")
        req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(body_text) if body_text else None
            except json.JSONDecodeError:
                body = body_text
            raise CodeKbError(
                f"Code-KB Hub HTTP {exc.code}: {body_text[:300]}",
                status=exc.code,
                body=body,
            ) from exc
        except urllib.error.URLError as exc:
            raise CodeKbError(f"Cannot reach Code-KB Hub at {self.base_url}: {exc}") from exc
