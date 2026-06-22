"""POST /analytics/query — NL question → Devin SQL → guarded exec → chart JSON."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db, get_db_ro
from app.models import AnalyticsQuery
from app.prompts import build_analytics_prompt
from app.schemas import (
    ANALYTICS_OUTPUT_SCHEMA,
    AnalyticsQueryOut,
    AnalyticsQueryRequest,
)
from app.services.analytics_queries import get_analytics_response
from app.services.sql_guard import SQLGuardError, validate_and_sanitize

router = APIRouter()
logger = logging.getLogger(__name__)


def _to_json_safe(v: Any) -> Any:
    """Convert Postgres types that aren't natively JSON-serializable."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


@router.post(
    "/analytics/query",
    response_model=AnalyticsQueryOut,
    summary="Ask a natural language question about Devin remediation metrics",
)
async def analytics_query(
    request: AnalyticsQueryRequest,
    db: AsyncSession = Depends(get_db),
    db_ro: AsyncSession = Depends(get_db_ro),
):
    """
    Flow:
    1. Build NL-analytics prompt.
    2. Call Devin with structured_output_schema to get SQL + chart meta.
    3. Validate SQL with the safety guard.
    4. Execute on the read-only DB connection.
    5. Persist the query + result preview.
    6. Return chart-ready JSON.
    """
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question must not be empty.")

    # Step 1 & 2: NL → SQL via Devin (with keyword-matched fallback)
    devin_output = await _get_analytics_output(question)
    safe_flag = devin_output.get("safe", True)
    sql_raw = devin_output.get("sql", "")
    chart_type = devin_output.get("chart_type", "table")
    x_axis = devin_output.get("x_axis")
    y_axis = devin_output.get("y_axis")
    explanation = devin_output.get("explanation", "")

    # Step 3: Guard
    sanitized_sql: str | None = None
    guard_error: str | None = None
    if not safe_flag:
        guard_error = f"Devin marked the query as unsafe: {explanation}"
    else:
        try:
            sanitized_sql = validate_and_sanitize(
                sql_raw, default_limit=settings.analytics_row_limit
            )
        except SQLGuardError as exc:
            guard_error = str(exc)
            safe_flag = False

    # Persist the analytics query record (safe or not)
    record = AnalyticsQuery(
        id=uuid.uuid4(),
        user_question=question,
        generated_sql=sql_raw,
        chart_type=chart_type,
        safe=safe_flag and guard_error is None,
        result_preview=None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.flush()

    if guard_error:
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Query rejected by safety guard",
                "reason": guard_error,
                "generated_sql": sql_raw,
                "safe": False,
            },
        )

    # Step 4: Execute read-only
    assert sanitized_sql is not None
    try:
        result = await db_ro.execute(
            text(sanitized_sql).execution_options(
                timeout=settings.analytics_timeout_ms / 1000
            )
        )
        rows_raw = result.fetchall()
        columns = list(result.keys())
        rows: list[list[Any]] = [
            [_to_json_safe(v) for v in r] for r in rows_raw
        ]
    except Exception as exc:
        logger.exception("Read-only query execution failed: %s", sanitized_sql)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query execution failed: {exc}",
        )

    # Step 5: Persist preview (first 5 rows)
    record.result_preview = {
        "columns": columns,
        "rows": rows[:5],
        "total_rows": len(rows),
    }
    await db.commit()

    # Step 6: Return
    return AnalyticsQueryOut(
        chart_type=chart_type,
        x_axis=x_axis,
        y_axis=y_axis,
        columns=columns,
        rows=rows,
        explanation=explanation,
        generated_sql=sanitized_sql,
        safe=True,
    )


async def _get_analytics_output(question: str) -> dict[str, Any]:
    """Get NL→SQL output for the given question.

    Strategy:
    - If the question matches a known keyword pattern with high confidence,
      return the canned response instantly (sub-second, reliable).
    - Otherwise, call Devin for real NL→SQL reasoning (handles free-form questions
      the keyword map can't cover). Hard timeout of 90s; falls back to keyword
      matching on timeout or error.
    """
    # Check keyword match confidence first — if 2+ keywords match, trust it
    canned = _get_canned_if_confident(question)
    if canned is not None:
        return canned

    # Free-form question: use Devin as the NL→SQL reasoning engine
    from app.services.devin_client import RealDevinClient
    import asyncio

    client = RealDevinClient()
    try:
        prompt = build_analytics_prompt(question)
        session = await client.create_session(
            prompt=prompt,
            title=f"Analytics: {question[:60]}",
            tags=["analytics"],
            structured_output_schema=ANALYTICS_OUTPUT_SCHEMA,
        )
        logger.info("Analytics Devin session %s created for: %s", session.session_id, question[:60])
        deadline = 90  # seconds
        interval = 5
        for _ in range(deadline // interval):
            status_resp = await client.get_session(session.session_id)
            devin_status = status_resp.status
            # Promote on output present, same logic as poller
            structured = status_resp.structured_output or {}
            if structured.get("sql") or devin_status in ("finished", "blocked", "failed", "expired"):
                if structured.get("sql"):
                    logger.info("Analytics Devin session returned SQL in %s seconds", _  * interval)
                    return structured
                break
            await asyncio.sleep(interval)
        logger.warning("Analytics Devin session timed out or returned no SQL; falling back to keyword matching")
    except Exception:
        logger.warning("Analytics Devin session failed; falling back to keyword matching", exc_info=True)
    finally:
        await client.aclose()

    return get_analytics_response(question)


def _get_canned_if_confident(question: str) -> dict[str, Any] | None:
    """Return a canned response only when 2+ keywords match (high confidence)."""
    q = question.lower()
    best: dict[str, Any] | None = None
    best_score = 0
    for resp in __import__("app.services.analytics_queries", fromlist=["ANALYTICS_RESPONSES"]).ANALYTICS_RESPONSES:
        score = sum(1 for kw in resp["question_keywords"] if kw in q)
        if score > best_score:
            best_score = score
            best = resp
    # Require at least 2 keyword hits to be confident enough to skip Devin
    if best_score >= 2:
        return best
    return None
