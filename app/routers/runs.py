"""GET /runs, GET /runs/{id}, POST /runs/{id}/refresh."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models import DevinRun
from app.schemas import RunListOut, RunOut
from app.services.github_client import GitHubClient
from app.services.poller import poll_run

router = APIRouter()
logger = logging.getLogger(__name__)

_github_client = GitHubClient()


@router.get("/runs", response_model=RunListOut, summary="List all remediation runs")
async def list_runs(
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(default=None, description="Filter by status"),
    classification: str | None = Query(default=None, description="Filter by classification"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Return a paginated list of DevinRun records."""
    q = select(DevinRun).options(selectinload(DevinRun.events))
    if status:
        q = q.where(DevinRun.status == status.upper())
    if classification:
        q = q.where(DevinRun.classification == classification)
    q = q.order_by(DevinRun.started_at.desc()).limit(limit).offset(offset)

    result = await db.execute(q)
    runs = result.scalars().all()

    # Total count (without pagination)
    count_q = select(DevinRun)
    if status:
        count_q = count_q.where(DevinRun.status == status.upper())
    if classification:
        count_q = count_q.where(DevinRun.classification == classification)
    count_result = await db.execute(count_q)
    total = len(count_result.scalars().all())

    return RunListOut(total=total, items=[RunOut.model_validate(r) for r in runs])


@router.get(
    "/runs/{run_id}",
    response_model=RunOut,
    summary="Get a single remediation run with event timeline",
)
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DevinRun)
        .where(DevinRun.id == run_id)
        .options(selectinload(DevinRun.events))
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunOut.model_validate(run)


@router.post(
    "/runs/{run_id}/refresh",
    response_model=RunOut,
    summary="Force-poll the Devin session for this run and advance its state",
)
async def refresh_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DevinRun)
        .where(DevinRun.id == run_id)
        .options(selectinload(DevinRun.events))
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    await poll_run(db, run, _github_client)
    await db.commit()
    await db.refresh(run)
    return RunOut.model_validate(run)
