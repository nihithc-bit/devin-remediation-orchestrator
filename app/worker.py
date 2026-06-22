"""Background worker: poll active Devin sessions on a fixed interval."""

from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.db import init_db
from app.services.poller import poll_all_active_runs

logging.basicConfig(
    level=logging.DEBUG if settings.app_env == "development" else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run_worker() -> None:
    await init_db()
    logger.info("Worker started (interval=%ds)", settings.poll_interval_seconds)
    while True:
        try:
            await poll_all_active_runs()
        except Exception:
            logger.exception("Poll cycle failed; will retry next interval.")
        await asyncio.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_worker())
