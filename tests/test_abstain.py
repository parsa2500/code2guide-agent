"""Tests for abstain / confidence gate (اهرم ۲)."""

from src.agent.abstain import (
    DEFAULT_TAU,
    evaluate_abstain,
    apply_abstain_to_state,
    REASON_UNKNOWN_INTENT,
    REASON_NO_EVIDENCE,
    REASON_WEAK_FE_BE,
)
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
    s = _state(
        query_plan={"intent": "ux"},
        identified_routes=[{"path": "/x"}],
        discovered_forms=[{"name": "f"}],
        tool_evidence=[{"tool": "get_route"}],
    )
    d = evaluate_abstain(s)
    assert d.abstain is False
    assert d.confidence >= DEFAULT_TAU


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
        query_plan={"intent": "flow"},
        identified_routes=[{"path": "/x"}],
        discovered_forms=[{"name": "f"}],
        flow_trace={"chains": []},
        tool_evidence=[{"tool": "trace_flow"}],
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
