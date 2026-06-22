"""Run state machine: status enum + allowed transitions."""

from __future__ import annotations

from enum import Enum


class RunStatus(str, Enum):
    # Happy path
    NEW = "NEW"
    QUEUED = "QUEUED"
    DEVIN_SESSION_CREATED = "DEVIN_SESSION_CREATED"
    RUNNING = "RUNNING"
    PR_OPENED = "PR_OPENED"
    CI_RUNNING = "CI_RUNNING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    MERGED = "MERGED"  # set manually by humans; never auto-set by orchestrator
    # Failure states
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


TERMINAL_STATUSES: frozenset[RunStatus] = frozenset(
    {
        RunStatus.READY_FOR_REVIEW,
        RunStatus.MERGED,
        RunStatus.BLOCKED,
        RunStatus.FAILED,
        RunStatus.NEEDS_HUMAN_REVIEW,
    }
)

# Allowed forward transitions (source → set of valid targets)
TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.NEW: {RunStatus.QUEUED, RunStatus.FAILED},
    RunStatus.QUEUED: {
        RunStatus.DEVIN_SESSION_CREATED,
        RunStatus.FAILED,
        RunStatus.BLOCKED,
    },
    RunStatus.DEVIN_SESSION_CREATED: {
        RunStatus.RUNNING,
        RunStatus.FAILED,
        RunStatus.BLOCKED,
    },
    RunStatus.RUNNING: {
        RunStatus.PR_OPENED,
        RunStatus.READY_FOR_REVIEW,   # Devin finishes + PR in one shot (skips PR_OPENED)
        RunStatus.BLOCKED,
        RunStatus.FAILED,
        RunStatus.NEEDS_HUMAN_REVIEW,
        RunStatus.RUNNING,            # no-op on poll cycle
    },
    RunStatus.PR_OPENED: {
        RunStatus.CI_RUNNING,
        RunStatus.READY_FOR_REVIEW,
        RunStatus.NEEDS_HUMAN_REVIEW,
    },
    RunStatus.CI_RUNNING: {
        RunStatus.READY_FOR_REVIEW,
        RunStatus.NEEDS_HUMAN_REVIEW,
        RunStatus.FAILED,
    },
    RunStatus.READY_FOR_REVIEW: {RunStatus.MERGED},
    RunStatus.MERGED: set(),
    RunStatus.BLOCKED: {RunStatus.QUEUED, RunStatus.NEEDS_HUMAN_REVIEW},
    RunStatus.FAILED: {RunStatus.QUEUED},
    RunStatus.NEEDS_HUMAN_REVIEW: set(),
}


class InvalidTransitionError(Exception):
    """Raised when an attempted status transition is not allowed."""


def assert_transition(old: RunStatus, new: RunStatus) -> None:
    """Raise InvalidTransitionError if the transition old→new is not allowed."""
    allowed = TRANSITIONS.get(old, set())
    if new not in allowed:
        raise InvalidTransitionError(
            f"Transition {old.value!r} → {new.value!r} is not allowed. "
            f"Allowed from {old.value!r}: {[s.value for s in allowed]}"
        )


# Map Devin session status strings to RunStatus
DEVIN_STATUS_MAP: dict[str, RunStatus] = {
    "running": RunStatus.RUNNING,
    "working": RunStatus.RUNNING,
    "suspended": RunStatus.RUNNING,   # Devin-internal pause state; session may still have output
    "blocked": RunStatus.BLOCKED,
    "finished": RunStatus.PR_OPENED,  # refined in poller based on structured_output
    "expired": RunStatus.FAILED,
    "suspend_requested": RunStatus.RUNNING,
    "suspend_requested_frontend": RunStatus.RUNNING,
    "resume_requested": RunStatus.RUNNING,
    "resume_requested_frontend": RunStatus.RUNNING,
    "resumed": RunStatus.RUNNING,
}
