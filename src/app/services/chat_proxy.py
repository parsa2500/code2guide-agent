"""W3-02: server-side chat proxy — auth context + routed answer; browser never hits my-kb."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Dict, Optional

from src.app.services.answer_router import AnswerRouterService
from src.app.services.auth_context import AuthContextError, verify_context
from src.app.services.turn_telemetry import TurnTelemetryStore, build_turn_record

_EXECUTOR = ThreadPoolExecutor(max_workers=8)


class ChatProxyService:
    def __init__(
        self,
        router: Optional[AnswerRouterService] = None,
        timeout_seconds: float = 25.0,
        store: Optional[TurnTelemetryStore] = None,
    ):
        self.router = router or AnswerRouterService()
        self.timeout_seconds = timeout_seconds
        self.store = store

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
            out = self._ui_error("پیام نمی‌تواند خالی باشد.", rid, session_id)
            self._remember(out, tenant_id=None, question_type="empty", feedback_allowed=False)
            return out

        try:
            claims = verify_context(auth_context, browser_claims=browser_claims)
        except AuthContextError as exc:
            out = self._ui_error(
                "نشست نامعتبر است. لطفاً دوباره وارد شوید.",
                rid,
                session_id,
                extra={
                    "success": False,
                    "error_code": exc.code,
                    "fallback": "support",
                },
            )
            self._remember(
                out,
                tenant_id=None,
                question_type=exc.code,
                feedback_allowed=False,
            )
            return out

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
            out = self._ui_error(
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
            self._remember(
                out,
                tenant_id=claims.get("tenant_id"),
                question_type="timeout",
                document_version=claims.get("product_version"),
                feedback_allowed=True,
            )
            return out
        except Exception as exc:
            out = self._ui_error(
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
            self._remember(
                out,
                tenant_id=claims.get("tenant_id"),
                question_type="proxy_failure",
                document_version=claims.get("product_version"),
                feedback_allowed=True,
            )
            return out

        answer = (routed.get("answer_text_fa") or "").strip()
        status = routed.get("status") or "answered"
        trace_id = routed.get("trace_id") or f"trace:w3-02:{rid}"

        if status == "escalate" and not answer:
            answer = (
                "این مورد به پشتیبانی ارجاع شد. "
                f"شناسهٔ پیگیری: {trace_id}"
            )

        trace = routed.get("trace") or {}
        latency = trace.get("latency_ms") or {}
        # Shape compatible with existing ChatBot Index.cshtml expectations.
        # Telemetry stays server-side and does not include the answer body.
        out = {
            "response": answer,
            "messageId": str(uuid.uuid4()),
            "tokensUsed": int(trace.get("model_calls_used") or 0),
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
            "tools_used": trace.get("tools_used") or [],
        }
        self._remember(
            out,
            tenant_id=claims.get("tenant_id"),
            question_type=str(trace.get("route_kind") or routed.get("reason_code") or status),
            document_version=routed.get("knowledge_revision") or claims.get("product_version"),
            model_version=str(trace.get("model_version") or "none"),
            retrieval_ms=int(latency.get("retrieval") or 0),
            model_ms=int(latency.get("model") or 0),
            latency_source=str(trace.get("latency_source") or "none"),
            tokens=trace.get("tokens") or {},
            feedback_allowed=True,
            response_chars=len(answer),
        )
        return out

    def _remember(
        self,
        out: Dict[str, Any],
        *,
        tenant_id: Optional[str],
        question_type: str,
        feedback_allowed: bool,
        document_version: Optional[str] = None,
        model_version: str = "none",
        retrieval_ms: int = 0,
        model_ms: int = 0,
        latency_source: str = "none",
        tokens: Optional[Dict[str, int]] = None,
        response_chars: int = 0,
    ) -> None:
        if self.store is None:
            return
        status = out.get("status") or ("answered" if out.get("success") else "rejected")
        self.store.record(
            build_turn_record(
                trace_id=str(out.get("trace_id") or ""),
                tenant_id=tenant_id,
                question_type=question_type,
                document_version=document_version,
                model_version=model_version,
                retrieval_ms=retrieval_ms,
                model_ms=model_ms,
                latency_source=latency_source,
                tokens=tokens or {},
                response_status=str(status),
                response_chars=response_chars,
                feedback_allowed=feedback_allowed,
            )
        )

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
