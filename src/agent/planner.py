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


UX_HINTS = (
    "چگونه",
    "چطور",
    "ثبت",
    "مسیر",
    "فرم",
    "دکمه",
    "راهنما",
    "صفحه",
    "منو",
    "بردکرامب",
    "ux",
    "how to",
    "navigate",
)

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
        is_ux = any(h in q_lower for h in UX_HINTS)
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
