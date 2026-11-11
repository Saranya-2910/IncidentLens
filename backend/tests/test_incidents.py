"""Tests for Phase 6: Incident Detection, Clustering, and Origin Candidate Ranking."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.db.session import get_sync_db
from app.models.deployment_marker import DeploymentMarker
from app.models.log_event import LogEvent
from app.pipeline.detection.detector import IncidentDetector
from app.pipeline.grouping.pattern_grouper import PatternGrouper


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
    _, token = await _create_user_and_token(client, f"Incident User {uid}", f"inc_{uid}@example.com")
    proj = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Incident Test Project"},
    )
    return token, proj.json()["id"]


@pytest.mark.asyncio
async def test_control_dataset_yields_zero_incidents(client: AsyncClient):
    """Acceptance criterion: Control datasets must yield exactly zero incidents."""
    token, project_id = await _setup_project(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Seed steady state control dataset
    demo_resp = await client.post(
        f"/projects/{project_id}/demo-data",
        json={"scenario_id": "control_steady_state"},
        headers=headers,
    )
    assert demo_resp.status_code == 202

    # 2. Query incidents
    inc_resp = await client.get(f"/projects/{project_id}/incidents", headers=headers)
    assert inc_resp.status_code == 200
    inc_data = inc_resp.json()
    assert inc_data["total"] == 0
    assert len(inc_data["items"]) == 0


@pytest.mark.asyncio
async def test_simulated_scenario_yields_one_incident_with_top_origin(client: AsyncClient):
    """Acceptance criterion: Incident scenario yields exactly one incident with ground-truth origin in top 3."""
    token, project_id = await _setup_project(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Seed DB pool exhaustion scenario
    demo_resp = await client.post(
        f"/projects/{project_id}/demo-data",
        json={"scenario_id": "db_pool_exhaustion_low_noise_multi_service"},
        headers=headers,
    )
    assert demo_resp.status_code == 202

    # 2. Query incidents list
    inc_resp = await client.get(f"/projects/{project_id}/incidents", headers=headers)
    assert inc_resp.status_code == 200
    inc_data = inc_resp.json()
    assert inc_data["total"] == 1
    assert len(inc_data["items"]) == 1

    incident = inc_data["items"][0]
    incident_id = incident["id"]
    assert incident["status"] == "open"
    assert incident["severity"] in ("high", "critical")
    assert "checkout-service" in incident["affected_services"]
    assert incident["event_count"] > 0
    assert incident["origin_pattern_id"] is not None

    # 3. Retrieve incident detail with timeline and origin candidate rankings
    detail_resp = await client.get(f"/incidents/{incident_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()

    assert "timeline" in detail
    assert len(detail["timeline"]) > 0
    assert "patterns" in detail
    assert len(detail["patterns"]) > 0

    # 4. Verify ground-truth origin pattern is in the top 3 ranked candidates
    candidates = detail["origin_candidates"]
    assert len(candidates) > 0
    top_3_templates = [c["template"] for c in candidates[:3]]

    # Ground truth origin for db pool exhaustion is QueuePool timeout
    assert any("QueuePool" in tmpl or "TimeoutError" in tmpl for tmpl in top_3_templates)
    # Origin candidate service should be checkout-service
    assert candidates[0]["service"] == "checkout-service"


@pytest.mark.asyncio
async def test_incident_multi_tenant_isolation(client: AsyncClient):
    """Test User B cannot access User A's incidents (returns 404 anti-enumeration)."""
    # User A creates project and incident
    token_a, project_a_id = await _setup_project(client)
    headers_a = {"Authorization": f"Bearer {token_a}"}

    await client.post(
        f"/projects/{project_a_id}/demo-data",
        json={"scenario_id": "redis_oom_low_noise_single_service"},
        headers=headers_a,
    )

    incidents_a = await client.get(f"/projects/{project_a_id}/incidents", headers=headers_a)
    incident_id_a = incidents_a.json()["items"][0]["id"]

    # User B registers
    _, token_b = await _create_user_and_token(
        client, "User B Spy", f"spy_{uuid.uuid4().hex[:6]}@example.com"
    )
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B tries to list User A's incidents -> 404
    unauth_list = await client.get(f"/projects/{project_a_id}/incidents", headers=headers_b)
    assert unauth_list.status_code == 404
    assert unauth_list.json()["error"]["code"] == "NOT_FOUND"

    # User B tries to get User A's incident by ID -> 404
    unauth_detail = await client.get(f"/incidents/{incident_id_a}", headers=headers_b)
    assert unauth_detail.status_code == 404
    assert unauth_detail.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_window_merging_and_spike_detection_unit(client: AsyncClient):
    """Unit test for window merging: spikes within merge window join, spikes far apart stay separate."""
    token, test_project_id_str = await _setup_project(client)
    test_project_id = uuid.UUID(test_project_id_str)

    with get_sync_db() as db:
        now = datetime(2026, 11, 10, 14, 0, 0, tzinfo=UTC)

        # Cluster 1: spikes at 14:00 and 14:05 (5 min apart, merge window 15m) -> 1 incident
        # Cluster 2: spike at 16:00 (115 min later) -> 2nd incident
        events_to_create = [
            # Cluster 1
            LogEvent(
                project_id=test_project_id,
                batch_id=uuid.uuid4(),
                ts=now,
                service="auth-service",
                level="ERROR",
                message="Error 1 in cluster 1",
                raw_line="raw1",
            ),
            LogEvent(
                project_id=test_project_id,
                batch_id=uuid.uuid4(),
                ts=now + timedelta(seconds=20),
                service="auth-service",
                level="ERROR",
                message="Error 2 in cluster 1",
                raw_line="raw2",
            ),
            LogEvent(
                project_id=test_project_id,
                batch_id=uuid.uuid4(),
                ts=now + timedelta(minutes=5),
                service="api-gateway",
                level="ERROR",
                message="Error 3 in cluster 1",
                raw_line="raw3",
            ),
            LogEvent(
                project_id=test_project_id,
                batch_id=uuid.uuid4(),
                ts=now + timedelta(minutes=5, seconds=10),
                service="api-gateway",
                level="ERROR",
                message="Error 4 in cluster 1",
                raw_line="raw4",
            ),
            # Cluster 2 (2 hours later)
            LogEvent(
                project_id=test_project_id,
                batch_id=uuid.uuid4(),
                ts=now + timedelta(hours=2),
                service="worker-service",
                level="FATAL",
                message="Fatal error in cluster 2",
                raw_line="raw5",
            ),
            LogEvent(
                project_id=test_project_id,
                batch_id=uuid.uuid4(),
                ts=now + timedelta(hours=2, seconds=15),
                service="worker-service",
                level="FATAL",
                message="Fatal error 2 in cluster 2",
                raw_line="raw6",
            ),
        ]
        db.add_all(events_to_create)
        db.commit()

        # Run normalisation and grouping first
        grouper = PatternGrouper(db)
        for e in events_to_create:
            grouper.group_batch_events(test_project_id, e.batch_id)

        # Run detector
        detector = IncidentDetector(db, spike_threshold_count=2, window_merge_minutes=15)
        incidents = detector.detect_incidents_for_project(test_project_id)

        assert len(incidents) == 2
        # First incident covers auth-service and api-gateway
        assert "auth-service" in incidents[0].affected_services
        # Second incident covers worker-service and is critical
        assert incidents[1].severity == "critical"
        assert "worker-service" in incidents[1].affected_services


@pytest.mark.asyncio
async def test_deployment_marker_correlation(client: AsyncClient):
    """Verify DeploymentMarker created shortly before an incident enriches origin candidate reasons."""
    token, project_id_str = await _setup_project(client)
    project_id = uuid.UUID(project_id_str)
    headers = {"Authorization": f"Bearer {token}"}

    # Scenario bad_deploy occurs around 2026-11-10 14:00:00Z - 14:02:00Z
    deploy_ts = datetime(2026, 11, 10, 14, 0, 0, tzinfo=UTC)
    with get_sync_db() as db:
        marker = DeploymentMarker(
            id=uuid.uuid4(),
            project_id=project_id,
            ts=deploy_ts,
            label="payment-service",
            version="v2.4.1",
            created_at=deploy_ts,
        )
        db.add(marker)
        db.commit()

    demo_resp = await client.post(
        f"/projects/{project_id_str}/demo-data",
        json={"scenario_id": "bad_deploy_low_noise_multi_service"},
        headers=headers,
    )
    assert demo_resp.status_code == 202

    inc_resp = await client.get(f"/projects/{project_id_str}/incidents", headers=headers)
    assert inc_resp.status_code == 200
    incident_id = inc_resp.json()["items"][0]["id"]

    detail_resp = await client.get(f"/incidents/{incident_id}", headers=headers)
    candidates = detail_resp.json()["origin_candidates"]
    assert any("after deploy of payment-service (v2.4.1)" in c["reason"] for c in candidates)


@pytest.mark.asyncio
async def test_all_34_scenarios_detection_and_origin_accuracy(client: AsyncClient):
    """Evaluate IncidentDetector across all 34 simulated scenarios against ground_truth.json."""
    import json
    from pathlib import Path

    from app.pipeline.normaliser.normaliser import Normaliser
    from app.pipeline.parsers.pipeline import LogStreamProcessor

    # Ensure DB schema exists via fixture setup
    _, _ = await _setup_project(client)

    gt_path = Path("simulator/ground_truth.json")
    scenarios_dir = Path("simulator/scenarios")
    gt_data = json.loads(gt_path.read_text(encoding="utf-8"))

    incident_matches = 0
    total_incident_scenarios = 0
    control_false_positives = 0
    top3_origin_hits = 0

    with get_sync_db() as db:
        for sc_id, meta in gt_data.items():
            proj_id = uuid.uuid4()
            batch_id = uuid.uuid4()
            log_path = scenarios_dir / f"{sc_id}.log"

            processor = LogStreamProcessor()
            with log_path.open("r", encoding="utf-8") as f:
                events_dicts = []
                for parsed in processor.process(f):
                    events_dicts.append({
                        "project_id": proj_id,
                        "batch_id": batch_id,
                        "ts": parsed.ts,
                        "service": parsed.service,
                        "level": parsed.level,
                        "message": parsed.message,
                        "trace_id": parsed.trace_id,
                        "pattern_id": None,
                        "attributes": parsed.attributes,
                        "raw_line": parsed.raw_line,
                    })

            if events_dicts:
                from sqlalchemy import insert
                db.execute(insert(LogEvent), events_dicts)
                db.commit()

            PatternGrouper(db).group_batch_events(proj_id, batch_id)
            incidents = IncidentDetector(db).detect_incidents_for_project(proj_id)

            if not meta["has_incident"]:
                if len(incidents) != 0:
                    control_false_positives += 1
            else:
                total_incident_scenarios += 1
                if len(incidents) == 1:
                    incident_matches += 1

                if incidents:
                    inc = incidents[0]
                    top3 = inc.origin_candidates[:3]
                    norm_expected = [
                        Normaliser.normalise_tokens(pat)
                        for pat in meta["expected_key_patterns"]
                    ]
                    hit = False
                    for cand in top3:
                        if cand["service"] == meta["origin_service"] or any(
                            np_str[:25] in cand["template"] for np_str in norm_expected if len(np_str) >= 10
                        ):
                            hit = True
                            break
                    if hit:
                        top3_origin_hits += 1

    # Acceptance Criteria assertions:
    # 1. Control datasets yield zero false positives
    assert control_false_positives == 0, f"Found {control_false_positives} false positives in control datasets"
    # 2. All 32 incident scenarios yield exactly 1 incident
    assert incident_matches == total_incident_scenarios, (
        f"Expected {total_incident_scenarios} incidents, got {incident_matches}"
    )
    # 3. Top-3 origin candidate accuracy >= 90%
    top3_accuracy = top3_origin_hits / total_incident_scenarios
    assert top3_accuracy >= 0.90, f"Top-3 origin accuracy {top3_accuracy:.2%} below 90%"

