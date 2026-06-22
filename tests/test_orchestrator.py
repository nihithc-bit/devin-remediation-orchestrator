"""Tests for the orchestrator flow (uses unittest.mock for external dependencies)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.schemas import GitHubIssuePayload
from app.state import RunStatus
from app.services.analytics_queries import get_analytics_response


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_github_client():
    client = MagicMock()
    client.post_issue_comment = AsyncMock(return_value={"id": 123, "html_url": "https://example.com"})
    client.add_label = AsyncMock()
    return client


@pytest.fixture
def sample_labeled_payload():
    return GitHubIssuePayload(
        action="labeled",
        issue={
            "number": 42,
            "title": "fix(lint): remove == False",
            "body": "Replace == False with ~ in daos/",
            "html_url": "https://github.com/test-org/superset/issues/42",
            "labels": [{"name": "devin:auto-remediate"}],
        },
        label={"name": "devin:auto-remediate"},
        repository={"full_name": "test-org/superset"},
        sender={"login": "tester"},
    )


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_analytics_canned_responses():
    """Canned analytics responses match expected chart types."""
    r = get_analytics_response("success rate by week as a graph")
    assert r["chart_type"] == "line"
    assert r["safe"] is True
    assert "SELECT" in r["sql"].upper()

    r2 = get_analytics_response("show active sessions")
    assert r2["chart_type"] == "table"

    r3 = get_analytics_response("how many issues fixed this month")
    assert r3["chart_type"] == "metric"


def test_classifier_used_in_orchestrator():
    """classify_issue should be pure and deterministic."""
    from app.services.classifier import classify_issue
    r1 = classify_issue("fix(lint): remove == False", "", [])
    r2 = classify_issue("fix(lint): remove == False", "", [])
    assert r1.classification == r2.classification == "lint"


def test_devin_client_builds_correct_payload():
    """RealDevinClient constructs the session payload correctly."""
    from app.services.devin_client import RealDevinClient
    import app.services.devin_client as dc_module

    # Patch settings so no real credentials are needed during test
    original_key = dc_module.settings.devin_api_key
    dc_module.settings.devin_api_key = "apk_test"
    try:
        client = RealDevinClient()
        assert client._client.headers.get("authorization") == "Bearer apk_test"
    finally:
        dc_module.settings.devin_api_key = original_key


def test_orchestrator_skips_wrong_label(sample_labeled_payload):
    """handle_issue_labeled returns None when label doesn't match."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    wrong_payload = GitHubIssuePayload(
        action="labeled",
        issue=sample_labeled_payload.issue,
        label={"name": "bug"},
        repository=sample_labeled_payload.repository,
        sender=sample_labeled_payload.sender,
    )

    db = MagicMock()
    github = MagicMock()

    from app.services.orchestrator import handle_issue_labeled
    result = asyncio.get_event_loop().run_until_complete(
        handle_issue_labeled(db, github, wrong_payload, "delivery-123")
    )
    assert result is None
