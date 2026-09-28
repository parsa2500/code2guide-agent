"""W3-02: server-side chat proxy — auth context + routed answer; browser never hits my-kb."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Dict, Optional

from src.app.services.answer_router import AnswerRouterService
from src.app.services.auth_context import AuthContextError, verify_context

_EXECUTOR = ThreadPoolExecutor(max_workers=8)


class ChatProxyService:
    def __init__(
        self,
        router: Optional[AnswerRouterService] = None,
        timeout_seconds: float = 25.0,
    ):
        self.router = router or AnswerRouterService()
        self.timeout_seconds = timeout_seconds

    def handle_turn(
        self,
        *,
        text: str,
        auth_context: Dict[str, Any],
        browser_claims: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        rid = request_id or str(uuid.uuid4())
        if not (text or "").strip():
            return self._ui_error("پیام نمی‌تواند خالی باشد.", rid, session_id)

        try:
            claims = verify_context(auth_context, browser_claims=browser_claims)
        except AuthContextError as exc:
            return self._ui_error(
                "نشست نامعتبر است. لطفاً دوباره وارد شوید.",
                rid,
                session_id,
                extra={
                    "success": False,
                    "error_code": exc.code,
                    "fallback": "support",
                },
            )

        role = None
        roles = claims.get("role_labels") or []
        if roles:
            role = roles[0]

        def _run():
            return self.router.route(
                text.strip(),
                role=role,
                request_id=rid,
            )

        try:
            future = _EXECUTOR.submit(_run)
            routed = future.result(timeout=self.timeout_seconds)
        except FuturesTimeout:
            return self._ui_error(
                "زمان پاسخ به پایان رسید. لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.",
                rid,
                session_id,
                extra={
                    "success": False,
                    "error_code": "timeout",
                    "fallback": "support",
                    "trace_id": f"trace:w3-02:{rid}",
                },
            )
        except Exception as exc:
            return self._ui_error(
                "خطای سیستمی رخ داده است. لطفاً دوباره تلاش کنید یا به پشتیبانی مراجعه کنید.",
                rid,
                session_id,
                extra={
                    "success": False,
                    "error_code": "proxy_failure",
                    "fallback": "support",
                    "detail": str(exc)[:200],
                    "trace_id": f"trace:w3-02:{rid}",
                },
            )

        answer = (routed.get("answer_text_fa") or "").strip()
        status = routed.get("status") or "answered"
        trace_id = routed.get("trace_id") or f"trace:w3-02:{rid}"

        if status == "escalate" and not answer:
            answer = (
                "این مورد به پشتیبانی ارجاع شد. "
                f"شناسهٔ پیگیری: {trace_id}"
            )

        # Shape compatible with existing ChatBot Index.cshtml expectations
        return {
            "response": answer,
            "messageId": str(uuid.uuid4()),
            "tokensUsed": int((routed.get("trace") or {}).get("model_calls_used") or 0),
            "sessionId": session_id or str(uuid.uuid4()),
            "success": status in ("answered", "clarify"),
            "error": "" if status in ("answered", "clarify") else (routed.get("escalation_reason") or ""),
            "trace_id": trace_id,
            "status": status,
            "reason_code": routed.get("reason_code"),
            "fallback": None if status in ("answered", "clarify") else "support",
            "auth": {
                "tenant_id": claims.get("tenant_id"),
                "user_id": claims.get("user_id"),
                "page_route": claims.get("page_route"),
                "product_version": claims.get("product_version"),
            },
            "tools_used": (routed.get("trace") or {}).get("tools_used") or [],
        }

    @staticmethod
    def _ui_error(
        message: str,
        request_id: str,
        session_id: Optional[str],
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        out = {
            "response": "",
            "messageId": "",
            "tokensUsed": 0,
            "sessionId": session_id or "",
            "success": False,
            "error": message,
            "trace_id": f"trace:w3-02:{request_id}",
            "fallback": "support",
        }
        if extra:
            out.update(extra)
        return out
