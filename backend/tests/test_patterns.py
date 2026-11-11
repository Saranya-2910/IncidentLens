"""Tests for Phase 5: Error Pattern Grouping, API endpoints, and reduction metrics."""

import uuid

import pytest
from httpx import AsyncClient


async def _create_user_and_token(client: AsyncClient, name: str, email: str) -> tuple[str, str]:
    """Helper to register user and return (user_id, token)."""
    res = await client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": "Password123!"},
    )
    data = res.json()
    return data["user"]["id"], data["access_token"]


async def _setup_project(client: AsyncClient) -> tuple[str, str]:
    """Helper to register user and create project, returning (token, project_id)."""
    uid = uuid.uuid4().hex[:6]
    _, token = await _create_user_and_token(client, f"Pattern User {uid}", f"patterns_{uid}@example.com")
    proj = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Pattern Test Project"},
    )
    return token, proj.json()["id"]


@pytest.mark.asyncio
async def test_pattern_grouping_and_reduction_ratio(client: AsyncClient):
    """Test background pattern grouping collapses repetitive error lines with high reduction ratio."""
    token, project_id = await _setup_project(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Load a high-noise multi-service scenario dataset (e.g. ~1,000+ lines)
    demo_resp = await client.post(
        f"/projects/{project_id}/demo-data",
        json={"scenario_id": "db_pool_exhaustion_high_noise_multi_service"},
        headers=headers,
    )
    assert demo_resp.status_code == 202
    batch_data = demo_resp.json()
    total_lines = batch_data["total_lines"]
    assert total_lines > 500

    # 2. Check batch completed
    batch_id = batch_data["batch_id"]
    batch_resp = await client.get(f"/batches/{batch_id}", headers=headers)
    assert batch_resp.status_code == 200
    assert batch_resp.json()["status"] == "done"

    # 3. Retrieve extracted error patterns
    patterns_resp = await client.get(
        f"/projects/{project_id}/patterns",
        headers=headers,
    )
    assert patterns_resp.status_code == 200
    patterns_data = patterns_resp.json()

    unique_patterns = patterns_data["total"]
    assert unique_patterns > 0
    # Crucial acceptance criterion: thousands of lines reduce to a small number of patterns
    # Assert significant reduction ratio: unique patterns should be a small fraction of total lines
    reduction_ratio = 1.0 - (unique_patterns / total_lines)
    assert reduction_ratio >= 0.80, f"Expected reduction ratio >= 80%, got {reduction_ratio:.2%}"

    # 4. Verify pattern structure (counts, sample event ids, trend buckets)
    first_pattern = patterns_data["items"][0]
    assert "fingerprint" in first_pattern
    assert "template" in first_pattern
    assert first_pattern["total_count"] >= 1
    assert "example_event_ids" in first_pattern
    assert len(first_pattern["example_event_ids"]) > 0
    assert "trend" in first_pattern
    assert len(first_pattern["trend"]) > 0


@pytest.mark.asyncio
async def test_pattern_detail_and_filtering(client: AsyncClient):
    """Test filtering patterns by level/service and retrieving detailed pattern metrics."""
    token, project_id = await _setup_project(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Seed demo data
    await client.post(
        f"/projects/{project_id}/demo-data",
        json={"scenario_id": "redis_oom_low_noise_multi_service"},
        headers=headers,
    )

    # 1. Filter by level=ERROR
    error_patterns_resp = await client.get(
        f"/projects/{project_id}/patterns",
        params={"level": "ERROR"},
        headers=headers,
    )
    assert error_patterns_resp.status_code == 200
    error_items = error_patterns_resp.json()["items"]
    assert len(error_items) > 0
    assert all(p["level"] == "ERROR" for p in error_items)

    # 2. Retrieve detailed pattern info
    target_pattern = error_items[0]
    pattern_id = target_pattern["id"]

    detail_resp = await client.get(
        f"/projects/{project_id}/patterns/{pattern_id}",
        headers=headers,
    )
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["id"] == pattern_id
    assert detail_data["total_count"] >= 1
    assert len(detail_data["example_event_ids"]) > 0
    assert "trend" in detail_data


@pytest.mark.asyncio
async def test_pattern_multi_tenant_isolation(client: AsyncClient):
    """Test User B cannot access User A's error patterns (returns 404 anti-enumeration)."""
    # User A creates a project and seeds data
    token_a, project_a_id = await _setup_project(client)
    headers_a = {"Authorization": f"Bearer {token_a}"}

    demo_resp = await client.post(
        f"/projects/{project_a_id}/demo-data",
        json={"scenario_id": "bad_deploy_low_noise_single_service"},
        headers=headers_a,
    )
    assert demo_resp.status_code == 202

    # Get pattern ID from User A
    patterns_a = await client.get(f"/projects/{project_a_id}/patterns", headers=headers_a)
    pattern_id_a = patterns_a.json()["items"][0]["id"]

    # User B registers
    _, token_b = await _create_user_and_token(
        client, "User B Pattern Spy", f"spy_{uuid.uuid4().hex[:6]}@example.com"
    )
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B tries to list User A's patterns -> 404
    unauthorized_list = await client.get(
        f"/projects/{project_a_id}/patterns",
        headers=headers_b,
    )
    assert unauthorized_list.status_code == 404
    assert unauthorized_list.json()["error"]["code"] == "NOT_FOUND"

    # User B tries to get User A's pattern detail -> 404
    unauthorized_detail = await client.get(
        f"/projects/{project_a_id}/patterns/{pattern_id_a}",
        headers=headers_b,
    )
    assert unauthorized_detail.status_code == 404
    assert unauthorized_detail.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_pattern_idempotent_reprocessing(client: AsyncClient):
    """Test reprocessing batch does not duplicate patterns or skew event associations."""
    token, project_id = await _setup_project(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Upload custom log lines
    raw_logs = (
        "2026-11-10 14:00:01 [ERROR] [checkout-service] Connection timed out after 5000ms\n"
        "2026-11-10 14:00:02 [ERROR] [checkout-service] Connection timed out after 3000ms\n"
        "2026-11-10 14:00:03 [ERROR] [checkout-service] Connection timed out after 2000ms\n"
    )

    upload_resp = await client.post(
        f"/projects/{project_id}/logs/upload",
        files={"file": ("reprocess_test.log", raw_logs.encode("utf-8"), "text/plain")},
        headers=headers,
    )
    assert upload_resp.status_code == 202
    batch_id = upload_resp.json()["batch_id"]

    # Verify initial patterns count
    patterns_first = await client.get(f"/projects/{project_id}/patterns", headers=headers)
    assert patterns_first.status_code == 200
    items_first = patterns_first.json()["items"]
    assert len(items_first) == 1
    assert items_first[0]["total_count"] == 3

    # Reprocess the same batch directly using tasks.process_log_batch
    from app.workers.tasks import process_log_batch
    reprocess_result = process_log_batch(str(batch_id))
    assert reprocess_result["status"] == "done"

    # Verify patterns count remains identical (not duplicated to 6)
    patterns_second = await client.get(f"/projects/{project_id}/patterns", headers=headers)
    assert patterns_second.status_code == 200
    items_second = patterns_second.json()["items"]
    assert len(items_second) == 1
    assert items_second[0]["total_count"] == 3
