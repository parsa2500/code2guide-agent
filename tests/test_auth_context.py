"""W3-01 auth context forgery rejection tests."""

from __future__ import annotations

import unittest

from src.app.services.auth_context import (
    AuthContextError,
    build_from_main_session,
    sign_context,
    verify_context,
)


class TestAuthContext(unittest.TestCase):
    def setUp(self):
        self.secret = "test-auth-context-secret-w3-01"
        self.packet = build_from_main_session(
            support_id="tenant-support-1",
            user_id="user-aaa",
            post_id="post-bbb",
            role_labels=["کارشناس"],
            product_version="Contracts.Main@local-baseline-2026-09-27",
            page_route="/ChatBot",
            display_name="Test User",
            secret=self.secret,
            ttl_seconds=300,
        )

    def test_valid_packet_accepts(self):
        claims = verify_context(self.packet, secret=self.secret)
        self.assertEqual(claims["tenant_id"], "tenant-support-1")
        self.assertEqual(claims["user_id"], "user-aaa")

    def test_forged_tenant_rejected(self):
        with self.assertRaises(AuthContextError) as ctx:
            verify_context(
                self.packet,
                browser_claims={"tenant_id": "evil-tenant"},
                secret=self.secret,
            )
        self.assertEqual(ctx.exception.code, "forged_tenant")

    def test_forged_user_rejected(self):
        with self.assertRaises(AuthContextError) as ctx:
            verify_context(
                self.packet,
                browser_claims={"user_id": "evil-user"},
                secret=self.secret,
            )
        self.assertEqual(ctx.exception.code, "forged_user")

    def test_tampered_signature_rejected(self):
        bad = dict(self.packet)
        bad["sig"] = "0" * 64
        with self.assertRaises(AuthContextError) as ctx:
            verify_context(bad, secret=self.secret)
        self.assertEqual(ctx.exception.code, "bad_signature")

    def test_matching_browser_ids_ok(self):
        claims = verify_context(
            self.packet,
            browser_claims={
                "tenant_id": "tenant-support-1",
                "user_id": "user-aaa",
                "post_id": "post-bbb",
            },
            secret=self.secret,
        )
        self.assertEqual(claims["user_id"], "user-aaa")

    def test_sign_roundtrip_roles(self):
        packet = sign_context(
            {
                "tenant_id": "t",
                "user_id": "u",
                "post_id": "p",
                "role_labels": ["مدیر", "پشتیبانی"],
                "product_version": "v",
                "page_route": "/ChatBot",
            },
            secret=self.secret,
            now=1_700_000_000,
        )
        claims = verify_context(packet, secret=self.secret, now=1_700_000_010)
        self.assertEqual(claims["role_labels"], ["مدیر", "پشتیبانی"])


if __name__ == "__main__":
    unittest.main()
