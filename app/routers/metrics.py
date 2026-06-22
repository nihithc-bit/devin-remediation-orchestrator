"""GET /metrics/summary, /metrics/throughput, /metrics/failures."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, extract, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import DevinRun
from app.schemas import FailureEntry, FailuresOut, MetricsSummaryOut, ThroughputEntry, ThroughputOut
from app.state import TERMINAL_STATUSES, RunStatus

router = APIRouter()
logger = logging.getLogger(__name__)

_SUCCESS_STATUSES = [
    RunStatus.PR_OPENED.value,
    RunStatus.CI_RUNNING.value,
    RunStatus.READY_FOR_REVIEW.value,
    RunStatus.MERGED.value,
]

_FAILURE_STATUSES = [
    RunStatus.BLOCKED.value,
    RunStatus.FAILED.value,
    RunStatus.NEEDS_HUMAN_REVIEW.value,
]

_ACTIVE_STATUSES = [
    RunStatus.QUEUED.value,
    RunStatus.DEVIN_SESSION_CREATED.value,
    RunStatus.RUNNING.value,
]


@router.get(
    "/metrics/summary",
    response_model=MetricsSummaryOut,
    summary="Top-level observability: total/active/success/failure counts and rates",
)
async def metrics_summary(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            func.count(DevinRun.id).label("total"),
            func.sum(case((DevinRun.status.in_(_ACTIVE_STATUSES), 1), else_=0)).label("active"),
            func.sum(case((DevinRun.status.in_(_SUCCESS_STATUSES), 1), else_=0)).label("success"),
            func.sum(case((DevinRun.status.in_(_FAILURE_STATUSES), 1), else_=0)).label("failed"),
            func.avg(
                case(
                    (
                        DevinRun.completed_at.isnot(None),
                        extract("epoch", DevinRun.completed_at - DevinRun.started_at),
                    ),
                    else_=None,
                )
            ).label("mean_secs"),
        )
    )
    row = result.one()
    total = row.total or 0
    success = row.success or 0
    failed = row.failed or 0
    active = row.active or 0

    return MetricsSummaryOut(
        total_runs=total,
        active_runs=active,
        successful_runs=success,
        failed_runs=failed,
        success_rate=round(success / total, 4) if total > 0 else 0.0,
        mean_time_to_pr_seconds=float(row.mean_secs) if row.mean_secs else None,
    )


@router.get(
    "/metrics/throughput",
    response_model=ThroughputOut,
    summary="Runs/PRs started per day or week",
)
async def metrics_throughput(
    db: AsyncSession = Depends(get_db),
    granularity: str = Query(default="week", pattern="^(day|week)$"),
):
    trunc_expr = func.date_trunc(granularity, DevinRun.started_at)

    result = await db.execute(
        select(
            trunc_expr.label("period"),
            func.count(DevinRun.id).label("runs_started"),
            func.sum(
                case((DevinRun.status.in_(_SUCCESS_STATUSES), 1), else_=0)
            ).label("prs_opened"),
        )
        .group_by(trunc_expr)
        .order_by(trunc_expr)
        .limit(104)  # 2 years at weekly granularity
    )
    rows = result.all()
    return ThroughputOut(
        granularity=granularity,
        data=[
            ThroughputEntry(
                period=row.period.strftime("%Y-%m-%d") if isinstance(row.period, datetime) else str(row.period),
                runs_started=row.runs_started or 0,
                prs_opened=row.prs_opened or 0,
            )
            for row in rows
        ],
    )


@router.get(
    "/metrics/failures",
    response_model=FailuresOut,
    summary="Failures grouped by reason + status distribution",
)
async def metrics_failures(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            DevinRun.failure_reason,
            func.count(DevinRun.id).label("count"),
        )
        .where(DevinRun.status.in_(_FAILURE_STATUSES))
        .group_by(DevinRun.failure_reason)
        .order_by(func.count(DevinRun.id).desc())
        .limit(50)
    )
    rows = result.all()
    return FailuresOut(
        data=[
            FailureEntry(reason=row.failure_reason or "unknown", count=row.count)
            for row in rows
        ]
    )
