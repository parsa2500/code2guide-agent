"""Planner intent classification + evidence rescue."""

from src.agent.planner import QueryPlanner, QueryPlan


def test_weather_how_alone_is_unknown():
    p = QueryPlanner()
    plan = p.plan("فردا هوا چطوره؟")
    assert plan.intent == "unknown"


def test_bitcoin_unrelated_is_unknown():
    p = QueryPlanner()
    plan = p.plan("قیمت بیت‌کوین امروز چقدر است؟")
    assert plan.intent == "unknown"


def test_tender_how_with_context_is_ux():
    p = QueryPlanner()
    plan = p.plan("چگونه مناقصه جدید ثبت کنم؟")
    assert plan.intent == "ux"


def test_profile_settings_where_is_ux():
    p = QueryPlanner()
    plan = p.plan("تنظیمات پروفایل کجاست؟")
    assert plan.intent == "ux"


def test_rescue_upgrades_unknown_when_routes_found():
    p = QueryPlanner()
    plan = QueryPlan(intent="unknown", tools=["search_code"], skip_ast=True, skip_ux_template=True)
    rescued = p.rescue_from_evidence(plan, routes_found=1)
    assert rescued.intent == "ux"
    assert rescued.skip_ast is False
    assert "get_route" in rescued.tools


def test_rescue_keeps_unknown_without_strong_evidence():
    p = QueryPlanner()
    plan = QueryPlan(intent="unknown", tools=["search_code"])
    rescued = p.rescue_from_evidence(plan, routes_found=0, forms_found=0, hybrid_hits=2, label_hits=1)
    assert rescued.intent == "unknown"


def test_rescue_hybrid_needs_five():
    p = QueryPlanner()
    plan = QueryPlan(intent="unknown", tools=["search_code"])
    assert p.rescue_from_evidence(plan, hybrid_hits=4).intent == "unknown"
    assert p.rescue_from_evidence(plan, hybrid_hits=5).intent == "ux"


def test_rescue_does_not_override_non_unknown():
    p = QueryPlanner()
    plan = QueryPlan(intent="api", tools=["search_code", "get_api"])
    rescued = p.rescue_from_evidence(plan, routes_found=5)
    assert rescued.intent == "api"
