"""Tests for Phase 8: Similar Past Incidents, Resolution Notes, Embeddings, and Project Stats."""

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


async def _setup_project(client: AsyncClient, name: str = "Similarity Project") -> tuple[str, str]:
    """Helper to register user and create project, returning (token, project_id)."""
    uid = uuid.uuid4().hex[:6]
    _, token = await _create_user_and_token(client, f"Sim User {uid}", f"sim_{uid}@example.com")
    proj = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name},
    )
    return token, proj.json()["id"]


@pytest.mark.asyncio
async def test_empty_history_returns_empty_list(client: AsyncClient):
    """Acceptance criterion: Empty history returns 200 OK with empty items list, not an error."""
    token, project_id = await _setup_project(client)
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        f"/projects/{project_id}/demo-data",
        json={"scenario_id": "redis_oom_low_noise_single_service"},
        headers=headers,
    )
    inc_id = (await client.get(f"/projects/{project_id}/incidents", headers=headers)).json()["items"][0]["id"]

    # Call /similar when only 1 incident exists
    sim_resp = await client.get(f"/incidents/{inc_id}/similar", headers=headers)
    assert sim_resp.status_code == 200
    assert sim_resp.json()["incident_id"] == inc_id
    assert sim_resp.json()["items"] == []


@pytest.mark.asyncio
async def test_similar_incident_matching_and_resolution_notes(client: AsyncClient):
    """Acceptance: Resolving a DB pool incident makes a second DB pool incident match it as top hit with fix note."""
    token, project_id = await _setup_project(client, "Prod E-Commerce")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Batch 1: DB Pool Exhaustion at 10:00 (Incident 1)
    logs_db_1 = (
        "2026-11-10 10:00:01 [ERROR] [checkout-service] QueuePool limit of size 20 overflow 10 reached, connection timed out\n"
        "2026-11-10 10:00:05 [ERROR] [checkout-service] sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 reached\n"
        "2026-11-10 10:00:10 [ERROR] [api-gateway] HTTP 504 Gateway Timeout from upstream checkout-service\n"
    )
    await client.post(
        f"/projects/{project_id}/logs/upload",
        files={"file": ("inc1_db.log", logs_db_1.encode(), "text/plain")},
        headers=headers,
    )

    # 2. Batch 2: Unrelated Disk Full at 13:00 (3h gap -> separate Incident 2)
    logs_disk = (
        "2026-11-10 13:00:01 [ERROR] [worker-service] OSError: [Errno 28] No space left on device\n"
        "2026-11-10 13:00:05 [ERROR] [worker-service] Task generate_invoice_pdf failed: No space left on device\n"
    )
    await client.post(
        f"/projects/{project_id}/logs/upload",
        files={"file": ("inc2_disk.log", logs_disk.encode(), "text/plain")},
        headers=headers,
    )

    # List incidents chronologically (newest first)
    incidents = (await client.get(f"/projects/{project_id}/incidents", headers=headers)).json()["items"]
    assert len(incidents) == 2
    inc_disk_id = incidents[0]["id"]  # 13:00
    inc_db1_id = incidents[1]["id"]   # 10:00

    # Generate AI explanations (which builds and stores embeddings) for Incident 1 & Incident 2
    await client.post(f"/incidents/{inc_db1_id}/explain", headers=headers)
    await client.post(f"/incidents/{inc_disk_id}/explain", headers=headers)

    # Resolve Incident 1 with a helpful note
    res_note = "Increased SQLAlchemy pool_size from 20 to 50 and deployed PgBouncer."
    res_resp = await client.post(
        f"/incidents/{inc_db1_id}/resolve",
        json={"status": "resolved", "resolution_note": res_note},
        headers=headers,
    )
    assert res_resp.status_code == 200
    assert res_resp.json()["status"] == "resolved"
    assert res_resp.json()["resolution_note"] == res_note

    # 3. Verify Disk Full does NOT falsely match DB Pool Exhaustion above threshold
    disk_sim = await client.get(f"/incidents/{inc_disk_id}/similar", headers=headers)
    assert disk_sim.status_code == 200
    assert disk_sim.json()["items"] == []

    # 4. Batch 3: Second DB Pool Exhaustion outage at 17:00 (Incident 3)
    logs_db_2 = (
        "2026-11-10 17:00:01 [ERROR] [checkout-service] QueuePool limit of size 20 overflow 10 reached, connection timed out\n"
        "2026-11-10 17:00:06 [ERROR] [checkout-service] sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 reached\n"
        "2026-11-10 17:00:12 [ERROR] [api-gateway] HTTP 504 Gateway Timeout from upstream checkout-service\n"
    )
    await client.post(
        f"/projects/{project_id}/logs/upload",
        files={"file": ("inc3_db.log", logs_db_2.encode(), "text/plain")},
        headers=headers,
    )

    incidents_after = (await client.get(f"/projects/{project_id}/incidents", headers=headers)).json()["items"]
    assert len(incidents_after) == 3
    inc_db2_id = incidents_after[0]["id"]  # 17:00 (newest)

    await client.post(f"/incidents/{inc_db2_id}/explain", headers=headers)

    # 5. Query similar incidents for the second DB Pool Exhaustion incident
    sim_resp = await client.get(f"/incidents/{inc_db2_id}/similar", headers=headers)
    assert sim_resp.status_code == 200
    matches = sim_resp.json()["items"]

    assert len(matches) >= 1
    top_match = matches[0]
    assert top_match["incident_id"] == inc_db1_id
    assert top_match["similarity_score"] >= 0.70
    assert top_match["status"] == "resolved"
    assert top_match["resolution_note"] == res_note


@pytest.mark.asyncio
async def test_similarity_scoped_to_project_and_tenant_isolation(client: AsyncClient):
    """Acceptance: Similarity search never leaks across projects or tenants; unowned access returns 404."""
    # User A creates Project A with a resolved DB pool incident
    token_a, proj_a_id = await _setup_project(client, "User A Project")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    await client.post(
        f"/projects/{proj_a_id}/demo-data",
        json={"scenario_id": "db_pool_exhaustion_low_noise_single_service"},
        headers=headers_a,
    )
    inc_a_id = (await client.get(f"/projects/{proj_a_id}/incidents", headers=headers_a)).json()["items"][0]["id"]
    await client.post(f"/incidents/{inc_a_id}/explain", headers=headers_a)
    await client.post(
        f"/incidents/{inc_a_id}/resolve",
        json={"status": "resolved", "resolution_note": "Secret User A fix note"},
        headers=headers_a,
    )

    # User B creates Project B with the exact same scenario
    token_b, proj_b_id = await _setup_project(client, "User B Project")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    await client.post(
        f"/projects/{proj_b_id}/demo-data",
        json={"scenario_id": "db_pool_exhaustion_low_noise_single_service"},
        headers=headers_b,
    )
    inc_b_id = (await client.get(f"/projects/{proj_b_id}/incidents", headers=headers_b)).json()["items"][0]["id"]
    await client.post(f"/incidents/{inc_b_id}/explain", headers=headers_b)

    # 1. User B's /similar search must return empty [] (never leak User A's match)
    sim_b = await client.get(f"/incidents/{inc_b_id}/similar", headers=headers_b)
    assert sim_b.status_code == 200
    assert sim_b.json()["items"] == []

    # 2. User B directly querying User A's incident similarity or resolve endpoint -> 404
    unauth_sim = await client.get(f"/incidents/{inc_a_id}/similar", headers=headers_b)
    assert unauth_sim.status_code == 404

    unauth_res = await client.post(
        f"/incidents/{inc_a_id}/resolve",
        json={"status": "resolved", "resolution_note": "hijack"},
        headers=headers_b,
    )
    assert unauth_res.status_code == 404


@pytest.mark.asyncio
async def test_project_stats_endpoint(client: AsyncClient):
    """Verify GET /projects/{id}/stats returns error rate timeline, top patterns, and incident counts."""
    token, project_id = await _setup_project(client, "Stats Project")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        f"/projects/{project_id}/demo-data",
        json={"scenario_id": "bad_deploy_low_noise_multi_service"},
        headers=headers,
    )

    # Resolve the incident so we test both open & resolved stats
    inc_id = (await client.get(f"/projects/{project_id}/incidents", headers=headers)).json()["items"][0]["id"]
    await client.patch(
        f"/incidents/{inc_id}",
        json={"status": "resolved", "resolution_note": "Added missing STRIPE_API_KEY env var"},
        headers=headers,
    )

    stats_resp = await client.get(f"/projects/{project_id}/stats", headers=headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()

    assert stats["project_id"] == project_id
    assert stats["total_events"] > 0
    assert stats["error_events"] > 0
    assert stats["total_patterns"] > 0
    assert stats["total_incidents"] == 1
    assert stats["open_incidents"] == 0
    assert stats["resolved_incidents"] == 1
    assert len(stats["error_rate_series"]) > 0
    assert len(stats["top_patterns"]) > 0
