"""Background poller: poll active Devin sessions, advance state machine, update GitHub."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db_session
from app.models import DevinEvent, DevinRun
from app.schemas import DevinRemediationOutput
from app.services.devin_client import RealDevinClient
from app.services.github_client import GitHubClient
from app.services.reporter import post_final_comment, post_progress_comment
from app.state import (
    DEVIN_STATUS_MAP,
    TERMINAL_STATUSES,
    RunStatus,
    assert_transition,
    InvalidTransitionError,
)

logger = logging.getLogger(__name__)


def get_devin_client():
    return RealDevinClient()


async def poll_run(db: AsyncSession, run: DevinRun, github: GitHubClient) -> None:
    """Poll a single Devin session and advance the run's state."""
    if not run.devin_session_id:
        logger.warning("Run %s has no session_id; skipping poll.", run.id)
        return

    devin = get_devin_client()
    try:
        session = await devin.get_session(run.devin_session_id)
    except Exception as exc:
        logger.exception("Poll failed for run %s session %s", run.id, run.devin_session_id)
        _record_event(db, run.id, "poll_error", {"error": str(exc)})
        return

    devin_status = session.status
    new_run_status = DEVIN_STATUS_MAP.get(devin_status)

    if new_run_status is None:
        logger.warning("Unknown Devin status %r for run %s", devin_status, run.id)
        return

    current_status = RunStatus(run.status)

    # Promote based on structured_output / pull_request even before Devin sets status=finished.
    # Real Devin sessions can remain "running" or "suspended" while already having delivered output.
    structured = session.structured_output or {}
    devin_outcome = structured.get("status", "")
    pr_url = structured.get("pr_url") or (session.pull_request or {}).get("url")

    if devin_status == "finished" or pr_url or devin_outcome in ("fixed", "blocked", "failed", "needs_human_review"):
        if devin_outcome in ("blocked",):
            new_run_status = RunStatus.BLOCKED
        elif devin_outcome in ("failed", "needs_human_review"):
            new_run_status = RunStatus.NEEDS_HUMAN_REVIEW
        elif pr_url:
            new_run_status = RunStatus.READY_FOR_REVIEW
        elif devin_status not in ("running", "working", "suspended",
                                   "suspend_requested", "resume_requested", "resumed",
                                   "suspend_requested_frontend", "resume_requested_frontend"):
            new_run_status = RunStatus.NEEDS_HUMAN_REVIEW

    if new_run_status == current_status:
        return  # No change — no-op

    # Validate transition
    try:
        assert_transition(current_status, new_run_status)
    except InvalidTransitionError:
        logger.warning(
            "Invalid transition %s→%s for run %s; skipping.",
            current_status,
            new_run_status,
            run.id,
        )
        return

    old_status = run.status
    run.status = new_run_status.value
    _record_event(
        db,
        run.id,
        "status_changed",
        {"from": old_status, "to": new_run_status.value, "devin_status": devin_status},
    )

    # Persist structured output fields
    if session.structured_output:
        try:
            out = DevinRemediationOutput(**session.structured_output)
            run.pr_url = out.pr_url
            run.branch_name = out.branch_name
            run.tests_run = out.tests_run
            run.risk_level = out.risk_level
            run.raw_devin_response = session.structured_output
            if out.status in ("blocked", "failed", "needs_human_review"):
                run.failure_reason = "; ".join(out.blockers) or out.summary
        except Exception as exc:
            logger.warning("Could not parse structured output for run %s: %s", run.id, exc)
            run.raw_devin_response = session.structured_output

    # Set PR url from pull_request field if not in structured_output
    if not run.pr_url and session.pull_request:
        run.pr_url = session.pull_request.get("url")

    # Mark completed for terminal states
    if new_run_status in TERMINAL_STATUSES:
        run.completed_at = datetime.now(timezone.utc)

    await db.flush()

    # Post GitHub comment
    structured = session.structured_output or {}
    try:
        if new_run_status in TERMINAL_STATUSES:
            await post_final_comment(
                client=github,
                issue_number=run.issue_number,
                status=structured.get("status", new_run_status.value.lower()),
                pr_url=run.pr_url,
                branch_name=run.branch_name,
                tests_run=run.tests_run or [],
                risk_level=run.risk_level or "unknown",
                summary=structured.get("summary", ""),
                blockers=structured.get("blockers", []),
                session_url=run.devin_session_url or "",
            )
        elif old_status != new_run_status.value:
            await post_progress_comment(
                client=github,
                issue_number=run.issue_number,
                status=new_run_status.value,
                message=structured.get("summary", ""),
            )
        _record_event(db, run.id, "github_comment_posted", {"status": new_run_status.value})
    except Exception as exc:
        logger.warning("Failed to post GitHub comment for run %s: %s", run.id, exc)


async def poll_all_active_runs() -> None:
    """Poll every non-terminal run. Called by the worker loop."""
    github = GitHubClient()
    async with get_db_session() as db:
        result = await db.execute(
            select(DevinRun).where(
                DevinRun.status.notin_([s.value for s in TERMINAL_STATUSES]),
                DevinRun.devin_session_id.isnot(None),
            )
        )
        runs = result.scalars().all()
        logger.info("Polling %d active runs.", len(runs))
        for run in runs:
            await poll_run(db, run, github)
    await github.aclose()


def _record_event(db: AsyncSession, run_id: uuid.UUID, event_type: str, payload: dict) -> None:
    event = DevinEvent(
        id=uuid.uuid4(),
        run_id=run_id,
        event_type=event_type,
        event_payload=payload,
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
