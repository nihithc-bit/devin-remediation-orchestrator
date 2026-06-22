"""Unit tests for the run state machine."""

import pytest

from app.state import InvalidTransitionError, RunStatus, assert_transition


# ── Valid transitions ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("old, new", [
    (RunStatus.NEW, RunStatus.QUEUED),
    (RunStatus.QUEUED, RunStatus.DEVIN_SESSION_CREATED),
    (RunStatus.DEVIN_SESSION_CREATED, RunStatus.RUNNING),
    (RunStatus.RUNNING, RunStatus.PR_OPENED),
    (RunStatus.RUNNING, RunStatus.BLOCKED),
    (RunStatus.RUNNING, RunStatus.FAILED),
    (RunStatus.RUNNING, RunStatus.NEEDS_HUMAN_REVIEW),
    (RunStatus.PR_OPENED, RunStatus.READY_FOR_REVIEW),
    (RunStatus.RUNNING, RunStatus.READY_FOR_REVIEW),   # Devin finishes in one shot
    (RunStatus.READY_FOR_REVIEW, RunStatus.MERGED),
    (RunStatus.BLOCKED, RunStatus.QUEUED),
    # idempotent re-RUNNING
    (RunStatus.RUNNING, RunStatus.RUNNING),
])
def test_valid_transition(old: RunStatus, new: RunStatus):
    assert_transition(old, new)  # must not raise


# ── Invalid transitions ────────────────────────────────────────────────────────

@pytest.mark.parametrize("old, new", [
    (RunStatus.NEW, RunStatus.RUNNING),                    # must go through QUEUED
    (RunStatus.MERGED, RunStatus.QUEUED),                  # terminal
    (RunStatus.MERGED, RunStatus.RUNNING),                 # terminal
    (RunStatus.NEEDS_HUMAN_REVIEW, RunStatus.RUNNING),     # terminal
    (RunStatus.READY_FOR_REVIEW, RunStatus.NEW),           # can't go backwards
    (RunStatus.RUNNING, RunStatus.DEVIN_SESSION_CREATED),  # wrong direction
    (RunStatus.RUNNING, RunStatus.MERGED),                 # must pass through READY_FOR_REVIEW
])
def test_invalid_transition(old: RunStatus, new: RunStatus):
    with pytest.raises(InvalidTransitionError):
        assert_transition(old, new)


def test_error_message_contains_statuses():
    with pytest.raises(InvalidTransitionError) as exc_info:
        assert_transition(RunStatus.NEW, RunStatus.RUNNING)
    msg = str(exc_info.value)
    assert "NEW" in msg
    assert "RUNNING" in msg
