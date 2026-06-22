"""Tests for the analytics flow: NL→SQL keyword matching → SQL guard → result."""

from __future__ import annotations

import pytest

from app.services.analytics_queries import ANALYTICS_RESPONSES, get_analytics_response
from app.services.sql_guard import SQLGuardError, validate_and_sanitize


def test_all_analytics_sqls_pass_guard():
    """Every canned analytics SQL must pass the safety guard."""
    for resp in ANALYTICS_RESPONSES:
        sql = resp["sql"]
        try:
            sanitized = validate_and_sanitize(sql, default_limit=500)
            assert "SELECT" in sanitized.upper(), f"Expected SELECT in: {sanitized}"
        except SQLGuardError as exc:
            pytest.fail(f"Canned SQL failed guard: {exc}\nSQL: {sql}")


def test_success_rate_by_week_returns_line_chart():
    resp = get_analytics_response("remediation success rate by week as a graph")
    assert resp["chart_type"] == "line"
    assert resp["x_axis"] == "week"
    assert resp["y_axis"] == "success_rate_pct"


def test_active_sessions_returns_table():
    resp = get_analytics_response("show me all active Devin sessions")
    assert resp["chart_type"] == "table"


def test_failures_by_reason_returns_bar():
    resp = get_analytics_response("show failed sessions by failure reason")
    assert resp["chart_type"] == "bar"


def test_prs_per_week_returns_line():
    resp = get_analytics_response("graph PRs opened per week")
    assert resp["chart_type"] == "line"


def test_guard_injects_limit_on_table_queries():
    """Confirm that table queries get LIMIT injected."""
    for resp in ANALYTICS_RESPONSES:
        if resp["chart_type"] == "table":
            sanitized = validate_and_sanitize(resp["sql"], default_limit=500)
            assert "LIMIT" in sanitized.upper(), f"LIMIT not injected for: {resp['sql']}"


def test_unsafe_sql_rejected_by_guard():
    with pytest.raises(SQLGuardError):
        validate_and_sanitize("SELECT * FROM pg_roles")


def test_failure_keywords_match_bar_chart():
    """'why did the devin runs fail' should route to failure reason bar chart."""
    resp = get_analytics_response("why did the devin runs fail")
    assert resp["chart_type"] == "bar"
    assert resp["x_axis"] == "failure_reason"


def test_default_fallback_is_success_rate():
    """Unrecognized question falls back to success rate by week."""
    resp = get_analytics_response("foobar baz qux unrecognized gibberish")
    assert resp["chart_type"] == "line"
    assert resp["y_axis"] == "success_rate_pct"
