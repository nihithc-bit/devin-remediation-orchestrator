"""Canned keyword-matched SQL responses for analytics queries.

Used as a fallback when the live Devin NL→SQL session doesn't return
structured output in time. All queries target the three known tables:
devin_runs, devin_events, analytics_queries.
"""

from __future__ import annotations

from typing import Any

ANALYTICS_RESPONSES: list[dict[str, Any]] = [
    {
        "question_keywords": ["fix", "month"],
        "safe": True,
        "sql": (
            "SELECT COUNT(*) AS issues_fixed "
            "FROM devin_runs "
            "WHERE status IN ('READY_FOR_REVIEW', 'MERGED') "
            "AND started_at >= date_trunc('month', CURRENT_DATE) "
            "LIMIT 1"
        ),
        "chart_type": "metric",
        "x_axis": None,
        "y_axis": "issues_fixed",
        "explanation": "Counts remediation runs that resulted in a PR ready for review or merged this month.",
    },
    {
        "question_keywords": ["failed", "reason", "failure", "fail", "why"],
        "safe": True,
        "sql": (
            "SELECT failure_reason, COUNT(*) AS count "
            "FROM devin_runs "
            "WHERE status IN ('BLOCKED', 'FAILED', 'NEEDS_HUMAN_REVIEW') "
            "AND failure_reason IS NOT NULL "
            "GROUP BY failure_reason "
            "ORDER BY count DESC "
            "LIMIT 20"
        ),
        "chart_type": "bar",
        "x_axis": "failure_reason",
        "y_axis": "count",
        "explanation": "Groups failed/blocked sessions by their failure reason.",
    },
    {
        "question_keywords": ["pr", "week", "opened"],
        "safe": True,
        "sql": (
            "SELECT to_char(date_trunc('week', started_at), 'YYYY-MM-DD') AS week, "
            "COUNT(*) AS prs_opened "
            "FROM devin_runs "
            "WHERE status IN ('PR_OPENED', 'CI_RUNNING', 'READY_FOR_REVIEW', 'MERGED') "
            "GROUP BY date_trunc('week', started_at) "
            "ORDER BY week "
            "LIMIT 52"
        ),
        "chart_type": "line",
        "x_axis": "week",
        "y_axis": "prs_opened",
        "explanation": "Shows pull requests opened per week over time.",
    },
    {
        "question_keywords": ["acu", "consume", "type", "issue"],
        "safe": True,
        "sql": (
            "SELECT classification, AVG(acu_used) AS avg_acu, COUNT(*) AS runs "
            "FROM devin_runs "
            "WHERE acu_used IS NOT NULL "
            "GROUP BY classification "
            "ORDER BY avg_acu DESC "
            "LIMIT 20"
        ),
        "chart_type": "bar",
        "x_axis": "classification",
        "y_axis": "avg_acu",
        "explanation": "Shows average ACU consumption broken down by issue classification.",
    },
    {
        "question_keywords": ["average", "time", "label", "pr"],
        "safe": True,
        "sql": (
            "SELECT AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) AS avg_seconds "
            "FROM devin_runs "
            "WHERE completed_at IS NOT NULL "
            "AND status IN ('PR_OPENED', 'CI_RUNNING', 'READY_FOR_REVIEW', 'MERGED') "
            "LIMIT 1"
        ),
        "chart_type": "metric",
        "x_axis": None,
        "y_axis": "avg_seconds",
        "explanation": "Mean time in seconds from issue label to PR opened.",
    },
    {
        "question_keywords": ["active", "session"],
        "safe": True,
        "sql": (
            "SELECT issue_number, issue_title, status, devin_session_url, started_at "
            "FROM devin_runs "
            "WHERE status IN ('QUEUED', 'DEVIN_SESSION_CREATED', 'RUNNING') "
            "ORDER BY started_at DESC "
            "LIMIT 50"
        ),
        "chart_type": "table",
        "x_axis": None,
        "y_axis": None,
        "explanation": "Lists all currently active Devin sessions.",
    },
    {
        "question_keywords": ["breakdown", "classification", "type", "category"],
        "safe": True,
        "sql": (
            "SELECT classification, COUNT(*) AS runs, "
            "SUM(CASE WHEN status IN ('PR_OPENED','CI_RUNNING','READY_FOR_REVIEW','MERGED') THEN 1 ELSE 0 END) AS successful "
            "FROM devin_runs "
            "GROUP BY classification "
            "ORDER BY runs DESC "
            "LIMIT 20"
        ),
        "chart_type": "bar",
        "x_axis": "classification",
        "y_axis": "runs",
        "explanation": "Breakdown of remediation runs by issue classification.",
    },
    {
        "question_keywords": ["total", "count", "how many"],
        "safe": True,
        "sql": (
            "SELECT status, COUNT(*) AS count "
            "FROM devin_runs "
            "GROUP BY status "
            "ORDER BY count DESC "
            "LIMIT 20"
        ),
        "chart_type": "bar",
        "x_axis": "status",
        "y_axis": "count",
        "explanation": "Total run count grouped by status.",
    },
    {
        "question_keywords": ["blocked", "percentage", "percent"],
        "safe": True,
        "sql": (
            "SELECT "
            "ROUND(100.0 * SUM(CASE WHEN status = 'BLOCKED' THEN 1 ELSE 0 END) / COUNT(*), 1) AS blocked_pct, "
            "COUNT(*) AS total "
            "FROM devin_runs "
            "LIMIT 1"
        ),
        "chart_type": "metric",
        "x_axis": None,
        "y_axis": "blocked_pct",
        "explanation": "Percentage of Devin runs that ended in a blocked state.",
    },
    {
        "question_keywords": ["completed", "complete", "finished", "done"],
        "safe": True,
        "sql": (
            "SELECT issue_number, issue_title, classification, pr_url, completed_at "
            "FROM devin_runs "
            "WHERE status IN ('READY_FOR_REVIEW', 'MERGED', 'PR_OPENED') "
            "ORDER BY completed_at DESC "
            "LIMIT 50"
        ),
        "chart_type": "table",
        "x_axis": None,
        "y_axis": None,
        "explanation": "All completed remediation runs with PR links.",
    },
    {
        "question_keywords": ["success", "rate", "week"],
        "safe": True,
        "sql": (
            "SELECT to_char(date_trunc('week', started_at), 'YYYY-MM-DD') AS week, "
            "ROUND(100.0 * SUM(CASE WHEN status IN ('PR_OPENED','CI_RUNNING','READY_FOR_REVIEW','MERGED') "
            "THEN 1 ELSE 0 END) / COUNT(*), 1) AS success_rate_pct "
            "FROM devin_runs "
            "GROUP BY date_trunc('week', started_at) "
            "ORDER BY week "
            "LIMIT 52"
        ),
        "chart_type": "line",
        "x_axis": "week",
        "y_axis": "success_rate_pct",
        "explanation": "Remediation success rate (%) by week — percentage of runs that produced a PR.",
    },
]


def get_analytics_response(question: str) -> dict[str, Any]:
    """Return the best keyword-matched analytics response for a question."""
    q = question.lower()
    best: dict[str, Any] | None = None
    best_score = 0
    for resp in ANALYTICS_RESPONSES:
        score = sum(1 for kw in resp["question_keywords"] if kw in q)
        if score > best_score:
            best_score = score
            best = resp
    if best is None:
        best = ANALYTICS_RESPONSES[-1]  # default: success rate by week
    return best
