"""W2-04: normalize assistant payloads into the Persian customer-facing template."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


HEADER = "کاری که انجام دهید"


def format_persian_answer(
    payload: Dict[str, Any],
    *,
    role: Optional[str] = None,
    product_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Rewrite answer_text_fa into the standard FA template; keep structured fields."""
    out = dict(payload)
    status = out.get("status") or "answered"
    trace_id = out.get("trace_id") or "trace:unknown"
    steps = out.get("steps") or []
    prerequisites = list(out.get("prerequisites") or [])
    role_line = role or _first_role(out)
    version = product_version or out.get("knowledge_revision") or "نسخهٔ جاری نصب"

    if status == "clarify":
        question = _one_clarify_question(out)
        body = [
            HEADER,
            "",
            "برای ادامه به یک جزئیات نیاز است:",
            question,
            "",
            f"اگر به کمک انسانی نیاز دارید، شناسهٔ پیگیری را به پشتیبانی بدهید: {trace_id}",
        ]
        out["answer_text_fa"] = "\n".join(body)
        out["clarify_question"] = question
        return out

    if status == "escalate":
        reason = out.get("escalation_reason") or "نیاز به بررسی انسانی"
        body = [
            HEADER,
            "",
            "این مورد را نمی‌توانم به‌صورت خودکار کامل کنم.",
            f"علت: {reason}",
            f"لطفاً با پشتیبانی تماس بگیرید و این شناسهٔ پیگیری را اعلام کنید: {trace_id}",
        ]
        out["answer_text_fa"] = "\n".join(body)
        return out

    lines: List[str] = [HEADER, ""]
    if role_line or version:
        cond_bits = []
        if role_line:
            cond_bits.append(f"نقش: {role_line}")
        if version:
            cond_bits.append(f"نسخه: {version}")
        lines.append("شرط نقش/نسخه: " + " | ".join(cond_bits))
        lines.append("")

    if prerequisites:
        lines.append("پیش‌نیازها:")
        for p in prerequisites[:6]:
            lines.append(f"- {p}")
        lines.append("")

    if steps:
        lines.append("مراحل:")
        for i, st in enumerate(steps, start=1):
            label = (st.get("label") or f"گام {i}").strip()
            instruction = (st.get("instruction") or "").strip()
            lines.append(f"{i}) «{label}»: {instruction}")
            if st.get("expected_after"):
                lines.append(f"   نتیجهٔ مورد انتظار: {st['expected_after']}")
            if st.get("prerequisite"):
                lines.append(f"   پیش‌نیاز گام: {st['prerequisite']}")
            if st.get("condition"):
                lines.append(f"   شرط: {st['condition']}")
        lines.append("")
    else:
        raw = (out.get("answer_text_fa") or "").strip()
        if raw and not raw.startswith(HEADER):
            lines.append(raw)
            lines.append("")
        elif raw.startswith(HEADER):
            # already templated process text — keep core after header if present
            rest = raw.split("\n", 1)
            if len(rest) > 1 and rest[1].strip():
                lines.append(rest[1].strip())
                lines.append("")

    if out.get("expected_result"):
        lines.append(f"نتیجهٔ نهایی مورد انتظار: {out['expected_result']}")
        lines.append("")

    if out.get("uncertainty"):
        lines.append("نکته / ابهام:")
        lines.append(str(out["uncertainty"]))
        lines.append("")
        lines.append(
            "سؤال مشخص: نقش و نسخهٔ نصب شما با این راهنما یکی است، یا باید مسیر دیگری را بگویید؟"
        )
        lines.append("")

    lines.append(f"در صورت نیاز به پشتیبانی، شناسهٔ پیگیری: {trace_id}")
    out["answer_text_fa"] = "\n".join(lines).strip()
    out["template"] = {
        "name": "persian_v0",
        "header": HEADER,
        "has_steps": bool(steps),
        "has_role_version": bool(role_line or version),
        "has_support_trace": True,
    }
    return out


def _first_role(payload: Dict[str, Any]) -> Optional[str]:
    for ev in payload.get("evidence") or []:
        roles = ev.get("role_scope") or []
        if roles:
            return roles[0]
    sub = payload.get("subgraph") or {}
    roles = sub.get("role_scope") or []
    return roles[0] if roles else None


def _one_clarify_question(payload: Dict[str, Any]) -> str:
    text = (payload.get("answer_text_fa") or "").strip()
    # Prefer a single interrogative sentence already present
    for part in text.replace("؟", "؟\n").split("\n"):
        p = part.strip()
        if p.endswith("؟"):
            return p
    reason = payload.get("uncertainty") or payload.get("reason_code") or ""
    if "personal" in str(reason):
        return "آیا راهنمای عمومی یک فرآیند مشخص را می‌خواهید، یا وضعیت همان قرارداد/نشست جاری؟"
    if "ambiguous" in str(reason):
        return "کدام فرآیند یا صفحه مدنظرتان است (مثلاً مناقصه دو مرحله‌ای، ارزیابی کیفی، منابع پیشنهادی)؟"
    return "لطفاً یک فرآیند یا صفحهٔ مشخص را نام ببرید تا راهنمای مرحله‌ای بدهم."
