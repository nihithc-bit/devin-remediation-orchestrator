"""Prompt templates for Devin sessions."""

from __future__ import annotations

import re


def build_remediation_prompt(
    issue_number: int,
    issue_title: str,
    issue_body: str,
    repo: str,
    classification: str,
) -> str:
    """Build the structured remediation prompt sent to Devin."""
    slug = re.sub(r"[^a-z0-9]+", "-", issue_title.lower()).strip("-")[:50]
    branch_name = f"devin/issue-{issue_number}-{slug}"

    return f"""You are remediating issue #{issue_number} in {repo}.

## Goal
Fix the issue described below and open a pull request.

## Issue
**Title:** {issue_title}

**Body:**
{issue_body or "(no body provided)"}

## Repository
{repo}

## Requirements
1. Clone the repository and check out a **new branch** named exactly: `{branch_name}`
2. Make the **smallest safe change** that resolves the issue.
3. Run relevant tests, lint checks (ruff), and type checks (mypy) where appropriate.
4. Update dependency lockfiles only if required.
5. Open a PR referencing this issue (use "Closes #{issue_number}" in the PR body).
6. Include a **verification summary** in the PR body: tests run, lint result, type-check result.
7. If blocked, explain exactly why in the `blockers` field of your structured output.

## Classification
This issue is classified as: **{classification}**

## Definition of Done
- PR opened on branch `{branch_name}`
- CI-relevant checks documented in the PR body
- Issue #{issue_number} linked with "Closes #{issue_number}"
- Risk level stated (low/medium/high)
- **Human review required before merge — do NOT merge.**

## Structured Output
Return your result as structured JSON matching the required schema with fields:
issue_number, status (fixed|blocked|failed|needs_human_review), pr_url, branch_name,
tests_run (list of strings), risk_level (low|medium|high), summary, blockers (list of strings).
"""


# ── DB schema doc embedded in the analytics prompt ────────────────────────────
_DB_SCHEMA_DOC = """
devin_runs(
  id UUID,
  issue_number INTEGER,
  issue_title TEXT,
  issue_url TEXT,
  repo VARCHAR(255),
  classification VARCHAR(100),
  priority VARCHAR(50),
  devin_session_id VARCHAR(255),
  devin_session_url TEXT,
  status VARCHAR(50),  -- NEW|QUEUED|DEVIN_SESSION_CREATED|RUNNING|PR_OPENED|CI_RUNNING|READY_FOR_REVIEW|MERGED|BLOCKED|FAILED|NEEDS_HUMAN_REVIEW
  branch_name VARCHAR(255),
  pr_url TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  acu_used NUMERIC(10,4),
  tests_run JSON,
  risk_level VARCHAR(50),
  failure_reason TEXT,
  raw_devin_response JSON
)

devin_events(
  id UUID,
  run_id UUID REFERENCES devin_runs(id),
  event_type VARCHAR(100),
  event_payload JSON,
  created_at TIMESTAMPTZ
)

analytics_queries(
  id UUID,
  user_question TEXT,
  generated_sql TEXT,
  chart_type VARCHAR(50),
  safe BOOLEAN,
  result_preview JSON,
  created_at TIMESTAMPTZ
)
"""


def build_analytics_prompt(question: str) -> str:
    """Build the NL-to-SQL analytics prompt sent to Devin."""
    return f"""You are a SQL analytics assistant for Devin remediation metrics.

Convert the user question into safe read-only PostgreSQL.

## Database Schema
{_DB_SCHEMA_DOC}

## Rules
- Only generate SELECT queries. Never generate INSERT, UPDATE, DELETE, DROP, ALTER,
  TRUNCATE, CREATE, COPY, GRANT, or REVOKE statements.
- Only query the whitelisted tables: devin_runs, devin_events, analytics_queries.
- Always include LIMIT unless the query is a pure aggregate (COUNT/SUM/AVG with no GROUP BY).
- Include a chart recommendation in chart_type: table | bar | line | pie | metric.
- Return structured JSON only, matching the required output schema.
- If the question is unsafe or unanswerable from the schema, set safe=false and explain in explanation.

## User Question
{question}
"""
