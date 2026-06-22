"""Unit tests for the issue classifier."""

import pytest

from app.services.classifier import classify_issue


@pytest.mark.parametrize("title,body,labels,expected_clf", [
    # Lint detection
    ("fix(lint): replace == False with ~ in DAO", "", [], "lint"),
    ("ruff E712 cleanup", "Remove == False comparisons", [], "lint"),
    # Type hints
    ("add missing type hints to helpers.py", "", [], "type-hint"),
    ("mypy annotation fixes", "Add return type annotations", [], "type-hint"),
    # Docs
    ("fix typo in docstring", "", [], "docs"),
    ("remove 'currently' from comments", "", [], "docs"),
    # Dependency
    ("bump cachetools to >=5.0", "", [], "dependency"),
    ("dependabot: upgrade requests", "", [], "dependency"),
    # Bug
    ("fix: dashboard load fails", "Traceback: ...", [], "bug"),
    # Security
    ("security: XSS in chart title", "", [], "security"),
])
def test_classification(title, body, labels, expected_clf):
    result = classify_issue(title, body, labels)
    assert result.classification == expected_clf, (
        f"Expected {expected_clf!r}, got {result.classification!r} for {title!r}"
    )


def test_priority_high_from_label():
    result = classify_issue("some issue", "", ["priority: critical"])
    assert result.priority == "high"


def test_priority_medium_default_for_bug():
    result = classify_issue("fix: something broken", "traceback error", [])
    assert result.priority == "medium"


def test_priority_low_for_docs():
    # "correct typo" has no bug/fix keywords → genuinely low priority
    result = classify_issue("correct typo in README", "", [])
    assert result.priority == "low"


def test_risk_high_for_security():
    result = classify_issue("security: XSS vulnerability", "", [])
    assert result.risk_level == "high"


def test_risk_low_for_lint():
    result = classify_issue("fix(lint): remove == False", "", [])
    assert result.risk_level == "low"
