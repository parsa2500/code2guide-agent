"""Tests for abstain / confidence gate (اهرم ۲)."""

from src.agent.abstain import (
    DEFAULT_TAU,
    evaluate_abstain,
    apply_abstain_to_state,
    _has_useful_grounding,
    REASON_UNKNOWN_INTENT,
    REASON_NO_EVIDENCE,
    REASON_WEAK_FE_BE,
)
from src.agent.planner import QueryPlanner
from src.agent.state import AgentState


def _state(**kwargs):
    s = AgentState(query="چگونه ثبت کنم؟", workspace_path=".")
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def test_unknown_intent_abstains():
    s = _state(query_plan={"intent": "unknown"})
    d = evaluate_abstain(s)
    assert d.abstain is True
    assert REASON_UNKNOWN_INTENT in d.reason_codes
    assert d.confidence < DEFAULT_TAU


def test_no_evidence_abstains():
    s = _state(query_plan={"intent": "ux"})
    d = evaluate_abstain(s)
    assert d.abstain is True
    assert REASON_NO_EVIDENCE in d.reason_codes


def test_strong_evidence_no_abstain():
    # Routes/forms must overlap query tokens (ثبت) — bare presence is not enough.
    s = _state(
        query="چگونه مناقصه ثبت کنم؟",
        query_plan={"intent": "ux"},
        identified_routes=[{"path": "/tenders/create", "title": "ثبت مناقصه"}],
        discovered_forms=[{"name": "tenderForm", "title": "فرم ثبت مناقصه"}],
        tool_evidence=[{"tool": "get_route", "title": "ثبت مناقصه", "path": "/tenders/create"}],
    )
    assert _has_useful_grounding(s) is True
    d = evaluate_abstain(s)
    assert d.abstain is False
    assert d.confidence >= DEFAULT_TAU


def test_weak_hybrid_score_without_overlap_abstains():
    s = _state(
        query="فردا هوا چطوره؟",
        query_plan={"intent": "ux"},
        hybrid_hits=[{"title": "Dashboard", "content": "settings panel", "score": 0.9}],
        backend_hits=[{"id": "x"}],
        flow_trace={"chains": []},
    )
    assert _has_useful_grounding(s) is False
    d = evaluate_abstain(s)
    assert d.abstain is True
    assert REASON_NO_EVIDENCE in d.reason_codes
    assert d.confidence <= 0.1


def test_weather_planner_unknown_then_abstain():
    plan = QueryPlanner().plan("فردا هوا چطوره؟")
    assert plan.intent == "unknown"
    s = _state(query="فردا هوا چطوره؟", query_plan=plan.model_dump())
    d = evaluate_abstain(s)
    assert d.abstain is True
    assert REASON_UNKNOWN_INTENT in d.reason_codes or REASON_NO_EVIDENCE in d.reason_codes


def test_force_no_grounding_even_when_scores_nonempty():
    """Weak signals filling scores must not bypass useful-grounding force."""
    s = _state(
        query="قیمت بیت‌کوین امروز چقدر است؟",
        query_plan={"intent": "ux"},  # wrongly classified
        identified_routes=[{"path": "/dashboard", "title": "Dashboard"}],
        hybrid_hits=[{"title": "Home", "score": 0.99}],
    )
    d = evaluate_abstain(s)
    assert d.abstain is True
    assert REASON_NO_EVIDENCE in d.reason_codes
    assert d.confidence <= 0.1


def test_weak_maps_to_via_store(tmp_path):
    from src.knowledge.store import GraphStore
    from src.knowledge.schema import EdgeType, GraphEdge, GraphNode, NodeType

    db = tmp_path / "g.db"
    store = GraphStore(str(tmp_path), db_path=db)
    store.upsert_nodes(
        [
            GraphNode(id="f1", node_type=NodeType.FORM_FIELD, title="a"),
            GraphNode(id="d1", node_type=NodeType.DTO, title="A"),
        ]
    )
    store.upsert_edges(
        [
            GraphEdge(
                id="e1",
                edge_type=EdgeType.MAPS_TO,
                source_id="f1",
                target_id="d1",
                payload={"confidence": 0.4},
            )
        ]
    )
    s = _state(
        query="چگونه مناقصه ثبت کنم؟",
        query_plan={"intent": "flow"},
        identified_routes=[{"path": "/tenders/create", "title": "ثبت مناقصه"}],
        discovered_forms=[{"name": "f", "title": "فرم ثبت"}],
        flow_trace={"chains": [{"title": "ثبت مناقصه"}]},
        tool_evidence=[{"tool": "trace_flow", "title": "ثبت مناقصه"}],
    )
    d = evaluate_abstain(s, store=store)
    assert d.abstain is True
    assert REASON_WEAK_FE_BE in d.reason_codes
    store.close()


def test_apply_rewrites_guide():
    s = _state(query_plan={"intent": "unknown"}, final_persian_guide="گام ۱: کلیک کن")
    d = apply_abstain_to_state(s)
    assert d.abstain is True
    assert s.abstain is True
    assert "گام ۱" not in (s.final_persian_guide or "")
    assert s.confidence <= 0.2


def test_tau_unchanged():
    assert DEFAULT_TAU == 0.75
