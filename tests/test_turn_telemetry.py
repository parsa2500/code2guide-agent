"""W3-03: telemetry records metadata and drops contract text."""

from __future__ import annotations

import json
import os
import unittest

from src.app.services.auth_context import build_from_main_session
from src.app.services.chat_proxy import ChatProxyService
from src.app.services.turn_telemetry import (
    TurnTelemetryStore,
    estimate_cost_usd,
    tenant_pseudonym,
)
from unittest.mock import MagicMock


CONTRACT = "متن قرارداد شماره ۱۲۳۴۵ مبلغ محرمانه"


class TestTurnTelemetry(unittest.TestCase):
    def setUp(self):
        self.secret = "w3-03-test-secret"
        os.environ["AUTH_CONTEXT_SECRET"] = self.secret
        self.packet = build_from_main_session(
            support_id="tenant-1",
            user_id="user-1",
            post_id="post-1",
            role_labels=["کارشناس"],
            product_version="Contracts.Main@local-baseline-2026-09-27",
            secret=self.secret,
        )
        self.store = TurnTelemetryStore()
        self.router = MagicMock()
        self.router.route.return_value = {
            "status": "answered",
            "answer_text_fa": "راهنما\n" + CONTRACT,
            "trace_id": "trace:w3-03",
            "reason_code": "process_graph_route",
            "knowledge_revision": "rev:fixture",
            "escalation_reason": None,
            "trace": {
                "route_kind": "process",
                "model_calls_used": 0,
                "model_version": "none",
                "prompt_version": "persian-template-v0",
                "latency_source": "local_retrieval",
                "latency_ms": {"retrieval": 12, "model": 0},
                "tokens": {"input": 1_000_000, "output": 0, "cache": 50},
                "tools_used": ["router.classify"],
            },
        }
        self.svc = ChatProxyService(router=self.router, timeout_seconds=5, store=self.store)

    def test_record_omits_contract_and_raw_tenant(self):
        out = self.svc.handle_turn(
            text="سؤال کاربر. " + CONTRACT,
            auth_context=self.packet,
            session_id="sess-1",
            request_id="r1",
        )
        row = self.store.get(out["trace_id"])
        self.assertIsNotNone(row)
        blob = json.dumps(row, ensure_ascii=False)
        self.assertNotIn(CONTRACT, blob)
        self.assertNotIn("tenant-1", blob)
        self.assertNotIn("user-1", blob)
        self.assertNotIn("سؤال کاربر", blob)
        self.assertEqual(row["tenant_pseudonym"], tenant_pseudonym("tenant-1"))
        self.assertTrue(row["tenant_pseudonym"].startswith("tn_"))
        self.assertEqual(row["question_type"], "process")
        self.assertEqual(row["document_version"], "rev:fixture")
        self.assertEqual(row["model_version"], "none")
        self.assertEqual(row["prompt_version"], "persian-template-v0")
        self.assertEqual(row["latency_ms"], {"retrieval": 12, "model": 0})
        self.assertEqual(row["tokens"], {"input": 1000000, "output": 0, "cache": 50})
        self.assertEqual(row["estimated_cost"]["usd"], 0.0)
        self.assertTrue(row["response"]["allowed"])
        self.assertGreater(row["response"]["chars"], 0)
        self.assertTrue(row["feedback"]["allowed"])
        self.assertFalse(row["stored_contract_text"])
        self.assertNotIn("tenant_pseudonym", out)
        self.assertNotIn("stored_contract_text", out)

    def test_feedback_stores_reason_not_explanation(self):
        out = self.svc.handle_turn(
            text="hello guide",
            auth_context=self.packet,
            request_id="r-fb",
        )
        feedback = self.store.record_feedback(out["trace_id"], "down", "persian")
        self.assertTrue(feedback["feedback_id"].startswith("fb:"))
        self.assertFalse(feedback["explanation_stored"])
        row = self.store.get(out["trace_id"])
        self.assertNotIn(CONTRACT, json.dumps(row, ensure_ascii=False))
        with self.assertRaises(ValueError):
            self.store.record_feedback(out["trace_id"], "down", "free_text_" + CONTRACT)

    def test_forged_tenant_has_no_pseudonym_of_claim(self):
        out = self.svc.handle_turn(
            text=CONTRACT,
            auth_context=self.packet,
            browser_claims={"tenant_id": "evil-tenant"},
            request_id="r-forge",
        )
        row = self.store.get(out["trace_id"])
        blob = json.dumps(row, ensure_ascii=False)
        self.assertEqual(row["question_type"], "forged_tenant")
        self.assertEqual(row["tenant_pseudonym"], "tn_unknown")
        self.assertNotIn(CONTRACT, blob)
        self.assertNotIn("evil-tenant", blob)
        self.assertFalse(row["feedback"]["allowed"])

    def test_gemini_list_price_ignores_cache(self):
        cost = estimate_cost_usd(
            "gemini-3.5-flash-lite",
            {"input": 1_000_000, "output": 0, "cache": 1_000_000},
        )
        self.assertEqual(cost["usd"], 0.3)
        self.assertEqual(cost["cache_tokens_unpriced"], 1_000_000)
        self.assertEqual(cost["basis"], "list_price_ex_cache")


if __name__ == "__main__":
    unittest.main()
