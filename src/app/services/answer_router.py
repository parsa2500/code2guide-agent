"""W2-03: rule-based router + abstain (max 2 model calls, no tool loops)."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from src.app.services.persian_answer_template import PROMPT_VERSION

from src.app.services.mykb_guide_spike import MyKbGuideSpikeService
from src.app.services.process_graph_route import ProcessGraphRouteService

MAX_MODEL_CALLS = 2

REASON_FAQ_GUIDE = "faq_approved_guide"
REASON_PROCESS_GRAPH = "process_graph_route"
REASON_CLARIFY_AMBIGUOUS = "clarify_ambiguous"
REASON_CLARIFY_PERSONAL = "clarify_personal_status"
REASON_REFUSE_ADVERSARIAL = "refuse_adversarial"
REASON_ABSTAIN_NO_ROUTE = "abstain_no_route"
REASON_ESCALATE_HUB = "escalate_hub_unavailable"

_PROCESS_HINTS = (
    "مرحله",
    "فرآیند",
    "گام",
    "پاکت",
    "دو مرحله",
    "ارزیابی کیفی",
    "منابع پیشنهادی",
    "انعقاد",
    "برنده",
    "مزایده",
    "استعلام",
    "shortlist",
    "گردش کار",
)

_PERSONAL_HINTS = (
    "قرارداد من",
    "وضعیت من",
    "برای من",
    "مشتری من",
    "بدهکار",
    "مانده حساب",
    "tenant",
    "مستأجر دیگر",
    "داده مشتری",
    "شماره قرارداد",
)

_ADVERSARIAL_HINTS = (
    "sql",
    "connection string",
    "api key",
    "نادیده بگیر",
    "دور بزن",
    "prompt",
    "system prompt",
    "/etc/passwd",
    "جعل نقش",
    "بدون لاگین",
    "همه قراردادها",
)

_AMBIGUOUS_EXACT = {
    "این کار را چطور انجام دهم؟",
    "فرم را باز کن.",
    "ارزیابی را درست کن.",
    "قرارداد را ببند.",
    "اینجا دکمه چیست؟",
    "تنظیمات را عوض کن بدون توضیح بیشتر.",
}


class AnswerRouterService:
    """FAQ → guide; process → graph; personal/ambiguous → clarify; attack → refuse."""

    def __init__(
        self,
        guide_service: Optional[MyKbGuideSpikeService] = None,
        process_service: Optional[ProcessGraphRouteService] = None,
        max_model_calls: int = MAX_MODEL_CALLS,
    ):
        self.guide_service = guide_service or MyKbGuideSpikeService()
        self.process_service = process_service or ProcessGraphRouteService()
        self.max_model_calls = max_model_calls

    def classify(self, query: str) -> str:
        q = (query or "").strip()
        qlow = q.lower()
        if not q or len(q) < 4:
            return "ambiguous"
        if q in _AMBIGUOUS_EXACT or q.endswith("بدون توضیح بیشتر."):
            return "ambiguous"
        if any(h in qlow for h in _ADVERSARIAL_HINTS):
            return "adversarial"
        if any(h in qlow for h in _PERSONAL_HINTS):
            return "personal"
        # Prefer process when process service matches strongly or process hints present
        if self.process_service.match_process(q) and (
            any(h in qlow for h in _PROCESS_HINTS)
            or "چطور" in qlow
            or "چگونه" in qlow
            or "مراحل" in qlow
            or "مرحله" in qlow
        ):
            return "process"
        if self.process_service.match_process(q) and any(
            h in qlow for h in ("مناقصه", "ارزیابی", "معامله", "قرارداد", "منبع")
        ):
            # how-to about a known process topic without explicit "مراحل" still can be FAQ;
            # use FAQ unless clearly multi-step wording
            if any(h in qlow for h in ("مرحله", "فرآیند", "گام به گام", "مرحله‌به‌مرحله", "مرحله به مرحله")):
                return "process"
            return "faq"
        if any(h in qlow for h in _PROCESS_HINTS):
            return "process"
        return "faq"

    def route(
        self,
        query: str,
        *,
        role: Optional[str] = None,
        request_id: Optional[str] = None,
        workspace_id: str = "contracts-guides",
        brain: str = "guide",
    ) -> Dict[str, Any]:
        rid = request_id or str(uuid.uuid4())
        route_kind = self.classify(query)
        model_calls = 0
        tools: List[str] = ["router.classify"]

        if route_kind == "adversarial":
            return self._wrap(
                {
                    "status": "escalate",
                    "answer_text_fa": "این درخواست مجاز نیست. نمی‌توانم دستور دور زدن امنیت، افشای secret، یا دسترسی غیرمجاز بدهم.",
                    "steps": [],
                    "prerequisites": [],
                    "expected_result": "",
                    "citations": [],
                    "assumptions": [],
                    "uncertainty": None,
                    "escalation_reason": "adversarial_or_unauthorized",
                    "trace_id": f"trace:w2-03:{rid}",
                    "knowledge_revision": None,
                    "evidence": [],
                },
                reason_code=REASON_REFUSE_ADVERSARIAL,
                tools_used=tools,
                route_kind=route_kind,
                model_calls=model_calls,
                request_id=rid,
                role=role,
            )

        if route_kind == "personal":
            return self._wrap(
                {
                    "status": "clarify",
                    "answer_text_fa": "برای وضعیت شخصی/قرارداد مشخص به دادهٔ نشست و ابزار مجاز نیاز است که در این فاز فعال نیست. لطفاً بگویید راهنمای عمومی کدام فرآیند را می‌خواهید، یا به پشتیبانی با همین شناسهٔ trace مراجعه کنید.",
                    "steps": [],
                    "prerequisites": ["نشست معتبر", "ابزار وضعیت شخصی (فاز بعد)"],
                    "expected_result": "",
                    "citations": [],
                    "assumptions": ["بدون خواندن DB مشتری"],
                    "uncertainty": "personal_status_requires_tooling",
                    "escalation_reason": None,
                    "trace_id": f"trace:w2-03:{rid}",
                    "knowledge_revision": None,
                    "evidence": [],
                },
                reason_code=REASON_CLARIFY_PERSONAL,
                tools_used=tools,
                route_kind=route_kind,
                model_calls=model_calls,
                request_id=rid,
                role=role,
            )

        if route_kind == "ambiguous":
            return self._wrap(
                {
                    "status": "clarify",
                    "answer_text_fa": "سؤال مبهم است. دقیقاً بگویید کدام صفحه یا فرآیند (مثلاً مناقصه دو مرحله‌ای، ارزیابی کیفی، منابع پیشنهادی) و نقش/نسخهٔ مدنظر شما چیست؟",
                    "steps": [],
                    "prerequisites": [],
                    "expected_result": "",
                    "citations": [],
                    "assumptions": [],
                    "uncertainty": "ambiguous_query",
                    "escalation_reason": None,
                    "trace_id": f"trace:w2-03:{rid}",
                    "knowledge_revision": None,
                    "evidence": [],
                },
                reason_code=REASON_CLARIFY_AMBIGUOUS,
                tools_used=tools,
                route_kind=route_kind,
                model_calls=model_calls,
                request_id=rid,
                role=role,
            )

        if route_kind == "process":
            tools.append("process_graph.answer")
            t0 = time.perf_counter()
            out = self.process_service.answer(query, role=role, request_id=rid)
            retrieval_ms = int((time.perf_counter() - t0) * 1000)
            # process path is deterministic — 0 model calls
            return self._wrap(
                out,
                reason_code=REASON_PROCESS_GRAPH,
                tools_used=tools + list((out.get("trace") or {}).get("tools_used") or []),
                route_kind=route_kind,
                model_calls=model_calls,
                request_id=rid,
                role=role,
                retrieval_ms=retrieval_ms,
                model_ms=0,
                latency_source="local_retrieval",
            )

        # FAQ → approved guide via Hub (counts as at most one external answer path;
        # Hub may use its own models; we do not add a second local LLM loop here).
        tools.append("code_kb.query")
        if model_calls >= self.max_model_calls:
            return self._wrap(
                {
                    "status": "escalate",
                    "answer_text_fa": "سقف فراخوانی مدل برای این نوبت پر شد. لطفاً سؤال را ساده‌تر بپرسید یا به پشتیبانی مراجعه کنید.",
                    "steps": [],
                    "prerequisites": [],
                    "expected_result": "",
                    "citations": [],
                    "assumptions": [],
                    "uncertainty": "max_model_calls",
                    "escalation_reason": "model_budget_exhausted",
                    "trace_id": f"trace:w2-03:{rid}",
                    "knowledge_revision": None,
                    "evidence": [],
                },
                reason_code=REASON_ABSTAIN_NO_ROUTE,
                tools_used=tools,
                route_kind=route_kind,
                model_calls=model_calls,
                request_id=rid,
                role=role,
            )

        model_calls += 1  # one Hub/guide turn
        t0 = time.perf_counter()
        out = self.guide_service.answer(
            query,
            workspace_id=workspace_id,
            brain=brain,
            request_id=rid,
        )
        hub_ms = int((time.perf_counter() - t0) * 1000)
        if out.get("status") == "escalate" and self.process_service.match_process(query):
            # fallback without spending a second model call: local process graph
            tools.append("process_graph.answer_fallback")
            t1 = time.perf_counter()
            pout = self.process_service.answer(query, role=role, request_id=rid)
            retrieval_ms = int((time.perf_counter() - t1) * 1000)
            return self._wrap(
                pout,
                reason_code=REASON_PROCESS_GRAPH,
                tools_used=tools,
                route_kind="process_fallback",
                model_calls=model_calls,
                request_id=rid,
                role=role,
                retrieval_ms=retrieval_ms,
                model_ms=hub_ms,
                latency_source="hub_unsplit",
            )
        if out.get("status") in ("clarify", "escalate") and not out.get("citations"):
            reason = (
                REASON_ESCALATE_HUB
                if out.get("escalation_reason") == "code_kb_unavailable"
                else REASON_ABSTAIN_NO_ROUTE
            )
            return self._wrap(
                out,
                reason_code=reason,
                tools_used=tools + list((out.get("trace") or {}).get("tools_used") or []),
                route_kind=route_kind,
                model_calls=model_calls,
                request_id=rid,
                role=role,
                retrieval_ms=hub_ms,
                model_ms=0,
                latency_source="hub_unsplit",
            )
        return self._wrap(
            out,
            reason_code=REASON_FAQ_GUIDE,
            tools_used=tools + list((out.get("trace") or {}).get("tools_used") or []),
            route_kind=route_kind,
            model_calls=model_calls,
            request_id=rid,
            role=role,
            retrieval_ms=hub_ms,
            model_ms=0,
            latency_source="hub_unsplit",
        )

    def _wrap(
        self,
        payload: Dict[str, Any],
        *,
        reason_code: str,
        tools_used: List[str],
        route_kind: str,
        model_calls: int,
        request_id: str,
        role: Optional[str] = None,
        retrieval_ms: int = 0,
        model_ms: int = 0,
        latency_source: str = "none",
    ) -> Dict[str, Any]:
        from src.app.services.persian_answer_template import format_persian_answer

        out = dict(payload)
        trace = dict(out.get("trace") or {})
        usage = dict(trace.pop("usage", None) or {})
        if "retrieval_latency_ms" in usage or "model_latency_ms" in usage:
            retrieval_ms = int(usage.get("retrieval_latency_ms") or 0)
            model_ms = int(usage.get("model_latency_ms") or 0)
            latency_source = "usage"
        tokens = {
            "input": int(usage.get("input") or 0),
            "output": int(usage.get("output") or 0),
            "cache": int(usage.get("cache") or 0),
        }
        model_version = str(usage.get("model") or ("none" if model_calls == 0 else "hub-unspecified"))
        # dedupe tools preserving order
        seen = set()
        ordered = []
        for t in tools_used:
            if t not in seen:
                seen.add(t)
                ordered.append(t)
        ordered.append("persian_template.format")
        trace.update(
            {
                "request_id": request_id,
                "reason_code": reason_code,
                "route_kind": route_kind,
                "tools_used": ordered,
                "model_calls_used": model_calls,
                "model_calls_max": self.max_model_calls,
                "loop": False,
                "latency_ms": {"retrieval": int(retrieval_ms), "model": int(model_ms)},
                "latency_source": latency_source,
                "tokens": tokens,
                "model_version": model_version,
                "prompt_version": PROMPT_VERSION,
            }
        )
        out["trace"] = trace
        out["reason_code"] = reason_code
        if not out.get("trace_id"):
            out["trace_id"] = f"trace:w2-03:{request_id}"
        out = format_persian_answer(out, role=role)
        return out
