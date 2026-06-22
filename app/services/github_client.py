"""GitHub API client for issue comments, labels, and webhook helpers."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class GitHubClient:
    """Minimal async GitHub client using the REST API directly."""

    BASE_URL = "https://api.github.com"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15.0,
        )

    @property
    def _repo(self) -> str:
        return f"{settings.github_owner}/{settings.github_repo}"

    async def post_issue_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        """Post a markdown comment on a GitHub issue."""
        resp = await self._client.post(
            f"/repos/{self._repo}/issues/{issue_number}/comments",
            json={"body": body},
        )
        resp.raise_for_status()
        return resp.json()

    async def update_issue_comment(self, comment_id: int, body: str) -> dict[str, Any]:
        """Update an existing issue comment."""
        resp = await self._client.patch(
            f"/repos/{self._repo}/issues/comments/{comment_id}",
            json={"body": body},
        )
        resp.raise_for_status()
        return resp.json()

    async def add_label(self, issue_number: int, label: str) -> None:
        """Add a label to an issue."""
        resp = await self._client.post(
            f"/repos/{self._repo}/issues/{issue_number}/labels",
            json={"labels": [label]},
        )
        resp.raise_for_status()

    async def get_issue(self, issue_number: int) -> dict[str, Any]:
        """Fetch issue metadata."""
        resp = await self._client.get(f"/repos/{self._repo}/issues/{issue_number}")
        resp.raise_for_status()
        return resp.json()

    async def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create an issue (used by the seed script)."""
        resp = await self._client.post(
            f"/repos/{self._repo}/issues",
            json={"title": title, "body": body, "labels": labels or []},
        )
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self._client.aclose()


# ── Webhook signature verification ────────────────────────────────────────────

def verify_webhook_signature(payload_bytes: bytes, signature_header: str | None) -> bool:
    """Verify the X-Hub-Signature-256 header using constant-time comparison."""
    if not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected_sig = signature_header[7:]
    computed = hmac.new(
        settings.github_webhook_secret.encode(),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, expected_sig)
