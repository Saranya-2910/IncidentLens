"""Tests for health and readiness probes, and request ID middleware."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_liveness(client: AsyncClient) -> None:
    """Verify /health returns 200 and status ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "incidentlens-api"


@pytest.mark.asyncio
async def test_api_v1_health_liveness(client: AsyncClient) -> None:
    """Verify /api/v1/health also returns 200."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_ready_success(client: AsyncClient) -> None:
    """Verify /ready returns 200 when database is reachable."""
    with patch("app.api.v1.endpoints.health.check_db_health", return_value=True):
        response = await client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_ready_database_failure(client: AsyncClient) -> None:
    """Verify /ready returns 503 when database is unreachable."""
    with patch("app.api.v1.endpoints.health.check_db_health", return_value=False):
        response = await client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "disconnected"


@pytest.mark.asyncio
async def test_request_id_middleware(client: AsyncClient) -> None:
    """Verify X-Request-ID header is generated and preserved."""
    # When no header is sent, a UUID is generated
    res1 = await client.get("/health")
    assert "x-request-id" in res1.headers
    generated_id = res1.headers["x-request-id"]
    assert len(generated_id) > 0

    # When header is sent, it is preserved
    custom_id = "test-custom-request-id-1234"
    res2 = await client.get("/health", headers={"X-Request-ID": custom_id})
    assert res2.headers["x-request-id"] == custom_id
