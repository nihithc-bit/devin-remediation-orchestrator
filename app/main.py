"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.routers import analytics, metrics, runs, webhooks

logging.basicConfig(
    level=logging.DEBUG if settings.app_env == "development" else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Devin Remediation Orchestrator")
    await init_db()
    logger.info("Database initialized.")
    yield
    logger.info("Shutting down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Devin Remediation Orchestrator",
        description=(
            "Event-driven automation that remediates GitHub issues using Devin. "
            "Includes a conversational analytics layer (Devin as NL→SQL engine)."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # API routers
    app.include_router(webhooks.router, tags=["Webhooks"])
    app.include_router(runs.router, tags=["Runs"])
    app.include_router(metrics.router, tags=["Metrics"])
    app.include_router(analytics.router, tags=["Analytics"])

    # Serve single-page dashboard at root
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def root():
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"message": "Devin Remediation Orchestrator", "docs": "/docs"}

    @app.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
