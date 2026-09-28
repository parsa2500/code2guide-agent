"""Unit tests for W1-04 my-kb guide spike (no live Hub required)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.app.services.mykb_guide_spike import MyKbGuideSpikeService
from src.integrations.code_kb_client import CodeKbError


class TestMyKbGuideSpike(unittest.TestCase):
    def test_answered_maps_hub_packet_without_local_index(self):
        client = MagicMock()
        client.query.return_value = {
            "result": {
                "status": "ok",
                "queryId": "q-test-1",
                "revisionId": "rev:fixture-abc",
                "answers": [
                    {
                        "kind": "answer",
                        "text": "برای برگزاری مناقصه دو مرحله‌ای، در انتخاب گردش کار گزینهٔ ارزیابی فنی را فعال کنید.",
                        "evidenceIds": ["citation:ee04c092"],
                        "confidence": {"score": 0.7},
                    }
                ],
            }
        }
        service = MyKbGuideSpikeService(client=client)
        out = service.answer(
            "مناقصه دو مرحله‌ای چیست؟",
            request_id="w1-04-unit",
        )

        client.query.assert_called_once()
        kwargs = client.query.call_args
        self.assertEqual(kwargs.args[0], "contracts-guides")
        self.assertEqual(kwargs.kwargs.get("brain") or kwargs[1].get("brain"), "guide")

        self.assertEqual(out["status"], "answered")
        self.assertIn("مناقصه", out["answer_text_fa"])
        self.assertTrue(out["citations"])
        self.assertTrue(out["evidence"])
        self.assertEqual(out["knowledge_revision"], "rev:fixture-abc")
        self.assertFalse(out["trace"]["local_index_used"])
        self.assertEqual(out["trace"]["tools_used"], ["code_kb.query"])
        self.assertNotIn("HybridIndexer", str(out))
        self.assertNotIn("index_workspace", str(out))

    def test_hub_down_escalates(self):
        client = MagicMock()
        client.query.side_effect = CodeKbError("down", status=503)
        service = MyKbGuideSpikeService(client=client)
        out = service.answer("سؤال تست", request_id="down")
        self.assertEqual(out["status"], "escalate")
        self.assertEqual(out["escalation_reason"], "code_kb_unavailable")
        self.assertFalse(out["trace"]["local_index_used"])

    def test_empty_answers_clarify(self):
        client = MagicMock()
        client.query.return_value = {
            "result": {
                "status": "partial",
                "revisionId": "rev:empty",
                "answers": [],
            }
        }
        service = MyKbGuideSpikeService(client=client)
        out = service.answer("سؤال بدون شاهد")
        self.assertEqual(out["status"], "clarify")
        self.assertFalse(out["trace"]["local_index_used"])


if __name__ == "__main__":
    unittest.main()
