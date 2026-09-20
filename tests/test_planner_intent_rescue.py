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


def test_rescue_upgrades_unknown_on_explicit_route_hit():
    p = QueryPlanner()
    plan = QueryPlan(intent="unknown", tools=["search_code"], skip_ast=True, skip_ux_template=True)
    rescued = p.rescue_from_evidence(plan, route_hit=True)
    assert rescued.intent == "ux"
    assert rescued.skip_ast is False
    assert "get_route" in rescued.tools


def test_rescue_keeps_unknown_without_explicit_hit():
    p = QueryPlanner()
    plan = QueryPlan(intent="unknown", tools=["search_code"])
    rescued = p.rescue_from_evidence(
        plan, routes_found=5, forms_found=5, hybrid_hits=10, label_hits=10
    )
    assert rescued.intent == "unknown"


def test_rescue_label_hit_upgrades():
    p = QueryPlanner()
    plan = QueryPlan(intent="unknown", tools=["search_code"])
    assert p.rescue_from_evidence(plan, label_hit=True).intent == "ux"


def test_rescue_does_not_override_non_unknown():
    p = QueryPlanner()
    plan = QueryPlan(intent="api", tools=["search_code", "get_api"])
    rescued = p.rescue_from_evidence(plan, route_hit=True, routes_found=5)
    assert rescued.intent == "api"

