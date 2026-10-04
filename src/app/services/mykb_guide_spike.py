"""W1-04 spike: answer Persian guide turns from my-kb only (no local Qdrant/SQLite index)."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from src.integrations.code_kb_client import CodeKbClient, CodeKbError


def _usage_from_hub(result: Dict[str, Any]) -> Dict[str, Any]:
    """Copy numeric usage only. Do not keep prompt or answer text."""
    raw = result.get("usage") or result.get("tokenUsage") or {}
    if not isinstance(raw, dict):
        raw = {}

    def _n(*keys: str) -> int:
        for key in keys:
            value = raw.get(key)
            if isinstance(value, (int, float)):
                return int(value)
        return 0

    usage: Dict[str, Any] = {
        "input": _n("prompt_tokens", "input_tokens", "promptTokenCount"),
        "output": _n("completion_tokens", "output_tokens", "candidatesTokenCount"),
        "cache": _n("cache_tokens", "cached_tokens", "cachedContentTokenCount"),
    }
    model = raw.get("model") or result.get("model")
    if isinstance(model, str) and model.strip():
        usage["model"] = model.strip()[:120]
    latency = result.get("latencyMs") or result.get("latency_ms")
    if isinstance(latency, dict):
        if isinstance(latency.get("retrieval"), (int, float)):
            usage["retrieval_latency_ms"] = int(latency["retrieval"])
        if isinstance(latency.get("model"), (int, float)):
            usage["model_latency_ms"] = int(latency["model"])
    return usage


class MyKbGuideSpikeService:
    """Map Hub query packets into the blueprint answer/evidence shape.

    Explicitly does **not** call HybridIndexer / index_workspace / local graph.
    """

    def __init__(self, client: Optional[CodeKbClient] = None):
        self.client = client or CodeKbClient()

    def answer(
        self,
        message: str,
        *,
        workspace_id: str = "contracts-guides",
        brain: str = "guide",
        product_version: str = "Contracts.Main@local-baseline-2026-09-27",
        page_route: str = "/ChatBot",
        role_scope: Optional[List[str]] = None,
        revision_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        role_scope = role_scope or ["کارشناس", "مدیر", "پشتیبانی"]
        trace_id = f"trace:w1-04:{request_id or uuid.uuid4()}"
        tools_used = ["code_kb.query"]  # never local_index

        try:
            hub = self.client.query(
                workspace_id,
                message,
                brain=brain,
                revision_id=revision_id,
            )
        except CodeKbError as exc:
            return {
                "status": "escalate",
                "answer_text_fa": "در حال حاضر دانش مرکزی در دسترس نیست. لطفاً بعداً دوباره تلاش کنید یا به پشتیبانی مراجعه کنید.",
                "steps": [],
                "prerequisites": [],
                "expected_result": "",
                "citations": [],
                "assumptions": [],
                "uncertainty": str(exc),
                "escalation_reason": "code_kb_unavailable",
                "trace_id": trace_id,
                "knowledge_revision": revision_id,
                "evidence": [],
                "trace": {
                    "request_id": request_id,
                    "workspace_id": workspace_id,
                    "brain": brain,
                    "tools_used": tools_used,
                    "local_index_used": False,
                    "error": str(exc),
                    "http_status": exc.status,
                },
            }

        result = hub.get("result") if isinstance(hub.get("result"), dict) else hub
        revision = (
            result.get("revisionId")
            or hub.get("revisionId")
            or revision_id
            or "unknown"
        )
        answers = result.get("answers") or []
        citations_raw = result.get("citations") or result.get("evidence") or []
        status_hub = result.get("status") or hub.get("status") or "partial"

        answer_objs = [
            a
            for a in answers
            if isinstance(a, dict) and a.get("kind") == "answer" and a.get("text")
        ]
        # Prefer answers whose text overlaps query tokens (Hub order can be noisy).
        query_tokens = [t for t in message.replace("؟", " ").split() if len(t) >= 3]

        def _overlap_score(ans: Dict[str, Any]) -> int:
            text = str(ans.get("text") or "")
            return sum(1 for t in query_tokens if t in text)

        answer_objs.sort(key=_overlap_score, reverse=True)
        answer_texts = [a.get("text") for a in answer_objs]
        if not answer_texts:
            return {
                "status": "clarify",
                "answer_text_fa": "برای این سؤال شاهد کافی در دانش نسخه‌دار پیدا نشد. لطفاً دقیق‌تر بگویید کدام فرآیند یا صفحه مدنظرتان است؟",
                "steps": [],
                "prerequisites": [],
                "expected_result": "",
                "citations": [],
                "assumptions": ["مسیر پاسخ فقط از my-kb/Code-KB خوانده شد؛ ایندکس محلی code2guide استفاده نشد."],
                "uncertainty": "no_evidence_or_empty_answers",
                "escalation_reason": None,
                "trace_id": trace_id,
                "knowledge_revision": revision,
                "evidence": [],
                "trace": {
                    "request_id": request_id,
                    "workspace_id": workspace_id,
                    "brain": brain,
                    "hub_status": status_hub,
                    "tools_used": tools_used,
                    "local_index_used": False,
                    "query_id": result.get("queryId"),
                },
            }

        primary = answer_texts[0]
        evidence_items: List[Dict[str, Any]] = []
        citations: List[Dict[str, Any]] = []
        for idx, cite in enumerate(citations_raw[:5]):
            if not isinstance(cite, dict):
                continue
            eid = (
                cite.get("id")
                or cite.get("evidenceId")
                or cite.get("evidence_id")
                or f"ev:hub:{idx+1}"
            )
            label = (
                cite.get("title")
                or cite.get("label")
                or cite.get("path")
                or cite.get("source_path")
                or f"شاهد {idx+1}"
            )
            path = cite.get("path") or cite.get("source_path") or cite.get("uri") or ""
            open_uri = cite.get("uri") or cite.get("url") or (
                f"codekb://{workspace_id}/{path}" if path else f"codekb://{workspace_id}/{eid}"
            )
            evidence_items.append(
                {
                    "evidence_id": str(eid),
                    "tenant_scope": f"workspace:{workspace_id}",
                    "product_version": product_version,
                    "role_scope": role_scope,
                    "page_route": page_route,
                    "source_path": str(path or label),
                    "source_revision": str(revision),
                    "extraction_method": "guide_fixture",
                    "reviewer_status": "needs_review",
                    "updated_at": result.get("generatedAt") or "2026-09-28T00:00:00Z",
                    "confidence": float(
                        (cite.get("score") if isinstance(cite.get("score"), (int, float)) else 0.7)
                    ),
                    "snippet": (cite.get("excerpt") or cite.get("text") or "")[:400],
                    "open": {
                        "kind": "guide",
                        "uri": str(open_uri),
                        "label": str(label)[:120],
                    },
                }
            )
            citations.append(
                {
                    "evidence_id": str(eid),
                    "label": str(label)[:120],
                    "open_uri": str(open_uri),
                }
            )

        # If Hub omitted structured citations, synthesize from ranked answer evidenceIds
        if not citations and answer_objs:
            for idx, ans in enumerate(answer_objs[:3]):
                eid = (ans.get("evidenceIds") or [f"ev:answer:{idx+1}"])[0]
                label = f"پاسخ Hub #{idx+1}"
                open_uri = f"codekb://{workspace_id}/answers/{idx+1}"
                citations.append(
                    {"evidence_id": str(eid), "label": label, "open_uri": open_uri}
                )
                evidence_items.append(
                    {
                        "evidence_id": str(eid),
                        "tenant_scope": f"workspace:{workspace_id}",
                        "product_version": product_version,
                        "role_scope": role_scope,
                        "page_route": page_route,
                        "source_path": "hub:answer",
                        "source_revision": str(revision),
                        "extraction_method": "guide_fixture",
                        "reviewer_status": "needs_review",
                        "updated_at": "2026-09-28T00:00:00Z",
                        "confidence": float(
                            ((ans.get("confidence") or {}).get("score") or 0.7)
                        ),
                        "snippet": str(ans.get("text") or "")[:400],
                        "open": {"kind": "guide", "uri": open_uri, "label": label},
                    }
                )

        steps = [
            {
                "label": "مرور پاسخ دانش نسخه‌دار",
                "instruction": "مراحل زیر را با نام دکمه‌ها/بخش‌های واقعی سامانه تطبیق دهید؛ اگر با نسخهٔ نصب شما فرق داشت به پشتیبانی بگویید.",
            }
        ]

        return {
            "status": "answered" if status_hub in ("ok", "answered", "partial") else status_hub,
            "answer_text_fa": str(primary),
            "steps": steps,
            "prerequisites": [
                "دسترسی به دانش مرکزی my-kb/Code-KB",
                f"workspace={workspace_id}",
                f"brain={brain}",
            ],
            "expected_result": "پاسخ فارسی با شناسهٔ trace و حداقل یک شاهد نسخه‌دار",
            "citations": citations,
            "assumptions": [
                "ایندکس/بردار محلی code2guide در این مسیر خاموش است.",
                "منبع حقیقت بازیابی: Hub query با source_revision همان revision فعال workspace.",
            ],
            "uncertainty": None if status_hub == "ok" else f"hub_status={status_hub}",
            "escalation_reason": None,
            "trace_id": trace_id,
            "knowledge_revision": revision,
            "evidence": evidence_items,
            "trace": {
                "request_id": request_id,
                "workspace_id": workspace_id,
                "brain": brain,
                "hub_status": status_hub,
                "query_id": result.get("queryId"),
                "tools_used": tools_used,
                "local_index_used": False,
                "answer_count": len(answer_texts),
                "citation_count": len(citations),
                "usage": _usage_from_hub(result),
            },
        }
