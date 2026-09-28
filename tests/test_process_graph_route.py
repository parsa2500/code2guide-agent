"""Tests for W2-02 process graph route."""

from __future__ import annotations

import unittest

from src.app.services.process_graph_route import ProcessGraphRouteService


class TestProcessGraphRoute(unittest.TestCase):
    def setUp(self):
        self.svc = ProcessGraphRouteService()

    def test_two_stage_returns_steps_and_subgraph(self):
        out = self.svc.answer(
            "فرآیند مناقصه دو مرحله‌ای را مرحله‌به‌مرحله بگو",
            role="کارشناس",
            request_id="w2-02-unit",
        )
        self.assertEqual(out["status"], "answered")
        self.assertGreaterEqual(len(out["steps"]), 3)
        self.assertTrue(out["subgraph"])
        self.assertEqual(out["subgraph"]["process_id"], "proc:q01-two-stage-tender")
        self.assertTrue(out["model_context"]["omitted_full_corpus"])
        self.assertLessEqual(len(out["model_context"]["chunk_ids"]), 4)
        self.assertIn("process_graph.match", out["trace"]["tools_used"])
        self.assertFalse(out["trace"]["local_index_used"])
        # each step has prerequisite or expected
        for st in out["steps"]:
            self.assertTrue(st.get("label"))
            self.assertTrue(st.get("instruction"))

    def test_unmatched_clarifies(self):
        out = self.svc.answer("وضعیت آب‌وهوای تهران فردا چیست؟", request_id="nomatch")
        self.assertEqual(out["status"], "clarify")
        self.assertIsNone(out["subgraph"])

    def test_sources_process(self):
        out = self.svc.answer("منابع پیشنهادی مناقصه محدود را چطور اضافه کنم؟")
        self.assertEqual(out["subgraph"]["process_id"], "proc:q05-suggested-sources")
        self.assertTrue(out["prerequisites"])


if __name__ == "__main__":
    unittest.main()
