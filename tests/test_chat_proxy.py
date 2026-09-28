"""Tests for W3-02 chat proxy."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock

from src.app.services.auth_context import build_from_main_session
from src.app.services.chat_proxy import ChatProxyService


class TestChatProxy(unittest.TestCase):
    def setUp(self):
        self.secret = "w3-02-test-secret"
        os.environ["AUTH_CONTEXT_SECRET"] = self.secret
        self.packet = build_from_main_session(
            support_id="tenant-1",
            user_id="user-1",
            post_id="post-1",
            role_labels=["کارشناس"],
            product_version="Contracts.Main@local-baseline-2026-09-27",
            secret=self.secret,
        )
        self.router = MagicMock()
        self.router.route.return_value = {
            "status": "answered",
            "answer_text_fa": "کاری که انجام دهید\n1) «فراخوان ها»: وارد شوید.",
            "trace_id": "trace:test",
            "reason_code": "process_graph_route",
            "escalation_reason": None,
            "trace": {"model_calls_used": 0, "tools_used": ["router.classify"]},
        }
        self.svc = ChatProxyService(router=self.router, timeout_seconds=5)

    def test_success_shape(self):
        out = self.svc.handle_turn(
            text="مناقصه دو مرحله‌ای را مرحله‌به‌مرحله بگو",
            auth_context=self.packet,
            session_id="sess-1",
            request_id="r1",
        )
        self.assertTrue(out["success"])
        self.assertIn("کاری که انجام دهید", out["response"])
        self.assertEqual(out["sessionId"], "sess-1")
        self.assertEqual(out["auth"]["tenant_id"], "tenant-1")
        self.router.route.assert_called_once()

    def test_forged_tenant_rejected(self):
        out = self.svc.handle_turn(
            text="hello",
            auth_context=self.packet,
            browser_claims={"tenant_id": "evil"},
            request_id="r2",
        )
        self.assertFalse(out["success"])
        self.assertEqual(out.get("error_code"), "forged_tenant")
        self.assertEqual(out.get("fallback"), "support")
        self.router.route.assert_not_called()

    def test_empty_text(self):
        out = self.svc.handle_turn(text="  ", auth_context=self.packet, request_id="r3")
        self.assertFalse(out["success"])
        self.assertIn("خالی", out["error"])


if __name__ == "__main__":
    unittest.main()
