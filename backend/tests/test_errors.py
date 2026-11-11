"""Tests for error handling and standard error responses."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_404_not_found_format(client: AsyncClient) -> None:
    """Verify 404 response conforms to standard error schema."""
    response = await client.get("/non-existent-endpoint-xyz")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    error = data["error"]
    assert error["code"] == "NOT_FOUND"
    assert "message" in error
    assert "request_id" in error


@pytest.mark.asyncio
async def test_app_exception_format(client: AsyncClient) -> None:
    """Verify application exceptions return standard error schema."""
    from app.core.errors import BadRequestError
    from app.main import app

    @app.get("/test-custom-error")
    async def trigger_custom_error():
        raise BadRequestError("Custom bad request message", details={"field": "test"})

    response = await client.get("/test-custom-error")
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    error = data["error"]
    assert error["code"] == "BAD_REQUEST"
    assert error["message"] == "Custom bad request message"
    assert error["details"] == {"field": "test"}
    assert "request_id" in error
