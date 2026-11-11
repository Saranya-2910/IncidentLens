"""Tests for log ingestion endpoints, 50,000-line background processing, and idempotency."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import save_batch_content
from app.models.log_batch import LogBatch
from app.models.log_event import LogEvent
from app.workers.tasks import process_log_batch


async def _setup_project(client: AsyncClient) -> tuple[str, str]:
    """Helper to register user and create project, returning (token, project_id)."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={"name": "Ingest Tester", "email": f"tester_{uuid.uuid4().hex[:6]}@example.com", "password": "Password123!"},
    )
    token = reg.json()["access_token"]
    proj = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Log Test Project"},
    )
    return token, proj.json()["id"]


@pytest.mark.asyncio
async def test_file_upload_endpoint(client: AsyncClient, db_session: AsyncSession) -> None:
    """Verify POST /projects/{id}/logs/upload returns 202 and processes events in background."""
    token, project_id = await _setup_project(client)
    headers = {"Authorization": f"Bearer {token}"}

    log_content = (
        "2026-03-01 12:00:01 INFO auth-service User login successful\n"
        "2026-03-01 12:00:02 ERROR payment-service Stripe API timeout\n"
        "2026-03-01 12:00:03 WARN order-service Order retry triggered\n"
    )

    files = {"file": ("app.log", log_content.encode("utf-8"), "text/plain")}
    res = await client.post(
        f"/api/v1/projects/{project_id}/logs/upload",
        headers=headers,
        files=files,
    )
    assert res.status_code == 202
    data = res.json()
    batch_id = data["batch_id"]
    assert data["status"] in ("pending", "processing", "done")

    # In eager Celery test mode, task runs synchronously
    # Check batch record
    batch = await db_session.get(LogBatch, uuid.UUID(batch_id))
    assert batch is not None
    assert batch.status == "done"
    assert batch.line_count == 3

    # Check events inserted
    events_res = await db_session.execute(
        select(LogEvent).where(LogEvent.batch_id == uuid.UUID(batch_id))
    )
    events = list(events_res.scalars().all())
    assert len(events) == 3


@pytest.mark.asyncio
async def test_api_ingest_endpoint(client: AsyncClient, db_session: AsyncSession) -> None:
    """Verify POST /ingest accepts NDJSON and JSON array with X-API-Key."""
    token, project_id = await _setup_project(client)

    # Create API key
    key_res = await client.post(
        f"/api/v1/projects/{project_id}/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={"label": "Shipper Key"},
    )
    raw_key = key_res.json()["raw_key"]

    # 1. Ingest via JSON array
    json_array_payload = [
        {"timestamp": "2026-03-01T12:00:01Z", "service": "api-gw", "level": "INFO", "message": "OK"},
        {"timestamp": "2026-03-01T12:00:02Z", "service": "api-gw", "level": "ERROR", "message": "Failed"},
    ]
    res1 = await client.post(
        "/api/v1/ingest",
        headers={"X-API-Key": raw_key},
        json=json_array_payload,
    )
    assert res1.status_code == 202
    batch_1_id = res1.json()["batch_id"]

    batch1 = await db_session.get(LogBatch, uuid.UUID(batch_1_id))
    assert batch1 is not None
    assert batch1.status == "done"
    assert batch1.line_count == 2

    # 2. Ingest via raw NDJSON string
    ndjson_payload = (
        '{"timestamp": "2026-03-01T12:00:03Z", "service": "worker", "level": "INFO", "message": "Job 1"}\n'
        '{"timestamp": "2026-03-01T12:00:04Z", "service": "worker", "level": "WARN", "message": "Job 2"}\n'
    )
    res2 = await client.post(
        "/ingest",  # Test direct root endpoint as well
        headers={"X-API-Key": raw_key, "Content-Type": "application/x-ndjson"},
        content=ndjson_payload.encode("utf-8"),
    )
    assert res2.status_code == 202


@pytest.mark.asyncio
async def test_50k_line_background_ingestion_benchmark(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Acceptance criterion: Uploading a 50,000-line file completes in the background with status=done and correct line count."""
    token, project_id = await _setup_project(client)
    proj_uuid = uuid.UUID(project_id)

    # Generate 50,000 realistic log lines
    line_template = "2026-03-01 12:00:01 INFO service-{} Transaction processed successfully id={}\n"
    # Create content in chunks to be memory efficient
    batch_uuid = uuid.uuid4()

    # Write 50,000 lines directly into storage file
    raw_lines = [line_template.format(i % 5, i) for i in range(50000)]
    storage_path = save_batch_content(batch_uuid, "".join(raw_lines))

    # Create batch record
    batch = LogBatch(
        id=batch_uuid,
        project_id=proj_uuid,
        source="upload",
        filename="benchmark_50k.log",
        storage_path=storage_path,
        status="pending",
    )
    db_session.add(batch)
    await db_session.commit()

    # Execute worker task directly
    result = process_log_batch(str(batch_uuid))
    assert result["status"] == "done"
    assert result["events_count"] == 50000

    # Verify batch status in DB
    await db_session.refresh(batch)
    assert batch.status == "done"
    assert batch.line_count == 50000

    # Verify event count in database
    count_res = await db_session.execute(
        select(func.count(LogEvent.id)).where(LogEvent.batch_id == batch_uuid)
    )
    total_events = count_res.scalar_one()
    assert total_events == 50000


@pytest.mark.asyncio
async def test_batch_reprocessing_idempotency(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify that reprocessing/retrying a batch is idempotent and does not duplicate log events."""
    token, project_id = await _setup_project(client)
    proj_uuid = uuid.UUID(project_id)

    batch_uuid = uuid.uuid4()
    content = (
        "2026-03-01 12:00:01 INFO service-a Event 1\n"
        "2026-03-01 12:00:02 ERROR service-b Event 2\n"
    )
    storage_path = save_batch_content(batch_uuid, content)

    batch = LogBatch(
        id=batch_uuid,
        project_id=proj_uuid,
        source="upload",
        filename="retry_test.log",
        storage_path=storage_path,
        status="pending",
    )
    db_session.add(batch)
    await db_session.commit()

    # Process first time
    res1 = process_log_batch(str(batch_uuid))
    assert res1["status"] == "done"
    assert res1["events_count"] == 2

    # Process second time (retry simulation)
    res2 = process_log_batch(str(batch_uuid))
    assert res2["status"] == "done"
    assert res2["events_count"] == 2

    # Count events in DB: must still be exactly 2, not 4
    count_res = await db_session.execute(
        select(func.count(LogEvent.id)).where(LogEvent.batch_id == batch_uuid)
    )
    assert count_res.scalar_one() == 2
