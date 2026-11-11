"""Pytest configuration and shared test fixtures."""

import os
import sys
from pathlib import Path

# Ensure repository root is on sys.path for simulator/eval access
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

os.environ["TESTING"] = "1"

from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

import app.db.session as session_module
from app.db.base import Base
from app.db.session import get_db
from app.main import app as main_app
from app.workers.celery_app import celery_app

# Shared file-based SQLite database for both async API and sync Celery workers
TEST_DB_PATH = Path("test_incidentlens.db")
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH.name}"
TEST_SYNC_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.name}"

test_async_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

TestingAsyncSessionLocal = async_sessionmaker(
    bind=test_async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

test_sync_engine = create_engine(
    TEST_SYNC_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

TestingSyncSessionLocal = sessionmaker(
    bind=test_sync_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# Redirect global sync session in app.db.session to test sync database for Celery
session_module.SyncSessionLocal = TestingSyncSessionLocal


@pytest_asyncio.fixture
async def init_test_db() -> AsyncGenerator[None, None]:
    """Initialize database schema per test."""
    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session(init_test_db: None) -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean, isolated database session per test."""
    async with TestingAsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an HTTPX AsyncClient configured with test database session overrides."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestingAsyncSessionLocal() as session:
            yield session

    main_app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=main_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    main_app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def configure_celery_test_mode() -> Generator[None, None, None]:
    """Configure Celery to run in-memory and eager during tests."""
    original_eager = celery_app.conf.task_always_eager
    original_propagate = celery_app.conf.task_eager_propagates
    original_broker = celery_app.conf.broker_url
    original_backend = celery_app.conf.result_backend

    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        broker_url="memory://",
        result_backend="cache+memory://",
    )
    yield
    celery_app.conf.update(
        task_always_eager=original_eager,
        task_eager_propagates=original_propagate,
        broker_url=original_broker,
        result_backend=original_backend,
    )
