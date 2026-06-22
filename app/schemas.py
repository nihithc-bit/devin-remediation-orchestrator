"""Pydantic request/response schemas + Devin structured-output JSON Schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Devin structured output schemas (JSON Schema Draft 7 for the API) ──────────

#: Schema passed to POST /v1/sessions structured_output_schema for remediation tasks.
REMEDIATION_OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["issue_number", "status", "risk_level", "summary"],
    "properties": {
        "issue_number": {"type": "integer"},
        "status": {
            "type": "string",
            "enum": ["fixed", "blocked", "failed", "needs_human_review"],
        },
        "pr_url": {"type": ["string", "null"]},
        "branch_name": {"type": ["string", "null"]},
        "tests_run": {"type": "array", "items": {"type": "string"}},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "summary": {"type": "string"},
        "blockers": {"type": "array", "items": {"type": "string"}},
    },
}

#: Schema passed to POST /v1/sessions for NL-to-SQL analytics.
ANALYTICS_OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["safe", "sql", "chart_type", "explanation"],
    "properties": {
        "safe": {"type": "boolean"},
        "sql": {"type": "string"},
        "chart_type": {
            "type": "string",
            "enum": ["table", "bar", "line", "pie", "metric"],
        },
        "x_axis": {"type": ["string", "null"]},
        "y_axis": {"type": ["string", "null"]},
        "explanation": {"type": "string"},
    },
}


# ── Devin client response models ───────────────────────────────────────────────

class DevinCreateSessionResponse(BaseModel):
    session_id: str
    url: str
    is_new_session: bool | None = None


class DevinRemediationOutput(BaseModel):
    issue_number: int
    status: str
    pr_url: str | None = None
    branch_name: str | None = None
    tests_run: list[str] = Field(default_factory=list)
    risk_level: str = "medium"
    summary: str = ""
    blockers: list[str] = Field(default_factory=list)


class DevinAnalyticsOutput(BaseModel):
    safe: bool
    sql: str
    chart_type: str
    x_axis: str | None = None
    y_axis: str | None = None
    explanation: str


class DevinSessionStatus(BaseModel):
    session_id: str
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    structured_output: dict[str, Any] | None = None
    pull_request: dict[str, Any] | None = None  # {"url": "..."}


# ── GitHub webhook payloads ────────────────────────────────────────────────────

class GitHubIssuePayload(BaseModel):
    """Minimal structure of the GitHub issues.labeled webhook payload."""

    action: str
    issue: dict[str, Any]
    label: dict[str, Any] | None = None
    repository: dict[str, Any]
    sender: dict[str, Any]


class SimulateIssueLabeledRequest(BaseModel):
    issue_number: int
    issue_title: str
    issue_body: str = ""
    issue_url: str = ""
    label: str = "devin:auto-remediate"


# ── API response models ────────────────────────────────────────────────────────

class RunEventOut(BaseModel):
    id: uuid.UUID
    event_type: str
    event_payload: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: uuid.UUID
    issue_number: int
    issue_title: str
    issue_url: str
    repo: str
    classification: str | None
    priority: str | None
    status: str
    devin_session_id: str | None
    devin_session_url: str | None
    branch_name: str | None
    pr_url: str | None
    started_at: datetime
    completed_at: datetime | None
    acu_used: float | None
    risk_level: str | None
    failure_reason: str | None
    events: list[RunEventOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class RunListOut(BaseModel):
    total: int
    items: list[RunOut]


class MetricsSummaryOut(BaseModel):
    total_runs: int
    active_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float
    mean_time_to_pr_seconds: float | None


class ThroughputEntry(BaseModel):
    period: str
    runs_started: int
    prs_opened: int


class ThroughputOut(BaseModel):
    granularity: str
    data: list[ThroughputEntry]


class FailureEntry(BaseModel):
    reason: str
    count: int


class FailuresOut(BaseModel):
    data: list[FailureEntry]


class AnalyticsQueryRequest(BaseModel):
    question: str


class AnalyticsQueryOut(BaseModel):
    chart_type: str
    x_axis: str | None
    y_axis: str | None
    columns: list[str]
    rows: list[list[Any]]
    explanation: str
    generated_sql: str
    safe: bool


class OrchestratorTriggerOut(BaseModel):
    run_id: str
    message: str
    status: str
