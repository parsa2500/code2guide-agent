"""W2-02: process graph route — only subgraph + related chunks enter the answer path."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_DEFAULT_GRAPH = _DATA_DIR / "process-graphs-v0.json"
_DEFAULT_CHUNKS = _DATA_DIR / "chunks-v0.jsonl"


def _tokenize(text: str) -> List[str]:
    text = text.replace("‌", " ").replace("؟", " ").replace("،", " ")
    return [t for t in re.split(r"\s+", text.lower()) if len(t) >= 2]


class ProcessGraphRouteService:
    """Select a process subgraph and format a Persian step guide.

    Does **not** dump the full knowledge corpus into model context: only the matched
    process steps plus related chunk snippets (capped).
    """

    def __init__(
        self,
        graph_path: Optional[str] = None,
        chunks_path: Optional[str] = None,
    ):
        self.graph_path = Path(
            graph_path
            or os.getenv("PROCESS_GRAPH_PATH")
            or _DEFAULT_GRAPH
        )
        self.chunks_path = Path(
            chunks_path
            or os.getenv("PROCESS_CHUNKS_PATH")
            or _DEFAULT_CHUNKS
        )
        self._dataset = self._load_graph()
        self._chunks = self._load_chunks()

    def _load_graph(self) -> Dict[str, Any]:
        return json.loads(self.graph_path.read_text(encoding="utf-8"))

    def _load_chunks(self) -> List[Dict[str, Any]]:
        if not self.chunks_path.exists():
            return []
        rows = []
        for line in self.chunks_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def match_process(self, query: str) -> Optional[Dict[str, Any]]:
        q = query.lower()
        best: Optional[Tuple[int, Dict[str, Any]]] = None
        for proc in self._dataset.get("processes") or []:
            score = 0
            title = (proc.get("title_fa") or "").lower()
            if title and title in q:
                score += 5
            for alias in proc.get("aliases") or []:
                if str(alias).lower() in q:
                    score += 3
            for t in _tokenize(query):
                if t in title:
                    score += 1
            if score >= 3 and (best is None or score > best[0]):
                best = (score, proc)
        return best[1] if best else None

    def related_chunks(self, process: Dict[str, Any], limit: int = 4) -> List[Dict[str, Any]]:
        docs = set(process.get("related_chunk_docs") or [])
        out = []
        for ch in self._chunks:
            if ch.get("doc_id") in docs:
                out.append(
                    {
                        "chunk_id": ch.get("chunk_id"),
                        "title": ch.get("title"),
                        "section_title": ch.get("section_title"),
                        "source_path": ch.get("source_path"),
                        "page_route": ch.get("page_route"),
                        "snippet": (ch.get("text") or "")[:500],
                        "evidence_ids": ch.get("evidence_ids") or [],
                    }
                )
            if len(out) >= limit:
                break
        return out

    def answer(
        self,
        query: str,
        *,
        role: Optional[str] = None,
        request_id: Optional[str] = None,
        max_chunks: int = 4,
    ) -> Dict[str, Any]:
        trace_id = f"trace:w2-02:{request_id or uuid.uuid4()}"
        process = self.match_process(query)
        if not process:
            return {
                "status": "clarify",
                "answer_text_fa": "برای راهنمای مرحله‌ای بگویید کدام فرآیند مدنظرتان است (مثلاً مناقصه دو مرحله‌ای، ارزیابی کیفی، انواع معاملات، انعقاد پس از برنده، یا منابع پیشنهادی).",
                "steps": [],
                "prerequisites": [],
                "expected_result": "",
                "citations": [],
                "assumptions": [],
                "uncertainty": "no_process_match",
                "escalation_reason": None,
                "trace_id": trace_id,
                "knowledge_revision": self._dataset.get("updated_at"),
                "subgraph": None,
                "model_context": {"process_id": None, "chunk_ids": [], "omitted_full_corpus": True},
                "evidence": [],
                "trace": {
                    "request_id": request_id,
                    "tools_used": ["process_graph.match"],
                    "reason_code": "process_unmatched",
                    "local_index_used": False,
                },
            }

        chunks = self.related_chunks(process, limit=max_chunks)
        steps_out = []
        for st in process.get("steps") or []:
            if role and st.get("role_hint") and role not in st["role_hint"]:
                # still show step but mark role gate
                pass
            steps_out.append(
                {
                    "step_id": st["step_id"],
                    "label": st["label_ui"],
                    "instruction": st["instruction_fa"],
                    "prerequisite": st.get("prerequisite"),
                    "condition": st.get("condition"),
                    "role_hint": st.get("role_hint") or [],
                    "expected_after": st.get("expected_result"),
                    "uncertainty": st.get("uncertainty"),
                }
            )

        uncertain = [s for s in steps_out if s.get("uncertainty")]
        lines = [
            f"کاری که انجام دهید — {process['title_fa']}:",
            "",
        ]
        for i, st in enumerate(steps_out, start=1):
            lines.append(f"{i}) {st['label']}: {st['instruction']}")
            if st.get("prerequisite"):
                lines.append(f"   پیش‌نیاز: {st['prerequisite']}")
            if st.get("condition"):
                lines.append(f"   شرط: {st['condition']}")
            if st.get("expected_after"):
                lines.append(f"   نتیجهٔ مورد انتظار: {st['expected_after']}")
            if st.get("uncertainty"):
                lines.append(f"   نکته: {st['uncertainty']}")
            lines.append("")

        if uncertain:
            lines.append(
                "اگر نقش یا نسخهٔ نصب شما با این شواهد یکی نیست، یک سؤال مشخص بپرسید یا با شناسهٔ trace به پشتیبانی مراجعه کنید."
            )

        citations = []
        evidence = []
        for eid in process.get("evidence_ids") or []:
            citations.append(
                {
                    "evidence_id": eid,
                    "label": process["title_fa"],
                    "open_uri": f"graph://{process['process_id']}/{eid}",
                }
            )
            evidence.append(
                {
                    "evidence_id": eid,
                    "tenant_scope": "fixture:synthetic-canary",
                    "product_version": self._dataset.get("product_version"),
                    "role_scope": process.get("role_scope") or [],
                    "page_route": process.get("page_route"),
                    "source_path": (process.get("source_refs") or ["graph"])[0],
                    "source_revision": f"process-graphs-v0@{self._dataset.get('updated_at')}",
                    "extraction_method": "guide_fixture",
                    "reviewer_status": "approved",
                    "updated_at": f"{self._dataset.get('updated_at')}T00:00:00Z",
                    "confidence": 0.85,
                    "snippet": process["title_fa"],
                    "open": {
                        "kind": "guide",
                        "uri": f"graph://{process['process_id']}/{eid}",
                        "label": process["title_fa"],
                    },
                }
            )

        subgraph = {
            "process_id": process["process_id"],
            "title_fa": process["title_fa"],
            "module": process.get("module"),
            "page_route": process.get("page_route"),
            "role_scope": process.get("role_scope"),
            "prerequisites_global": process.get("prerequisites_global") or [],
            "nodes": [
                {
                    "id": s["step_id"],
                    "kind": "step",
                    "label": s["label"],
                    "condition": s.get("condition"),
                    "role_hint": s.get("role_hint"),
                }
                for s in steps_out
            ],
            "edges": [
                {"from": steps_out[i]["step_id"], "to": steps_out[i + 1]["step_id"], "kind": "next"}
                for i in range(len(steps_out) - 1)
            ],
        }

        model_context = {
            "process_id": process["process_id"],
            "step_count": len(steps_out),
            "chunk_ids": [c["chunk_id"] for c in chunks],
            "chunks": chunks,
            "omitted_full_corpus": True,
            "note": "Only this subgraph + capped related chunks should be sent to any LLM.",
        }

        status = "answered"
        if uncertain and len(uncertain) == len(steps_out):
            status = "clarify"

        return {
            "status": status,
            "answer_text_fa": "\n".join(lines).strip(),
            "steps": [
                {
                    "label": s["label"],
                    "instruction": s["instruction"],
                    "expected_after": s.get("expected_after"),
                    "prerequisite": s.get("prerequisite"),
                    "condition": s.get("condition"),
                }
                for s in steps_out
            ],
            "prerequisites": process.get("prerequisites_global") or [],
            "expected_result": steps_out[-1]["expected_after"] if steps_out else "",
            "citations": citations,
            "assumptions": [
                "پاسخ فقط از زیرگراف فرآیند و قطعه‌های مرتبط ساخته شده است.",
                "ایندکس کامل code2guide/Hub به مدل داده نشده است.",
            ],
            "uncertainty": (
                "؛ ".join(s["uncertainty"] for s in uncertain if s.get("uncertainty"))
                or None
            ),
            "escalation_reason": None,
            "trace_id": trace_id,
            "knowledge_revision": f"process-graphs-v0@{self._dataset.get('updated_at')}",
            "subgraph": subgraph,
            "model_context": model_context,
            "evidence": evidence,
            "trace": {
                "request_id": request_id,
                "tools_used": ["process_graph.match", "process_graph.related_chunks"],
                "reason_code": "process_graph_route",
                "process_id": process["process_id"],
                "chunk_count": len(chunks),
                "local_index_used": False,
                "hub_graph_used": False,
            },
        }
