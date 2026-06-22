"""Database engines and session factories."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models import Base

# ── Read-write engine (used by the application) ────────────────────────────────
_rw_engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=settings.app_env == "development",
)

AsyncSessionLocal = async_sessionmaker(
    _rw_engine, class_=AsyncSession, expire_on_commit=False
)

# ── Read-only engine (used exclusively by analytics queries) ───────────────────
_ro_engine = create_async_engine(
    settings.database_url_ro,
    pool_pre_ping=True,
    pool_size=5,
    echo=False,
)

AsyncSessionRO = async_sessionmaker(
    _ro_engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db() -> None:
    """Create all tables (create_all fallback; production would use Alembic)."""
    async with _rw_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager yielding a read-write DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for read-write DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_ro() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for read-only DB session (analytics)."""
    async with AsyncSessionRO() as session:
        yield session
