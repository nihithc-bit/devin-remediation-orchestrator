"""Compose and post GitHub issue comments at each workflow stage."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.services.github_client import GitHubClient

logger = logging.getLogger(__name__)


async def post_session_created_comment(
    client: GitHubClient,
    issue_number: int,
    run_id: str,
    session_url: str,
    classification: str,
    priority: str,
) -> dict:
    body = f"""## 🤖 Devin Remediation Started

A Devin session has been created to remediate this issue.

| Field | Value |
|---|---|
| **Session** | [{session_url}]({session_url}) |
| **Run ID** | `{run_id}` |
| **Classification** | `{classification}` |
| **Priority** | `{priority}` |
| **Status** | 🔄 Running |

> Devin will create a branch, make the smallest safe change, run tests/lint/types, and open a PR.
> **No auto-merge** — human review is required before merging.

_Powered by Devin Remediation Orchestrator_
"""
    return await client.post_issue_comment(issue_number, body)


async def post_progress_comment(
    client: GitHubClient,
    issue_number: int,
    status: str,
    message: str = "",
) -> dict:
    icon = {
        "RUNNING": "🔄",
        "BLOCKED": "⚠️",
        "PR_OPENED": "✅",
        "FAILED": "❌",
        "NEEDS_HUMAN_REVIEW": "👀",
        "READY_FOR_REVIEW": "✅",
    }.get(status, "ℹ️")

    body = f"""{icon} **Devin status update:** `{status}`

{message}

_Updated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_
"""
    return await client.post_issue_comment(issue_number, body)


async def post_final_comment(
    client: GitHubClient,
    issue_number: int,
    status: str,
    pr_url: str | None,
    branch_name: str | None,
    tests_run: list[str],
    risk_level: str,
    summary: str,
    blockers: list[str],
    session_url: str,
) -> dict:
    if status in ("fixed",) and pr_url:
        header = "## ✅ Devin Remediation Complete"
        status_line = f"A pull request has been opened and is ready for human review."
        pr_line = f"\n**PR:** [{pr_url}]({pr_url})"
    elif status == "blocked":
        header = "## ⚠️ Devin is Blocked"
        status_line = "Devin was unable to complete the fix. Human intervention required."
        pr_line = ""
    else:
        header = "## ❌ Devin Remediation Failed"
        status_line = "Devin could not fix this issue automatically."
        pr_line = ""

    blockers_section = ""
    if blockers:
        items = "\n".join(f"- {b}" for b in blockers)
        blockers_section = f"\n**Blockers:**\n{items}\n"

    tests_section = ""
    if tests_run:
        items = "\n".join(f"- `{t}`" for t in tests_run)
        tests_section = f"\n**Checks run:**\n{items}\n"

    body = f"""{header}

{status_line}{pr_line}

{f"**Branch:** `{branch_name}`" if branch_name else ""}

**Risk level:** `{risk_level}`

**Summary:** {summary}
{blockers_section}{tests_section}
**Session:** [{session_url}]({session_url})

> ⚠️ **This PR requires human review before merging.** No auto-merge is performed.

_Powered by Devin Remediation Orchestrator_
"""
    return await client.post_issue_comment(issue_number, body)
