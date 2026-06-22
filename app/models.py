"""SQLAlchemy ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DevinRun(Base):
    __tablename__ = "devin_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_title: Mapped[str] = mapped_column(Text, nullable=False)
    issue_url: Mapped[str] = mapped_column(Text, nullable=False)
    repo: Mapped[str] = mapped_column(String(255), nullable=False)
    source_event: Mapped[str] = mapped_column(String(100), nullable=False, default="github_webhook")
    classification: Mapped[str | None] = mapped_column(String(100))
    priority: Mapped[str | None] = mapped_column(String(50))
    devin_session_id: Mapped[str | None] = mapped_column(String(255))
    devin_session_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="NEW")
    branch_name: Mapped[str | None] = mapped_column(String(255))
    pr_url: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acu_used: Mapped[float | None] = mapped_column(Numeric(10, 4))
    tests_run: Mapped[list | None] = mapped_column(JSON)
    risk_level: Mapped[str | None] = mapped_column(String(50))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    raw_devin_response: Mapped[dict | None] = mapped_column(JSON)
    # For idempotency: track the GitHub delivery ID that created this run
    github_delivery_id: Mapped[str | None] = mapped_column(String(255))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    events: Mapped[list[DevinEvent]] = relationship(
        "DevinEvent", back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_devin_runs_status", "status"),
        Index("ix_devin_runs_issue_number", "issue_number"),
        Index("ix_devin_runs_devin_session_id", "devin_session_id"),
        Index("ix_devin_runs_github_delivery_id", "github_delivery_id"),
    )


class DevinEvent(Base):
    __tablename__ = "devin_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devin_runs.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    run: Mapped[DevinRun] = relationship("DevinRun", back_populates="events")

    __table_args__ = (Index("ix_devin_events_run_id", "run_id"),)


class AnalyticsQuery(Base):
    __tablename__ = "analytics_queries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_question: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[str | None] = mapped_column(Text)
    chart_type: Mapped[str | None] = mapped_column(String(50))
    safe: Mapped[bool | None] = mapped_column(Boolean)
    result_preview: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
