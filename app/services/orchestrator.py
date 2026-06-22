"""Core orchestration logic: webhook event → Devin session → DB → GitHub comment."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import DevinEvent, DevinRun
from app.prompts import build_remediation_prompt
from app.schemas import (
    REMEDIATION_OUTPUT_SCHEMA,
    DevinCreateSessionResponse,
    GitHubIssuePayload,
    SimulateIssueLabeledRequest,
)
from app.services.classifier import classify_issue
from app.services.devin_client import RealDevinClient
from app.services.github_client import GitHubClient
from app.services.reporter import post_session_created_comment
from app.state import RunStatus, assert_transition

logger = logging.getLogger(__name__)


async def handle_issue_labeled(
    db: AsyncSession,
    github: GitHubClient,
    payload: GitHubIssuePayload,
    delivery_id: str | None,
) -> DevinRun | None:
    """Process an issues.labeled webhook event.

    Returns the created DevinRun, or None if skipped (wrong label, duplicate, etc.).
    """
    label_name = (payload.label or {}).get("name", "")
    if label_name != settings.auto_remediate_label:
        logger.debug("Skipping label %r (not %r)", label_name, settings.auto_remediate_label)
        return None

    issue = payload.issue
    issue_number: int = issue["number"]
    issue_title: str = issue.get("title", "")
    issue_body: str = issue.get("body") or ""
    issue_url: str = issue.get("html_url", "")
    repo = f"{payload.repository.get('full_name', settings.github_repo)}"

    # Idempotency: skip if we already handled this delivery
    if delivery_id:
        existing = await db.execute(
            select(DevinRun).where(DevinRun.github_delivery_id == delivery_id)
        )
        if existing.scalar_one_or_none():
            logger.info("Skipping duplicate delivery_id=%s", delivery_id)
            return None

    # One active session per issue: don't create a new run if one is already running
    active_statuses = [
        RunStatus.QUEUED.value,
        RunStatus.DEVIN_SESSION_CREATED.value,
        RunStatus.RUNNING.value,
    ]
    existing_active = await db.execute(
        select(DevinRun).where(
            DevinRun.issue_number == issue_number,
            DevinRun.repo == repo,
            DevinRun.status.in_(active_statuses),
        )
    )
    if existing_active.scalar_one_or_none():
        logger.info("Issue #%s already has an active Devin session; skipping.", issue_number)
        return None

    # Classify
    labels = [lbl.get("name", "") for lbl in issue.get("labels", [])]
    clf = classify_issue(issue_title, issue_body, labels)

    # Create run record
    run = DevinRun(
        id=uuid.uuid4(),
        issue_number=issue_number,
        issue_title=issue_title,
        issue_url=issue_url,
        repo=repo,
        classification=clf.classification,
        priority=clf.priority,
        risk_level=clf.risk_level,
        status=RunStatus.NEW.value,
        github_delivery_id=delivery_id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()  # get the id assigned

    _record_event(db, run.id, "run_created", {"issue_number": issue_number})

    # Transition NEW → QUEUED
    assert_transition(RunStatus.NEW, RunStatus.QUEUED)
    run.status = RunStatus.QUEUED.value
    _record_event(db, run.id, "status_changed", {"from": "NEW", "to": "QUEUED"})

    # Build prompt
    prompt = build_remediation_prompt(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_body=issue_body,
        repo=repo,
        classification=clf.classification,
    )
    idempotency_key = f"{repo}#{issue_number}@{delivery_id or str(run.id)[:8]}"
    title = f"Remediate #{issue_number}: {issue_title[:60]}"
    tags = ["auto-remediate", clf.classification, clf.priority]

    # Create Devin session
    devin = RealDevinClient()
    try:
        session_resp: DevinCreateSessionResponse = await devin.create_session(
            prompt=prompt,
            title=title,
            tags=tags,
            max_acu_limit=settings.max_acu_limit,
            structured_output_schema=REMEDIATION_OUTPUT_SCHEMA,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        logger.exception("Failed to create Devin session for issue #%s", issue_number)
        run.status = RunStatus.FAILED.value
        run.failure_reason = f"Devin session creation failed: {exc}"
        _record_event(db, run.id, "devin_session_error", {"error": str(exc)})
        await db.commit()
        return run

    # Transition QUEUED → DEVIN_SESSION_CREATED → RUNNING
    assert_transition(RunStatus.QUEUED, RunStatus.DEVIN_SESSION_CREATED)
    run.status = RunStatus.DEVIN_SESSION_CREATED.value
    run.devin_session_id = session_resp.session_id
    run.devin_session_url = session_resp.url
    _record_event(
        db,
        run.id,
        "devin_session_created",
        {"session_id": session_resp.session_id, "url": session_resp.url},
    )

    assert_transition(RunStatus.DEVIN_SESSION_CREATED, RunStatus.RUNNING)
    run.status = RunStatus.RUNNING.value
    _record_event(db, run.id, "status_changed", {"from": "DEVIN_SESSION_CREATED", "to": "RUNNING"})

    await db.commit()

    # Post GitHub comment
    try:
        await post_session_created_comment(
            client=github,
            issue_number=issue_number,
            run_id=str(run.id),
            session_url=session_resp.url,
            classification=clf.classification,
            priority=clf.priority,
        )
        _record_event(db, run.id, "github_comment_posted", {"type": "session_created"})
        await db.commit()
    except Exception as exc:
        logger.warning("Failed to post GitHub comment for issue #%s: %s", issue_number, exc)

    logger.info(
        "Run %s created for issue #%s | session=%s",
        run.id,
        issue_number,
        session_resp.session_id,
    )
    return run


async def handle_simulate(
    db: AsyncSession,
    github: GitHubClient,
    request: SimulateIssueLabeledRequest,
) -> DevinRun | None:
    """Simulate the issues.labeled event without a real webhook."""
    fake_payload = GitHubIssuePayload(
        action="labeled",
        issue={
            "number": request.issue_number,
            "title": request.issue_title,
            "body": request.issue_body,
            "html_url": request.issue_url
            or f"https://github.com/{settings.github_owner}/{settings.github_repo}/issues/{request.issue_number}",
            "labels": [{"name": request.label}],
        },
        label={"name": request.label},
        repository={
            "full_name": f"{settings.github_owner}/{settings.github_repo}",
        },
        sender={"login": "simulation"},
    )
    delivery_id = f"sim-{uuid.uuid4().hex[:12]}"
    return await handle_issue_labeled(db, github, fake_payload, delivery_id)


def _record_event(
    db: AsyncSession,
    run_id: uuid.UUID,
    event_type: str,
    payload: dict,
) -> None:
    event = DevinEvent(
        id=uuid.uuid4(),
        run_id=run_id,
        event_type=event_type,
        event_payload=payload,
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
