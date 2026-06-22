"""Unit tests for the SQL safety guard."""

import pytest

from app.services.sql_guard import SQLGuardError, validate_and_sanitize


# ── Happy path ─────────────────────────────────────────────────────────────────

def test_simple_select_passes():
    sql = "SELECT * FROM devin_runs LIMIT 10"
    result = validate_and_sanitize(sql)
    assert "devin_runs" in result


def test_aggregate_no_limit_needed():
    sql = "SELECT COUNT(*) FROM devin_runs"
    result = validate_and_sanitize(sql)
    # Pure aggregate — LIMIT not injected
    assert "LIMIT" not in result.upper()


def test_group_by_gets_limit_injected():
    sql = "SELECT status, COUNT(*) FROM devin_runs GROUP BY status"
    result = validate_and_sanitize(sql)
    assert "LIMIT" in result.upper()


def test_all_whitelisted_tables():
    for table in ("devin_runs", "devin_events", "analytics_queries"):
        sql = f"SELECT * FROM {table} LIMIT 5"
        result = validate_and_sanitize(sql)
        assert table in result


def test_join_whitelisted_tables():
    sql = (
        "SELECT r.issue_number, e.event_type "
        "FROM devin_runs r JOIN devin_events e ON r.id = e.run_id "
        "LIMIT 20"
    )
    result = validate_and_sanitize(sql)
    assert "devin_runs" in result


# ── Blocked queries ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("evil_sql", [
    "INSERT INTO devin_runs (id) VALUES ('x')",
    "UPDATE devin_runs SET status = 'MERGED'",
    "DELETE FROM devin_runs",
    "DROP TABLE devin_runs",
    "ALTER TABLE devin_runs ADD COLUMN x TEXT",
    "TRUNCATE devin_runs",
    "CREATE TABLE evil (id int)",
    "COPY devin_runs TO '/tmp/dump'",
    "GRANT ALL ON devin_runs TO evil",
    "REVOKE SELECT ON devin_runs FROM analytics_ro",
])
def test_blocked_keywords(evil_sql: str):
    with pytest.raises(SQLGuardError, match="Blocked keyword"):
        validate_and_sanitize(evil_sql)


def test_non_whitelisted_table_rejected():
    with pytest.raises(SQLGuardError, match="non-whitelisted"):
        validate_and_sanitize("SELECT * FROM pg_tables LIMIT 10")


def test_multiple_statements_rejected():
    with pytest.raises(SQLGuardError, match="Multiple statements"):
        validate_and_sanitize("SELECT 1; SELECT 2")


def test_empty_sql_rejected():
    with pytest.raises(SQLGuardError):
        validate_and_sanitize("")


def test_non_select_rejected():
    with pytest.raises(SQLGuardError):
        validate_and_sanitize("WITH x AS (SELECT 1) SELECT * FROM x")


# ── LIMIT injection ────────────────────────────────────────────────────────────

def test_limit_injected_when_missing():
    sql = "SELECT issue_number, status FROM devin_runs WHERE status = 'RUNNING'"
    result = validate_and_sanitize(sql, default_limit=100)
    assert "LIMIT 100" in result.upper()


def test_existing_limit_not_doubled():
    sql = "SELECT * FROM devin_runs LIMIT 5"
    result = validate_and_sanitize(sql, default_limit=100)
    assert result.upper().count("LIMIT") == 1
