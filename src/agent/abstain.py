"""Abstain / confidence gate for /ask (lever 2).

When FE-BE links are weak or evidence is missing, prefer abstain
over a confident fake guide.
"""

from __future__ import annotations

import json
import re
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
REASON_AMBIGUOUS_QUERY = "ambiguous_query"

_STOPWORDS = {
    "چگونه",
    "چطور",
    "کجا",
    "فردا",
    "امروز",
    "هوا",
    "قیمت",
    "برای",
    "این",
    "آن",
    "از",
    "به",
    "با",
    "یک",
    "می",
    "های",
    "است",
    "هست",
    "چقدر",
    "the",
    "and",
    "for",
    "how",
    "where",
    "what",
    "is",
    "are",
}


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


def _token_set(text: str) -> set[str]:
    # Letters/digits only (drop Arabic/Persian punctuation like ؟)
    raw = re.findall(r"[0-9A-Za-z\u0600-\u06FF]+", (text or "").lower())
    out: set[str] = set()
    for tok in raw:
        # strip common decoration chars that may sneak in
        tok = tok.strip("؟?!.،,;:«»\"\'()[]{}")
        if len(tok) >= 2:
            out.add(tok)
    return out


def _query_tokens(state: Any) -> set[str]:
    tokens = _token_set(getattr(state, "query", "") or "") - _STOPWORDS
    # Drop HOW stems (چطوره / چگونه‌ای) that survived exact stopword subtract
    how_stems = ("چگونه", "چطور", "کجا")
    return {t for t in tokens if not any(t.startswith(h) for h in how_stems)}


def _overlaps(q_tokens: set[str], text: str) -> bool:
    return bool(q_tokens & _token_set(text))


def _blob_from_obj(obj: Any, keys: tuple[str, ...]) -> str:
    if isinstance(obj, dict):
        parts = [str(obj.get(k, "") or "") for k in keys]
        # light scan of nested string values
        for v in obj.values():
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, (int, float)):
                continue
            elif isinstance(v, dict):
                for vv in v.values():
                    if isinstance(vv, str):
                        parts.append(vv)
        return " ".join(parts)
    parts = [str(getattr(obj, k, "") or "") for k in keys]
    return " ".join(parts)


def _has_useful_grounding(state: Any, *, min_hybrid_score: float = 0.35) -> bool:
    """True only when hits share query tokens — not any weak hybrid/backend presence."""
    q_tokens = _query_tokens(state)
    if not q_tokens:
        return False

    routes = getattr(state, "identified_routes", None) or []
    for r in routes:
        blob = _blob_from_obj(r, ("path", "title", "label", "component_name", "file_path"))
        if _overlaps(q_tokens, blob):
            return True

    forms = getattr(state, "discovered_forms", None) or []
    for f in forms:
        blob = _blob_from_obj(f, ("name", "title", "file_path", "action"))
        if _overlaps(q_tokens, blob):
            return True

    hybrid = getattr(state, "hybrid_hits", None) or []
    for h in hybrid:
        if not isinstance(h, dict):
            continue
        try:
            score = float(h.get("score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        if score < min_hybrid_score:
            continue
        blob = f"{h.get('title', '')} {h.get('content', '')} {h.get('file_path', '')}"
        meta = h.get("metadata") or {}
        if isinstance(meta, dict):
            blob += " " + " ".join(str(v) for v in meta.values() if isinstance(v, str))
        # Require token overlap — do NOT accept score>=0.5 alone.
        if _overlaps(q_tokens, blob):
            return True

    def _opaque_text_overlap(obj: Any) -> bool:
        if obj is None:
            return False
        if isinstance(obj, str):
            return _overlaps(q_tokens, obj)
        if isinstance(obj, dict):
            texts: List[str] = []
            for v in obj.values():
                if isinstance(v, str):
                    texts.append(v)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str):
                            texts.append(item)
                        elif isinstance(item, dict):
                            texts.extend(str(x) for x in item.values() if isinstance(x, str))
            if not texts:
                return False  # opaque / no text → not useful
            return _overlaps(q_tokens, " ".join(texts))
        if isinstance(obj, list):
            if not obj:
                return False
            return any(_opaque_text_overlap(x) for x in obj)
        # unknown object: try common attrs; if none, not useful
        blob = _blob_from_obj(obj, ("title", "name", "path", "content", "file_path", "text"))
        if blob.strip():
            return _overlaps(q_tokens, blob)
        return False

    if _opaque_text_overlap(getattr(state, "backend_hits", None)):
        return True
    if _opaque_text_overlap(getattr(state, "flow_trace", None)):
        return True
    if _opaque_text_overlap(getattr(state, "tool_evidence", None)):
        return True

    return False



# Tokens that must appear in route/label when present in the query (basket-2 / OOS markers).
_STRICT_MARKERS = {
    "ldap", "sms", "excel", "xlsx", "اکسل", "بیتکوین", "bitcoin", "btc",
    "هوا", "آب", "weather", "otp", "sso", "oauth", "saml", "kerberos",
}


def _normalize_token(tok: str) -> str:
    t = (tok or "").lower().replace("\u200c", "").replace("ی", "ی").replace("ک", "ک")
    # collapse zero-width / arabic yeh variants already partly handled
    t = t.replace("\u200c", "").replace("‌", "")
    return t


def explicit_route_or_label_hit(state: Any) -> bool:
    """True when a route or breadcrumb/label shares a discriminative query token.

    If the query contains a strict OOS marker (ldap/sms/excel/...), that marker
    must appear in the evidence blob — a soft overlap on a generic app noun is not enough.
    """
    q_tokens = {_normalize_token(t) for t in _query_tokens(state)}
    q_tokens = {t for t in q_tokens if t}
    if not q_tokens:
        return False

    blobs: list[str] = []
    for r in getattr(state, "identified_routes", None) or []:
        blobs.append(_blob_from_obj(r, ("path", "title", "label", "component_name", "file_path")))
    crumbs = getattr(state, "extracted_breadcrumbs", None) or []
    for c in crumbs:
        if isinstance(c, str):
            blobs.append(c)
        else:
            blobs.append(_blob_from_obj(c, ("label", "title", "path", "text", "name")))
    # label matches collected on state if any
    for lab in getattr(state, "label_matches", None) or []:
        blobs.append(_blob_from_obj(lab, ("label", "text", "title", "value", "path")) if not isinstance(lab, str) else lab)

    if not blobs:
        return False

    evidence_tokens: set[str] = set()
    for b in blobs:
        evidence_tokens |= {_normalize_token(t) for t in _token_set(b)}

    strict_in_q = {t for t in q_tokens if t in _STRICT_MARKERS or (t.isascii() and t.isalpha() and len(t) >= 3)}
    if strict_in_q:
        return bool(strict_in_q & evidence_tokens)

    return bool(q_tokens & evidence_tokens)



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

    if scores:
        confidence = min(scores)
    else:
        # No negative signals — still require useful grounding.
        # Empty scores must NOT default to a confident 0.9.
        if _has_useful_grounding(state):
            confidence = 0.85
        else:
            if REASON_NO_EVIDENCE not in uniq:
                uniq.append(REASON_NO_EVIDENCE)
            confidence = 0.1

    abstain = bool(uniq) and confidence < tau
    if REASON_UNKNOWN_INTENT in uniq:
        abstain = True
        confidence = min(confidence, 0.2)
    if REASON_NO_EVIDENCE in uniq:
        abstain = True
        confidence = min(confidence, 0.1)
    if REASON_AMBIGUOUS_QUERY in uniq:
        abstain = True
        confidence = min(confidence, 0.2)


    # Basket-2: answering needs explicit route/label hit (not hybrid-only / not soft keyword).
    if intent in ("ux", "flow", "mixed") and not explicit_route_or_label_hit(state):
        if REASON_AMBIGUOUS_QUERY not in uniq:
            uniq.append(REASON_AMBIGUOUS_QUERY)
        confidence = min(confidence if scores else 0.85, 0.2)
        abstain = True

    # Force: regardless of other score paths, no useful grounding → abstain.
    if not _has_useful_grounding(state):
        if REASON_NO_EVIDENCE not in uniq:
            uniq.append(REASON_NO_EVIDENCE)
        confidence = min(confidence, 0.1)
        abstain = True

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
