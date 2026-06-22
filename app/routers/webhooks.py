"""POST /webhooks/github and POST /simulate/issue-labeled."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas import GitHubIssuePayload, OrchestratorTriggerOut, SimulateIssueLabeledRequest
from app.services.github_client import GitHubClient, verify_webhook_signature
from app.services.orchestrator import handle_issue_labeled, handle_simulate

router = APIRouter()
logger = logging.getLogger(__name__)

_github_client = GitHubClient()


@router.post("/webhooks/github", status_code=status.HTTP_200_OK)
async def github_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
):
    """Receive and process GitHub webhook events.

    - Verifies the HMAC-SHA256 signature.
    - Handles `issues.labeled` events for the auto-remediate label.
    """
    raw_body = await request.body()

    from app.config import settings as _settings
    if not _settings.skip_webhook_signature and not verify_webhook_signature(raw_body, x_hub_signature_256):
        logger.warning(
            "Invalid webhook signature from delivery=%s event=%s",
            x_github_delivery,
            x_github_event,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    if x_github_event == "ping":
        return {"message": "pong"}

    if x_github_event != "issues":
        logger.debug("Ignoring event type: %s", x_github_event)
        return {"message": f"Ignored event type: {x_github_event}"}

    try:
        import json
        body = json.loads(raw_body)
        payload = GitHubIssuePayload(**body)
    except Exception as exc:
        logger.exception("Failed to parse webhook payload")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid payload: {exc}",
        )

    if payload.action != "labeled":
        return {"message": f"Ignored action: {payload.action}"}

    run = await handle_issue_labeled(db, _github_client, payload, x_github_delivery)
    if run is None:
        return {"message": "Skipped (wrong label or duplicate delivery)"}

    return {
        "message": "Remediation run created",
        "run_id": str(run.id),
        "status": run.status,
    }


@router.post(
    "/simulate/issue-labeled",
    response_model=OrchestratorTriggerOut,
    summary="Simulate an issue-labeled event (no signature required)",
)
async def simulate_issue_labeled(
    request: SimulateIssueLabeledRequest,
    db: AsyncSession = Depends(get_db),
):
    """Trigger the automation as if a GitHub issue was labeled, without needing a real webhook.

    Useful for local development and demo purposes.
    """
    run = await handle_simulate(db, _github_client, request)
    if run is None:
        return OrchestratorTriggerOut(
            run_id="",
            message="Skipped (duplicate or active session already exists for this issue)",
            status="skipped",
        )
    return OrchestratorTriggerOut(
        run_id=str(run.id),
        message=f"Remediation run created for issue #{request.issue_number}",
        status=run.status,
    )
