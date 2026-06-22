"""Deterministic issue classifier: classification, priority, risk_level."""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── Classification rules (keyword → category) ─────────────────────────────────
_CLASSIFICATION_RULES: list[tuple[list[str], str]] = [
    (["dependabot", "dependency", "bump", "upgrade", "dep "], "dependency"),
    (["type hint", "type annotation", "mypy", "typing", "-> ", ": str", ": int"], "type-hint"),
    (["lint", "ruff", "flake8", "pylint", "==false", "== false", "== true", "==true"], "lint"),
    (["typo", "spelling", "misspell", "docstring", "comment", "currently"], "docs"),
    (["test", "flaky", "pytest", "unittest", "spec"], "test"),
    (["security", "cve", "vuln", "xss", "injection", "csrf"], "security"),
    (["bug", "error", "exception", "traceback", "fix", "broken", "crash", "fail"], "bug"),
]

# ── Priority rules ────────────────────────────────────────────────────────────
_HIGH_KEYWORDS = ["critical", "urgent", "security", "cve", "p0", "p1", "blocker", "crash"]
_MEDIUM_KEYWORDS = ["bug", "fix", "broken", "error", "p2"]
_HIGH_LABELS = {"priority: critical", "p0", "p1", "severity: high", "security"}
_MEDIUM_LABELS = {"priority: medium", "p2", "bug"}


@dataclass
class Classification:
    classification: str
    priority: str
    risk_level: str


def classify_issue(
    title: str,
    body: str | None,
    labels: list[str] | None = None,
) -> Classification:
    """Return classification, priority, and risk_level for a GitHub issue."""
    text = f"{title} {body or ''}".lower()
    label_set = {lbl.lower().strip() for lbl in (labels or [])}

    # Classification
    classification = "bug"  # default
    for keywords, category in _CLASSIFICATION_RULES:
        if any(kw in text for kw in keywords):
            classification = category
            break

    # Priority
    if label_set & _HIGH_LABELS or any(kw in text for kw in _HIGH_KEYWORDS):
        priority = "high"
    elif label_set & _MEDIUM_LABELS or any(kw in text for kw in _MEDIUM_KEYWORDS):
        priority = "medium"
    else:
        priority = "low"

    # Risk level — conservative: security/bug = medium+, everything else = low
    if classification == "security" or priority == "high":
        risk_level = "high"
    elif classification in ("bug", "dependency"):
        risk_level = "medium"
    else:
        risk_level = "low"

    return Classification(
        classification=classification,
        priority=priority,
        risk_level=risk_level,
    )


def slugify(text: str, max_len: int = 50) -> str:
    """Convert a string to a branch-name-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len]
