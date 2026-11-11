"""Tests for Phase 4: Simulated Incident Dataset and Demo Seeding."""

import json
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from simulator.generate import generate_all


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
    _, token = await _create_user_and_token(client, f"Demo User {uid}", f"demo_{uid}@example.com")
    proj = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Demo Incident Project"},
    )
    return token, proj.json()["id"]


def test_generator_deterministic_output(tmp_path: Path):
    """Test generator creates 34 files deterministically from seed."""
    scenarios_dir_1 = tmp_path / "scenarios_1"
    gt_file_1 = tmp_path / "gt_1.json"
    scenarios_dir_2 = tmp_path / "scenarios_2"
    gt_file_2 = tmp_path / "gt_2.json"

    gt_1 = generate_all(seed=42, output_dir=str(scenarios_dir_1), gt_path=str(gt_file_1))
    gt_2 = generate_all(seed=42, output_dir=str(scenarios_dir_2), gt_path=str(gt_file_2))

    # Check scenario count is between 25 and 40 (spec requirement)
    assert 25 <= len(gt_1) <= 40
    assert len(gt_1) == 34
    assert len(gt_2) == 34

    # Check identical ground truth
    assert gt_1 == gt_2

    # Check files match exactly
    files_1 = sorted(scenarios_dir_1.glob("*.log"))
    files_2 = sorted(scenarios_dir_2.glob("*.log"))
    assert len(files_1) == 34
    assert len(files_2) == 34

    for f1, f2 in zip(files_1, files_2, strict=False):
        assert f1.name == f2.name
        assert f1.read_text(encoding="utf-8") == f2.read_text(encoding="utf-8")


def test_ground_truth_metadata_structure():
    """Verify ground_truth.json schema and control dataset properties."""
    gt_path = Path("simulator/ground_truth.json")
    assert gt_path.exists(), "simulator/ground_truth.json must exist"

    data = json.loads(gt_path.read_text(encoding="utf-8"))
    assert len(data) == 34

    required_fields = {
        "scenario_id",
        "has_incident",
        "root_cause_category",
        "origin_service",
        "start_time",
        "end_time",
        "expected_key_patterns",
        "noise_level",
        "service_scope",
        "total_lines",
        "summary",
    }

    # Verify control datasets
    assert "control_steady_state" in data
    assert data["control_steady_state"]["has_incident"] is False
    assert data["control_steady_state"]["root_cause_category"] == "none"

    assert "control_benign_traffic_spike" in data
    assert data["control_benign_traffic_spike"]["has_incident"] is False
    assert data["control_benign_traffic_spike"]["root_cause_category"] == "none"

    # Verify all incident scenarios
    for sc_id, meta in data.items():
        assert required_fields.issubset(meta.keys())
        assert meta["total_lines"] > 0
        if not sc_id.startswith("control_"):
            assert meta["has_incident"] is True
            assert len(meta["expected_key_patterns"]) > 0
            assert meta["origin_service"] != "none"


@pytest.mark.asyncio
async def test_list_demo_scenarios_endpoint(client: AsyncClient):
    """Test GET /projects/demo-scenarios returns scenario catalog."""
    token, _ = await _setup_project(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get("/projects/demo-scenarios", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 34
    first = data[0]
    assert "scenario_id" in first
    assert "has_incident" in first
    assert "root_cause_category" in first


@pytest.mark.asyncio
async def test_demo_data_seeding_and_ingestion(client: AsyncClient):
    """Test POST /projects/{id}/demo-data ingests logs and makes them queryable."""
    token, project_id = await _setup_project(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Seed project with default scenario
    demo_resp = await client.post(
        f"/projects/{project_id}/demo-data",
        json={"scenario_id": "db_pool_exhaustion_low_noise_multi_service"},
        headers=headers,
    )
    assert demo_resp.status_code == 202
    demo_data = demo_resp.json()
    assert demo_data["scenario_id"] == "db_pool_exhaustion_low_noise_multi_service"
    assert "batch_id" in demo_data
    assert demo_data["total_lines"] > 0

    # 2. Verify batch details
    batch_id = demo_data["batch_id"]
    batch_resp = await client.get(f"/batches/{batch_id}", headers=headers)
    assert batch_resp.status_code == 200
    assert batch_resp.json()["status"] == "done"
    assert batch_resp.json()["line_count"] > 0

    # 3. Verify events are queryable via search endpoint
    events_resp = await client.get(
        f"/projects/{project_id}/events",
        params={"limit": 100},
        headers=headers,
    )
    assert events_resp.status_code == 200
    events_data = events_resp.json()
    assert events_data["total"] > 0
    assert len(events_data["items"]) > 0

    # 4. Verify key error pattern is present in messages
    error_events_resp = await client.get(
        f"/projects/{project_id}/events",
        params={"level": "ERROR", "text": "QueuePool"},
        headers=headers,
    )
    assert error_events_resp.status_code == 200
    matching = error_events_resp.json()["items"]
    assert len(matching) > 0
    assert any("QueuePool limit of size 20" in e["message"] for e in matching)


@pytest.mark.asyncio
async def test_demo_data_multi_tenant_isolation(client: AsyncClient):
    """Test User B cannot seed demo data into User A's project (404 anti-enumeration)."""
    # User A creates a project
    token_a, project_a_id = await _setup_project(client)

    # User B registers
    _, token_b = await _create_user_and_token(
        client, "User B Isolated", f"user_b_{uuid.uuid4().hex[:6]}@example.com"
    )
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B attempts to seed demo data into User A's project
    seed_resp = await client.post(
        f"/projects/{project_a_id}/demo-data",
        json={"scenario_id": "redis_oom_low_noise_single_service"},
        headers=headers_b,
    )
    # Must return 404 Not Found to prevent project enumeration
    assert seed_resp.status_code == 404
    assert seed_resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_demo_data_nonexistent_scenario(client: AsyncClient):
    """Test requesting an invalid scenario returns 400 Bad Request."""
    token, project_id = await _setup_project(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/projects/{project_id}/demo-data",
        json={"scenario_id": "non_existent_fake_scenario_xyz"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BAD_REQUEST"
