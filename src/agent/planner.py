"""Query planner: classify user intent for Code2Guide Q&A."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from src.agent.tools import Code2GuideToolbox
from src.core.normalizer import default_normalizer


class QueryPlan(BaseModel):
    """Structured plan for answering a user question."""

    intent: str = Field(
        description="ux | api | data | flow | mixed | unknown",
        default="ux",
    )
    tools: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    trace_ref: Optional[str] = None
    skip_ast: bool = False
    skip_ux_template: bool = False


# HOW-only words: alone must NOT force intent=ux (e.g. «فردا هوا چطوره؟»).
HOW_WORDS = (
    "چگونه",
    "چطور",
    "کجا",
    "how to",
)

# Domain / org / form UX hints (no bare HOW words).
UX_DOMAIN_HINTS = (
    "ثبت",
    "مسیر",
    "فرم",
    "دکمه",
    "راهنما",
    "صفحه",
    "منو",
    "بردکرامب",
    "ux",
    # organizational / panel synonyms (ExternalService-style)
    "تنظیمات",
    "پروفایل",
    "داشبورد",
    "شرکت",
    "شرکت‌ها",
    "توکن",
    "پرداخت",
    "لاگ",
    "لاگ‌ها",
    "دانش",
    "پایگاه دانش",
    "خروجی",
    "گزارش",
    "اعلان",
    "بسته",
    "مدیریت",
    "باز کنم",
    "ببینم",
    "settings",
    "dashboard",
    "profile",
    "token",
    "payment",
    "logs",
    "navigate",
)

# Context required when a HOW word is present.
UX_HOW_CONTEXT = (
    "فرم",
    "صفحه",
    "دکمه",
    "منو",
    "مسیر",
    "ثبت",
    "راهنما",
    "بردکرامب",
    "تنظیمات",
    "پروفایل",
    "داشبورد",
    "شرکت",
    "توکن",
    "پرداخت",
    "لاگ",
    "دانش",
    "گزارش",
    "اعلان",
    "بسته",
    "مدیریت",
    "settings",
    "dashboard",
    "profile",
    "token",
    "payment",
    "logs",
    "navigate",
    "ux",
)

# Back-compat alias: domain hints only (tests / callers may still import UX_HINTS).
UX_HINTS = UX_DOMAIN_HINTS

API_HINTS = (
    "api",
    "endpoint",
    "post ",
    "get ",
    "http",
    "controller",
    "کنترلر",
    "/api/",
)

DATA_HINTS = (
    "entity",
    "جدول",
    "table",
    "ستون",
    "فیلد مدل",
    "مدل",
    "migration",
    "دیتابیس",
    "database",
    "dbset",
    "orm",
)


class QueryPlanner:
    """Rule-based multi-intent planner (no LLM required)."""

    def plan(self, query: str) -> QueryPlan:
        q = (query or "").strip()
        q_lower = q.lower()
        keywords = default_normalizer.extract_keywords(q)

        is_flow = Code2GuideToolbox.is_flow_query(q)
        is_backend = Code2GuideToolbox.is_backend_query(q)
        has_how = any(h in q_lower for h in HOW_WORDS)
        has_domain = any(h in q_lower for h in UX_DOMAIN_HINTS)
        has_how_ctx = any(h in q_lower for h in UX_HOW_CONTEXT)
        is_ux = has_domain or (has_how and has_how_ctx)
        is_api = any(h in q_lower for h in API_HINTS) or (
            is_backend and any(h in q_lower for h in ("api", "endpoint", "controller", "کنترلر", "سرویس", "service"))
        )
        is_data = any(h in q_lower for h in DATA_HINTS) or (
            is_backend and any(h in q_lower for h in ("entity", "جدول", "table", "مدل", "migration"))
        )

        # Negative / empty-ish
        if not q or len(q) < 2:
            return QueryPlan(intent="unknown", tools=["search_code"], keywords=keywords, skip_ast=True)

        tools: List[str] = ["search_code"]
        intent = "ux"

        if is_flow and (is_ux or is_backend or is_api):
            intent = "mixed" if is_ux else "flow"
        elif is_flow:
            intent = "flow"
        elif is_ux and (is_api or is_data or is_backend):
            intent = "mixed"
        elif is_api and not is_data:
            intent = "api"
        elif is_data:
            intent = "data"
        elif is_backend:
            intent = "api" if is_api else "data"
        elif is_ux:
            intent = "ux"
        else:
            # No recognizable UX/API/data/flow signal → do not invent an answer
            intent = "unknown"

        if intent in ("ux", "mixed"):
            tools.extend(["get_route"])
        if intent in ("api", "mixed", "flow"):
            tools.extend(["get_api", "trace_flow"])
        if intent in ("data", "mixed", "flow"):
            tools.extend(["get_entity", "get_table"])
        if intent == "flow":
            tools = ["search_code", "get_route", "get_api", "get_entity", "get_table", "trace_flow"]
        if intent == "unknown":
            tools = ["search_code"]

        # de-dupe preserve order
        seen = set()
        tools_u = []
        for t in tools:
            if t not in seen:
                seen.add(t)
                tools_u.append(t)

        skip_ast = intent in ("api", "data", "flow", "unknown")
        skip_ux = intent in ("api", "data", "flow", "unknown")

        trace_ref = None
        if intent in ("flow", "mixed") or "trace_flow" in tools_u:
            if "tender" in q_lower or "مناقصه" in q:
                trace_ref = "/tenders/create"

        return QueryPlan(
            intent=intent,
            tools=tools_u,
            keywords=keywords,
            trace_ref=trace_ref,
            skip_ast=skip_ast,
            skip_ux_template=skip_ux,
        )

    def rescue_from_evidence(
        self,
        plan: QueryPlan,
        *,
        route_hit: bool = False,
        label_hit: bool = False,
        # legacy count kwargs ignored for strength (kept for call-site compat)
        routes_found: int = 0,
        forms_found: int = 0,
        hybrid_hits: int = 0,
        label_hits: int = 0,
    ) -> QueryPlan:
        """Upgrade unknown→ux only on explicit route/label token hit (not hybrid/forms/maps_to)."""
        if plan.intent != "unknown":
            return plan
        # Prefer explicit booleans; fall back to counts only if booleans unused by old callers
        strong = bool(route_hit) or bool(label_hit)
        if not strong:
            # Counts alone are NOT enough anymore (basket-2 guard).
            return plan
        tools = list(plan.tools or [])
        for t in ("search_code", "get_route"):
            if t not in tools:
                tools.append(t)
        return plan.model_copy(
            update={
                "intent": "ux",
                "tools": tools,
                "skip_ast": False,
                "skip_ux_template": False,
            }
        )
