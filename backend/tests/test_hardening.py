"""Tests for Phase 11: Security Hardening, Performance Indexes, and Event Retention."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import _normalize_async_db_url, _normalize_sync_db_url
from app.db.session import get_sync_db
from app.models.log_event import LogEvent
from app.workers.tasks import cleanup_old_events_task


async def _setup_user_and_project(client: AsyncClient) -> tuple[str, str]:
    uid = uuid.uuid4().hex[:6]
    reg = await client.post(
        "/api/v1/auth/register",
        json={"name": f"Hardening {uid}", "email": f"hard_{uid}@example.com", "password": "Password123!"},
    )
    token = reg.json()["access_token"]
    proj = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Hardening Test Project"},
    )
    return token, proj.json()["id"]


@pytest.mark.asyncio
async def test_security_headers_present(client: AsyncClient):
    """Verify OWASP security headers are set on HTTP responses."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "Permissions-Policy" in resp.headers


@pytest.mark.asyncio
async def test_upload_extension_and_binary_validation(client: AsyncClient):
    """Verify executable extensions and binary payloads are rejected cleanly."""
    token, project_id = await _setup_user_and_project(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Disallowed extension (.exe / .sh)
    bad_ext = await client.post(
        f"/api/v1/projects/{project_id}/logs/upload",
        files={"file": ("malware.exe", b"2026-01-01 INFO harmless", "application/octet-stream")},
        headers=headers,
    )
    assert bad_ext.status_code == 400
    assert bad_ext.json()["error"]["code"] == "BAD_REQUEST"

    # 2. Allowed extension (.log) containing binary null bytes
    binary_spoof = await client.post(
        f"/api/v1/projects/{project_id}/logs/upload",
        files={"file": ("fake.log", b"\x7fELF\x00\x00\x00binary_payload", "text/plain")},
        headers=headers,
    )
    assert binary_spoof.status_code == 400
    assert "Binary files are not permitted" in binary_spoof.json()["error"]["message"]


def test_unhandled_error_never_leaks_stack_trace_in_production():
    """Verify FastAPI app with debug=False masks internal exception tracebacks."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.errors import register_error_handlers

    prod_app = FastAPI()
    register_error_handlers(prod_app, debug=False)

    @prod_app.get("/boom")
    def crash():
        raise RuntimeError("Sensitive DB connection string secret_password_123")

    tc = TestClient(prod_app, raise_server_exceptions=False)
    res = tc.get("/boom")
    assert res.status_code == 500
    body = res.json()
    assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert body["error"]["message"] == "An internal server error occurred"
    assert "secret_password_123" not in res.text
    assert "Traceback" not in res.text


@pytest.mark.asyncio
async def test_database_index_usage_via_explain(client: AsyncClient):
    """Verify composite indexes exist and are utilized by SQL query planner."""
    _, project_id_str = await _setup_user_and_project(client)
    project_hex = uuid.UUID(project_id_str).hex

    with get_sync_db() as db:
        # 1. Check log_events (project_id, ts) index usage
        plan_ts = db.execute(
            text(
                f"EXPLAIN QUERY PLAN SELECT id, message FROM log_events "
                f"WHERE project_id = '{project_hex}' AND ts >= '2026-01-01' ORDER BY ts DESC LIMIT 50"
            )
        ).fetchall()
        plan_ts_str = " ".join(str(r) for r in plan_ts)
        assert "ix_log_events_project_ts" in plan_ts_str

        # 2. Check log_events (project_id, pattern_id) index usage
        plan_pat = db.execute(
            text(
                f"EXPLAIN QUERY PLAN SELECT id FROM log_events "
                f"WHERE project_id = '{project_hex}' AND pattern_id IS NOT NULL"
            )
        ).fetchall()
        plan_pat_str = " ".join(str(r) for r in plan_pat)
        assert "ix_log_events_project_pattern" in plan_pat_str


@pytest.mark.asyncio
async def test_event_retention_cleanup_and_isolation(client: AsyncClient):
    """Verify retention cleanup deletes expired events, preserves recent events, and enforces ownership."""
    token_a, proj_a_str = await _setup_user_and_project(client)
    token_b, _ = await _setup_user_and_project(client)
    proj_a_id = uuid.UUID(proj_a_str)
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    now = datetime.now(UTC)
    old_ts = now - timedelta(days=45)
    recent_ts = now - timedelta(days=2)

    with get_sync_db() as db:
        db.add_all([
            LogEvent(
                project_id=proj_a_id,
                batch_id=uuid.uuid4(),
                ts=old_ts,
                service="auth-service",
                level="INFO",
                message="Expired old event 1",
                raw_line="old1",
            ),
            LogEvent(
                project_id=proj_a_id,
                batch_id=uuid.uuid4(),
                ts=old_ts,
                service="auth-service",
                level="ERROR",
                message="Expired old event 2",
                raw_line="old2",
            ),
            LogEvent(
                project_id=proj_a_id,
                batch_id=uuid.uuid4(),
                ts=recent_ts,
                service="auth-service",
                level="INFO",
                message="Fresh active event",
                raw_line="fresh",
            ),
        ])
        db.commit()

    # 1. Tenant isolation: User B cannot run retention cleanup on User A's project -> 404
    unauth = await client.post(
        f"/api/v1/projects/{proj_a_str}/events/retention-cleanup?retention_days=30",
        headers=headers_b,
    )
    assert unauth.status_code == 404

    # 2. User A purges events older than 30 days
    purge_resp = await client.post(
        f"/api/v1/projects/{proj_a_str}/events/retention-cleanup?retention_days=30",
        headers=headers_a,
    )
    assert purge_resp.status_code == 200
    assert purge_resp.json()["deleted_count"] == 2

    # 3. Verify only the fresh event remains
    remaining = await client.get(f"/api/v1/projects/{proj_a_str}/events", headers=headers_a)
    assert remaining.json()["total"] == 1
    assert remaining.json()["items"][0]["message"] == "Fresh active event"

    # 4. Also verify Celery scheduled background task executes cleanly with 1-day retention
    task_res = cleanup_old_events_task(retention_days=1)
    assert task_res["deleted_count"] == 1


def test_cloud_database_url_normalization():
    """Verify postgres:// URIs from Render/Railway/Neon normalize to asyncpg & psycopg."""
    raw_pg = "postgres://user:pass@db.render.com:5432/incidentlens"
    assert _normalize_async_db_url(raw_pg) == "postgresql+asyncpg://user:pass@db.render.com:5432/incidentlens"
    assert _normalize_sync_db_url(raw_pg) == "postgresql+psycopg://user:pass@db.render.com:5432/incidentlens"


def test_alembic_revision_ids_fit_varchar_32():
    """Verify all Alembic revision IDs fit within default VARCHAR(32) alembic_version column."""
    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    scripts = list(ScriptDirectory.from_config(cfg).walk_revisions())
    assert len(scripts) >= 7
    for script in scripts:
        assert len(script.revision) <= 32, f"Revision ID too long for VARCHAR(32): {script.revision}"
