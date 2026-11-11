"""Database engine and session management for SQLAlchemy 2.x."""

import logging
from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger("incidentlens.db")

# Setup async engine
is_sqlite = settings.DATABASE_URL.startswith("sqlite")
async_connect_args = {"check_same_thread": False} if is_sqlite else {}

async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    connect_args=async_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# Setup sync engine (used by Celery tasks & migrations)
sync_is_sqlite = settings.DATABASE_SYNC_URL.startswith("sqlite")
sync_connect_args = {"check_same_thread": False} if sync_is_sqlite else {}

sync_engine = create_engine(
    settings.DATABASE_SYNC_URL,
    echo=False,
    connect_args=sync_connect_args,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for obtaining an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@contextmanager
def get_sync_db() -> Generator[Session, None, None]:
    """Context manager for obtaining a sync database session (Celery workers)."""
    session = SyncSessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def check_db_health(engine: AsyncEngine | None = None) -> bool:
    """Check connectivity to database by executing a simple query."""
    target_engine = engine or async_engine
    try:
        async with target_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning(f"Database readiness probe failed: {exc}")
        return False
