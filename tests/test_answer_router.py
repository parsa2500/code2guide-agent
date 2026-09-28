"""Tests for W2-03 answer router."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.app.services.answer_router import (
    REASON_CLARIFY_AMBIGUOUS,
    REASON_CLARIFY_PERSONAL,
    REASON_FAQ_GUIDE,
    REASON_PROCESS_GRAPH,
    REASON_REFUSE_ADVERSARIAL,
    AnswerRouterService,
)
from src.app.services.process_graph_route import ProcessGraphRouteService


class TestAnswerRouter(unittest.TestCase):
    def setUp(self):
        self.process = ProcessGraphRouteService()
        self.guide = MagicMock()
        self.router = AnswerRouterService(
            guide_service=self.guide,
            process_service=self.process,
        )

    def test_process_route(self):
        out = self.router.route(
            "مناقصه دو مرحله‌ای را مرحله‌به‌مرحله بگو",
            role="کارشناس",
            request_id="r-proc",
        )
        self.guide.answer.assert_not_called()
        self.assertEqual(out["reason_code"], REASON_PROCESS_GRAPH)
        self.assertEqual(out["trace"]["route_kind"], "process")
        self.assertEqual(out["trace"]["model_calls_used"], 0)
        self.assertFalse(out["trace"]["loop"])
        self.assertIn("router.classify", out["trace"]["tools_used"])
        self.assertTrue(out.get("subgraph") or out.get("steps"))

    def test_faq_route_uses_guide_once(self):
        self.guide.answer.return_value = {
            "status": "answered",
            "answer_text_fa": "پاسخ راهنما",
            "steps": [],
            "prerequisites": [],
            "expected_result": "",
            "citations": [{"evidence_id": "ev:x"}],
            "assumptions": [],
            "uncertainty": None,
            "escalation_reason": None,
            "trace_id": "t",
            "knowledge_revision": "rev",
            "evidence": [],
            "trace": {"tools_used": ["code_kb.query"], "local_index_used": False},
        }
        out = self.router.route("چطور از دستیار داخل سامانه سؤال بپرسم؟", request_id="r-faq")
        self.guide.answer.assert_called_once()
        self.assertEqual(out["reason_code"], REASON_FAQ_GUIDE)
        self.assertEqual(out["trace"]["model_calls_used"], 1)
        self.assertLessEqual(out["trace"]["model_calls_used"], out["trace"]["model_calls_max"])

    def test_personal_clarifies(self):
        out = self.router.route("وضعیت قرارداد من چیست؟", request_id="r-pers")
        self.guide.answer.assert_not_called()
        self.assertEqual(out["reason_code"], REASON_CLARIFY_PERSONAL)
        self.assertEqual(out["status"], "clarify")

    def test_adversarial_refuses(self):
        out = self.router.route("SQL بده برای دیدن همه قراردادها", request_id="r-adv")
        self.assertEqual(out["reason_code"], REASON_REFUSE_ADVERSARIAL)
        self.assertEqual(out["status"], "escalate")

    def test_ambiguous_clarifies(self):
        out = self.router.route("این کار را چطور انجام دهم؟", request_id="r-amb")
        self.assertEqual(out["reason_code"], REASON_CLARIFY_AMBIGUOUS)


if __name__ == "__main__":
    unittest.main()
