"""W3-01: signed auth context — session wins; forged browser tenant/user rejected."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any, Dict, List, Optional, Sequence


class AuthContextError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _secret() -> str:
    secret = os.getenv("AUTH_CONTEXT_SECRET") or os.getenv("CODE_KB_TOKEN")
    if not secret:
        raise AuthContextError(
            "secret_missing",
            "AUTH_CONTEXT_SECRET is not configured",
        )
    return secret


def canonical_string(
    claims: Dict[str, Any],
    iat: int,
    exp: int,
) -> str:
    roles = ",".join(claims.get("role_labels") or [])
    return "|".join(
        [
            str(claims.get("tenant_id") or ""),
            str(claims.get("user_id") or ""),
            str(claims.get("post_id") or ""),
            roles,
            str(claims.get("product_version") or ""),
            str(claims.get("page_route") or ""),
            str(iat),
            str(exp),
        ]
    )


def sign_context(
    claims: Dict[str, Any],
    *,
    secret: Optional[str] = None,
    ttl_seconds: int = 300,
    kid: str = "local-dev",
    now: Optional[int] = None,
) -> Dict[str, Any]:
    required = (
        "tenant_id",
        "user_id",
        "post_id",
        "role_labels",
        "product_version",
        "page_route",
    )
    for key in required:
        if key not in claims or claims[key] in (None, "", []):
            raise AuthContextError("invalid_claims", f"missing claim: {key}")
    if not isinstance(claims["role_labels"], (list, tuple)):
        raise AuthContextError("invalid_claims", "role_labels must be a list")

    iat = int(now if now is not None else time.time())
    exp = iat + int(ttl_seconds)
    clean = {
        "tenant_id": str(claims["tenant_id"]),
        "user_id": str(claims["user_id"]),
        "post_id": str(claims["post_id"]),
        "role_labels": [str(r) for r in claims["role_labels"]],
        "product_version": str(claims["product_version"]),
        "page_route": str(claims["page_route"]),
    }
    if claims.get("display_name"):
        clean["display_name"] = str(claims["display_name"])

    key = (secret or _secret()).encode("utf-8")
    digest = hmac.new(
        key,
        canonical_string(clean, iat, exp).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "alg": "HS256",
        "kid": kid,
        "iat": iat,
        "exp": exp,
        "claims": clean,
        "sig": digest,
    }


def verify_signature(
    packet: Dict[str, Any],
    *,
    secret: Optional[str] = None,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    if not packet or packet.get("alg") != "HS256":
        raise AuthContextError("invalid_packet", "alg must be HS256")
    claims = packet.get("claims") or {}
    try:
        iat = int(packet["iat"])
        exp = int(packet["exp"])
    except Exception as exc:
        raise AuthContextError("invalid_packet", "iat/exp required") from exc
    ts = int(now if now is not None else time.time())
    if ts > exp:
        raise AuthContextError("expired", "auth context expired")
    if iat > ts + 30:
        raise AuthContextError("invalid_packet", "iat in the future")

    key = (secret or _secret()).encode("utf-8")
    expected = hmac.new(
        key,
        canonical_string(claims, iat, exp).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    got = str(packet.get("sig") or "")
    if not hmac.compare_digest(expected, got):
        raise AuthContextError("bad_signature", "HMAC mismatch")
    return dict(claims)


def reconcile_browser_claims(
    session_claims: Dict[str, Any],
    browser_claims: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Session claims are authoritative; conflicting browser ids are forged."""
    browser_claims = browser_claims or {}
    mapping = (
        ("tenant_id", "forged_tenant"),
        ("user_id", "forged_user"),
        ("post_id", "forged_post"),
    )
    for field, code in mapping:
        browser_val = browser_claims.get(field)
        if browser_val is None or browser_val == "":
            continue
        if str(browser_val) != str(session_claims.get(field)):
            raise AuthContextError(code, f"browser {field} does not match session")
    return session_claims


def verify_context(
    packet: Dict[str, Any],
    *,
    browser_claims: Optional[Dict[str, Any]] = None,
    secret: Optional[str] = None,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    session = verify_signature(packet, secret=secret, now=now)
    return reconcile_browser_claims(session, browser_claims)


def build_from_main_session(
    *,
    support_id: str,
    user_id: str,
    post_id: str,
    role_labels: Sequence[str],
    product_version: str,
    page_route: str = "/ChatBot",
    display_name: Optional[str] = None,
    secret: Optional[str] = None,
    ttl_seconds: int = 300,
) -> Dict[str, Any]:
    """Mirror ChatBotController.Chat server-side identity assembly."""
    claims: Dict[str, Any] = {
        "tenant_id": str(support_id),
        "user_id": str(user_id),
        "post_id": str(post_id),
        "role_labels": list(role_labels) or ["کارشناس"],
        "product_version": product_version,
        "page_route": page_route,
    }
    if display_name:
        claims["display_name"] = display_name
    return sign_context(claims, secret=secret, ttl_seconds=ttl_seconds)
