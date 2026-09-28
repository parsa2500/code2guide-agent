"""Tests for W2-04 Persian answer template."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.app.services.answer_router import AnswerRouterService
from src.app.services.persian_answer_template import HEADER, format_persian_answer
from src.app.services.process_graph_route import ProcessGraphRouteService


class TestPersianTemplate(unittest.TestCase):
    def test_answered_has_header_steps_and_trace(self):
        payload = {
            "status": "answered",
            "answer_text_fa": "متن خام",
            "steps": [
                {
                    "label": "فراخوان ها",
                    "instruction": "وارد فهرست شوید.",
                    "expected_after": "فهرست دیده می‌شود.",
                }
            ],
            "prerequisites": ["ورود به سامانه"],
            "expected_result": "فهرست باز است",
            "trace_id": "trace:demo",
            "uncertainty": None,
            "evidence": [{"role_scope": ["کارشناس"]}],
        }
        out = format_persian_answer(payload, role="کارشناس", product_version="v-test")
        text = out["answer_text_fa"]
        self.assertTrue(text.startswith(HEADER))
        self.assertIn("شرط نقش/نسخه", text)
        self.assertIn("«فراخوان ها»", text)
        self.assertIn("شناسهٔ پیگیری: trace:demo", text)
        self.assertEqual(out["template"]["name"], "persian_v0")

    def test_clarify_asks_one_question(self):
        out = format_persian_answer(
            {
                "status": "clarify",
                "answer_text_fa": "سؤال مبهم است. کدام فرآیند مدنظر است؟",
                "uncertainty": "ambiguous_query",
                "trace_id": "trace:c",
            }
        )
        self.assertTrue(out["answer_text_fa"].startswith(HEADER))
        self.assertTrue(out["clarify_question"].endswith("؟"))
        self.assertIn("شناسهٔ پیگیری", out["answer_text_fa"])

    def test_router_applies_template(self):
        guide = MagicMock()
        router = AnswerRouterService(
            guide_service=guide,
            process_service=ProcessGraphRouteService(),
        )
        out = router.route(
            "مناقصه دو مرحله‌ای را مرحله‌به‌مرحله بگو",
            role="کارشناس",
            request_id="w204",
        )
        self.assertTrue(out["answer_text_fa"].startswith(HEADER))
        self.assertIn("persian_template.format", out["trace"]["tools_used"])
        self.assertIn("شناسهٔ پیگیری", out["answer_text_fa"])


if __name__ == "__main__":
    unittest.main()
