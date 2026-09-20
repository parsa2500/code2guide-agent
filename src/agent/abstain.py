"""Abstain / confidence gate for /ask (lever 2).

When FE-BE links are weak or evidence is missing, prefer abstain
over a confident fake guide.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_TAU = 0.75

ABSTAIN_MESSAGE_FA = (
    "نمی‌دانم / اطمینان کافی نیست. "
    "شاهد کافی یا پیوند قابل‌اعتماد FE↔BE برای این پرسش پیدا نشد."
)

REASON_UNKNOWN_INTENT = "unknown_intent"
REASON_WEAK_FE_BE = "weak_fe_be_link"
REASON_NO_EVIDENCE = "no_evidence"
REASON_NO_ROUTE = "no_route"


@dataclass
class AbstainDecision:
    confidence: float
    abstain: bool
    reason_codes: List[str] = field(default_factory=list)
    tau: float = DEFAULT_TAU

    def as_dict(self) -> Dict[str, Any]:
        return {
            "confidence": round(float(self.confidence), 4),
            "abstain": bool(self.abstain),
            "reason_codes": list(self.reason_codes),
            "tau": float(self.tau),
        }


def _intent(state: Any) -> str:
    plan = getattr(state, "query_plan", None) or {}
    if isinstance(plan, dict):
        return str(plan.get("intent") or "ux")
    return "ux"


def _maps_to_confidences(store: Any) -> List[float]:
    if store is None:
        return []
    conn = getattr(store, "_conn", None)
    if conn is None:
        return []
    try:
        cur = conn.execute(
            "SELECT payload FROM edges WHERE edge_type = ?",
            ("maps_to",),
        )
    except Exception:
        return []
    out: List[float] = []
    for (payload,) in cur.fetchall():
        data: Any = payload
        if isinstance(payload, (bytes, str)):
            try:
                data = json.loads(payload)
            except Exception:
                continue
        if not isinstance(data, dict):
            continue
        conf = data.get("confidence")
        if conf is None:
            continue
        try:
            out.append(float(conf))
        except (TypeError, ValueError):
            continue
    return out


def evaluate_abstain(
    state: Any,
    *,
    store: Any = None,
    tau: float = DEFAULT_TAU,
) -> AbstainDecision:
    reasons: List[str] = []
    scores: List[float] = []

    intent = _intent(state)
    if intent == "unknown":
        reasons.append(REASON_UNKNOWN_INTENT)
        scores.append(0.2)

    has_routes = bool(getattr(state, "identified_routes", None))
    has_forms = bool(getattr(state, "discovered_forms", None))
    has_hybrid = bool(getattr(state, "hybrid_hits", None))
    has_backend = bool(getattr(state, "backend_hits", None))
    has_flow = bool(getattr(state, "flow_trace", None))
    has_evidence = bool(getattr(state, "tool_evidence", None))

    if not any((has_routes, has_forms, has_hybrid, has_backend, has_flow, has_evidence)):
        reasons.append(REASON_NO_EVIDENCE)
        scores.append(0.1)

    if not has_routes and intent in ("ux", "flow", "mixed") and not has_forms:
        reasons.append(REASON_NO_ROUTE)
        scores.append(0.25)

    maps_conf = _maps_to_confidences(store)
    if maps_conf:
        weakest = min(maps_conf)
        scores.append(weakest)
        if weakest < tau:
            reasons.append(REASON_WEAK_FE_BE)
    elif has_flow:
        flow = getattr(state, "flow_trace", None) or {}
        field_maps: List[Any] = []
        if isinstance(flow, dict):
            chains = flow.get("chains") or []
            if isinstance(chains, list):
                for ch in chains:
                    if isinstance(ch, dict):
                        field_maps.extend(ch.get("field_mappings") or [])
            field_maps.extend(flow.get("field_mappings") or [])
        if has_forms and not field_maps:
            reasons.append(REASON_WEAK_FE_BE)
            scores.append(0.4)

    seen = set()
    uniq: List[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            uniq.append(r)

    confidence = min(scores) if scores else 0.9
    abstain = bool(uniq) and confidence < tau
    if REASON_UNKNOWN_INTENT in uniq:
        abstain = True
        confidence = min(confidence, 0.2)
    if REASON_NO_EVIDENCE in uniq:
        abstain = True
        confidence = min(confidence, 0.1)

    return AbstainDecision(
        confidence=confidence,
        abstain=abstain,
        reason_codes=uniq,
        tau=tau,
    )


def apply_abstain_to_state(
    state: Any,
    *,
    store: Any = None,
    tau: float = DEFAULT_TAU,
) -> AbstainDecision:
    decision = evaluate_abstain(state, store=store, tau=tau)
    state.confidence = decision.confidence
    state.abstain = decision.abstain
    state.reason_codes = list(decision.reason_codes)
    if decision.abstain:
        guide = ABSTAIN_MESSAGE_FA
        audience = getattr(state, "audience", "technical")
        if audience == "technical" and decision.reason_codes:
            codes = ", ".join(decision.reason_codes)
            guide = f"{guide}\n\n(reasons: `{codes}`)"
        # AgentState field name on disk
        state.final_persian_guide = guide
    return decision
