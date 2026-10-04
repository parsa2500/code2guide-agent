"""W3-03: per-turn telemetry without contract text.

Records trace metadata (pseudonym, versions, latency split, tokens, estimated
cost, allowed response/feedback). The user message and answer body are not
fields of the record.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any, Dict, Optional

from src.app.services.persian_answer_template import PROMPT_VERSION

# USD per 1M tokens. Paid list prices from blueprint docs/costing.md.
# Cache tokens are counted but not priced: costing.md has no cache rate.
_LIST_RATES_USD_PER_MILLION = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "openrouter/free": (0.0, 0.0),
    "none": (0.0, 0.0),
    "hub-unspecified": (0.0, 0.0),
}

ALLOWED_RATINGS = ("up", "down")
ALLOWED_FEEDBACK_REASONS = (
    "wrong_ui",
    "role_or_permission",
    "process",
    "document",
    "persian",
    "latency",
    "other",
)

_PSEUDONYM_SALT = "dargah-w3-03-v0"


def tenant_pseudonym(tenant_id: Optional[str]) -> str:
    """Stable short id. The raw tenant id is not returned."""
    import hashlib
    import hmac

    raw = (tenant_id or "").strip()
    if not raw:
        return "tn_unknown"
    digest = hmac.new(
        _PSEUDONYM_SALT.encode("utf-8"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return "tn_" + digest[:16]


def estimate_cost_usd(model_version: str, tokens: Dict[str, int]) -> Dict[str, Any]:
    rates = _LIST_RATES_USD_PER_MILLION.get(model_version or "")
    prompt = int(tokens.get("input") or 0)
    completion = int(tokens.get("output") or 0)
    cache = int(tokens.get("cache") or 0)
    if rates is None:
        return {
            "usd": 0.0,
            "basis": "unpriced",
            "cache_tokens_unpriced": cache,
        }
    usd = (prompt * rates[0] + completion * rates[1]) / 1_000_000
    return {
        "usd": round(usd, 8),
        "basis": "list_price_ex_cache",
        "cache_tokens_unpriced": cache,
    }


def build_turn_record(
    *,
    trace_id: str,
    tenant_id: Optional[str],
    question_type: str,
    document_version: Optional[str],
    model_version: str,
    retrieval_ms: int,
    model_ms: int,
    latency_source: str,
    tokens: Dict[str, int],
    response_status: str,
    response_chars: int,
    feedback_allowed: bool,
) -> Dict[str, Any]:
    token_counts = {
        "input": int(tokens.get("input") or 0),
        "output": int(tokens.get("output") or 0),
        "cache": int(tokens.get("cache") or 0),
    }
    answered = response_status in ("answered", "clarify")
    return {
        "trace_id": trace_id,
        "tenant_pseudonym": tenant_pseudonym(tenant_id),
        "question_type": question_type,
        "document_version": document_version,
        "model_version": model_version or "none",
        "prompt_version": PROMPT_VERSION,
        "latency_ms": {
            "retrieval": int(retrieval_ms),
            "model": int(model_ms),
        },
        "latency_source": latency_source,
        "tokens": token_counts,
        "estimated_cost": estimate_cost_usd(model_version or "none", token_counts),
        "response": {
            "status": response_status,
            "allowed": answered,
            "chars": int(response_chars),
        },
        "feedback": {
            "allowed": bool(feedback_allowed),
            "rating": None,
            "reason_code": None,
            "feedback_id": None,
            "explanation_stored": False,
        },
        "stored_contract_text": False,
    }


class TurnTelemetryStore:
    """Process-local store. Not a cross-tenant knowledge base."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: Dict[str, Dict[str, Any]] = {}

    def record(self, row: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._rows[row["trace_id"]] = row
            return row

    def get(self, trace_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._rows.get(trace_id)
            return dict(row) if row else None

    def record_feedback(
        self,
        trace_id: str,
        rating: str,
        reason_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        if rating not in ALLOWED_RATINGS:
            raise ValueError("rating")
        if reason_code is not None and reason_code not in ALLOWED_FEEDBACK_REASONS:
            raise ValueError("reason_code")
        if rating == "down" and not reason_code:
            raise ValueError("reason_code")
        with self._lock:
            row = self._rows.get(trace_id)
            if row is None:
                raise KeyError(trace_id)
            feedback = row["feedback"]
            if not feedback.get("allowed"):
                raise ValueError("feedback_not_allowed")
            feedback_id = "fb:" + uuid.uuid4().hex[:12]
            feedback["rating"] = rating
            feedback["reason_code"] = reason_code
            feedback["feedback_id"] = feedback_id
            feedback["explanation_stored"] = False
            return dict(feedback)


_STORE = TurnTelemetryStore()


def get_turn_telemetry_store() -> TurnTelemetryStore:
    return _STORE
