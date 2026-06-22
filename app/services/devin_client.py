"""Real Devin API v1 client."""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.config import settings
from app.schemas import (
    DevinCreateSessionResponse,
    DevinSessionStatus,
)


class DevinClientProtocol(Protocol):
    """Interface for the Devin API v1 client."""

    async def create_session(
        self,
        prompt: str,
        title: str | None = None,
        tags: list[str] | None = None,
        max_acu_limit: int | None = None,
        structured_output_schema: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> DevinCreateSessionResponse: ...

    async def get_session(self, session_id: str) -> DevinSessionStatus: ...

    async def send_message(self, session_id: str, message: str) -> None: ...


class RealDevinClient:
    """HTTP client for the Devin v1 API."""

    BASE_URL = "https://api.devin.ai/v1"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {settings.devin_api_key}"},
            timeout=30.0,
        )

    async def create_session(
        self,
        prompt: str,
        title: str | None = None,
        tags: list[str] | None = None,
        max_acu_limit: int | None = None,
        structured_output_schema: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> DevinCreateSessionResponse:
        payload: dict[str, Any] = {"prompt": prompt}
        if title:
            payload["title"] = title
        if tags:
            payload["tags"] = tags
        if max_acu_limit:
            payload["max_acu_limit"] = max_acu_limit
        if structured_output_schema:
            payload["structured_output_schema"] = structured_output_schema
        if idempotency_key:
            payload["idempotent"] = True
            # Devin uses the session title + idempotent flag for dedup;
            # we also embed the key in the title to make it globally unique.
            payload["title"] = f"{title or 'session'} [{idempotency_key[:8]}]"

        resp = await self._client.post("/sessions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return DevinCreateSessionResponse(**data)

    async def get_session(self, session_id: str) -> DevinSessionStatus:
        resp = await self._client.get(f"/sessions/{session_id}")
        resp.raise_for_status()
        data = resp.json()
        return DevinSessionStatus(
            session_id=data["session_id"],
            status=data["status"],
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            structured_output=data.get("structured_output"),
            pull_request=data.get("pull_request"),
        )

    async def send_message(self, session_id: str, message: str) -> None:
        resp = await self._client.post(
            f"/sessions/{session_id}/messages",
            json={"message": message},
        )
        resp.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()
