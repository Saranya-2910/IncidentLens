"""Tests for event search filtering, pagination, and multi-tenant scoping."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log_batch import LogBatch
from app.models.log_event import LogEvent


async def _create_user_and_project(client: AsyncClient, name: str, email: str) -> tuple[str, str]:
    reg = await client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": "Password123!"},
    )
    token = reg.json()["access_token"]
    proj = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": f"{name}'s Project"},
    )
    return token, proj.json()["id"]


@pytest.mark.asyncio
async def test_event_search_filters_and_isolation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Test filtering by service, level, time, query text, and verify tenant isolation."""
    # Setup User A and User B
    token_a, proj_a_id = await _create_user_and_project(client, "User A", "user_a_ev@example.com")
    token_b, proj_b_id = await _create_user_and_project(client, "User B", "user_b_ev@example.com")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    proj_a_uuid = uuid.UUID(proj_a_id)
    batch_a_uuid = uuid.uuid4()

    # Create batch for Project A
    batch_a = LogBatch(
        id=batch_a_uuid,
        project_id=proj_a_uuid,
        source="upload",
        filename="app.log",
        status="done",
        line_count=4,
    )
    db_session.add(batch_a)

    # Insert structured events for Project A
    t1 = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 3, 1, 10, 15, 0, tzinfo=UTC)
    t3 = datetime(2026, 3, 1, 10, 30, 0, tzinfo=UTC)
    t4 = datetime(2026, 3, 1, 11, 0, 0, tzinfo=UTC)

    events_a = [
        LogEvent(
            project_id=proj_a_uuid,
            batch_id=batch_a_uuid,
            ts=t1,
            service="auth-service",
            level="INFO",
            message="User logged in successfully",
            raw_line="...",
            attributes={},
        ),
        LogEvent(
            project_id=proj_a_uuid,
            batch_id=batch_a_uuid,
            ts=t2,
            service="payment-service",
            level="ERROR",
            message="Gateway timeout connecting to bank",
            raw_line="...",
            attributes={},
        ),
        LogEvent(
            project_id=proj_a_uuid,
            batch_id=batch_a_uuid,
            ts=t3,
            service="payment-service",
            level="WARN",
            message="Retrying payment transaction",
            raw_line="...",
            attributes={},
        ),
        LogEvent(
            project_id=proj_a_uuid,
            batch_id=batch_a_uuid,
            ts=t4,
            service="order-service",
            level="ERROR",
            message="Order cancelled due to payment failure",
            raw_line="...",
            attributes={},
        ),
    ]
    db_session.add_all(events_a)
    await db_session.commit()

    # 1. Search all events for Project A
    res_all = await client.get(f"/api/v1/projects/{proj_a_id}/events", headers=headers_a)
    assert res_all.status_code == 200
    assert res_all.json()["total"] == 4

    # 2. Filter by service: service=payment-service
    res_svc = await client.get(
        f"/api/v1/projects/{proj_a_id}/events?service=payment-service",
        headers=headers_a,
    )
    assert res_svc.status_code == 200
    assert res_svc.json()["total"] == 2
    assert all(e["service"] == "payment-service" for e in res_svc.json()["items"])

    # 3. Filter by level: level=ERROR
    res_lvl = await client.get(
        f"/api/v1/projects/{proj_a_id}/events?level=ERROR",
        headers=headers_a,
    )
    assert res_lvl.status_code == 200
    assert res_lvl.json()["total"] == 2
    assert all(e["level"] == "ERROR" for e in res_lvl.json()["items"])

    # 4. Filter by free-text message: text=timeout
    res_txt = await client.get(
        f"/api/v1/projects/{proj_a_id}/events?text=timeout",
        headers=headers_a,
    )
    assert res_txt.status_code == 200
    assert res_txt.json()["total"] == 1
    assert "timeout" in res_txt.json()["items"][0]["message"]

    # 5. Filter by time range
    res_time = await client.get(
        f"/api/v1/projects/{proj_a_id}/events?start_time=2026-03-01T10:10:00Z&end_time=2026-03-01T10:45:00Z",
        headers=headers_a,
    )
    assert res_time.status_code == 200
    assert res_time.json()["total"] == 2

    # 6. Pagination: limit=2, offset=0
    res_page1 = await client.get(
        f"/api/v1/projects/{proj_a_id}/events?limit=2&offset=0",
        headers=headers_a,
    )
    assert res_page1.status_code == 200
    data_page1 = res_page1.json()
    assert len(data_page1["items"]) == 2
    assert data_page1["total"] == 4

    # 7. Multi-Tenant Scoping (Rule 7):
    # User B attempts to search User A's events -> Must return 404 Not Found
    res_b_attempt = await client.get(
        f"/api/v1/projects/{proj_a_id}/events",
        headers=headers_b,
    )
    assert res_b_attempt.status_code == 404
    assert res_b_attempt.json()["error"]["code"] == "NOT_FOUND"

    # User B attempts to view User A's batch -> Must return 404 Not Found
    res_b_batch = await client.get(
        f"/api/v1/batches/{batch_a_uuid}",
        headers=headers_b,
    )
    assert res_b_batch.status_code == 404
    assert res_b_batch.json()["error"]["code"] == "NOT_FOUND"

    # 8. Single Event Lookup & Tenant Isolation
    first_event_id = data_page1["items"][0]["id"]
    ev_detail = await client.get(
        f"/api/v1/projects/{proj_a_id}/events/{first_event_id}",
        headers=headers_a,
    )
    assert ev_detail.status_code == 200
    assert ev_detail.json()["id"] == first_event_id

    ev_b_attempt = await client.get(
        f"/api/v1/projects/{proj_a_id}/events/{first_event_id}",
        headers=headers_b,
    )
    assert ev_b_attempt.status_code == 404
