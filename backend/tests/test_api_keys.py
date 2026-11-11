"""Tests for API key creation, hashing, tenant isolation, and ingestion authentication."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnauthorizedError
from app.core.rate_limit import reset_rate_limits
from app.models.api_key import ApiKey
from app.services.api_key_service import ApiKeyService


async def _create_user_and_project(
    client: AsyncClient, name: str, email: str, proj_name: str
) -> tuple[str, str, str]:
    """Helper returning (user_id, token, project_id)."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": "Password123!"},
    )
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]

    res_proj = await client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": proj_name},
    )
    project_id = res_proj.json()["id"]
    return user_id, token, project_id


@pytest.mark.asyncio
async def test_api_key_creation_and_hashing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify raw API key is returned once and only hashed prefix/hash is stored in DB."""
    _, token_a, project_a_id = await _create_user_and_project(
        client, "Alice Keys", "alice_keys@example.com", "Project A"
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # 1. Create API Key
    res = await client.post(
        f"/api/v1/projects/{project_a_id}/api-keys",
        headers=headers_a,
        json={"label": "Production Log Shipper"},
    )
    assert res.status_code == 201
    data = res.json()
    raw_key = data["raw_key"]
    key_prefix = data["key_prefix"]
    key_id = uuid.UUID(data["id"])

    assert raw_key.startswith("il_live_")
    assert raw_key.startswith(key_prefix)

    # 2. Check Database directly: verify raw_key is NEVER stored
    result = await db_session.execute(select(ApiKey).where(ApiKey.id == key_id))
    db_key = result.scalar_one()
    assert db_key.key_prefix == key_prefix
    assert db_key.key_hash != raw_key
    assert len(db_key.key_hash) == 64  # SHA-256 hex string

    # 3. List API keys: raw key must NOT be returned in list
    list_res = await client.get(
        f"/api/v1/projects/{project_a_id}/api-keys", headers=headers_a
    )
    assert list_res.status_code == 200
    listed_keys = list_res.json()
    assert len(listed_keys) == 1
    assert "raw_key" not in listed_keys[0]
    assert listed_keys[0]["key_prefix"] == key_prefix


@pytest.mark.asyncio
async def test_api_key_tenant_isolation(client: AsyncClient) -> None:
    """Verify User B cannot list or revoke User A's API keys."""
    _, token_a, project_a_id = await _create_user_and_project(
        client, "User A", "user_a_keys@example.com", "Project A"
    )
    _, token_b, project_b_id = await _create_user_and_project(
        client, "User B", "user_b_keys@example.com", "Project B"
    )

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A creates a key
    create_res = await client.post(
        f"/api/v1/projects/{project_a_id}/api-keys",
        headers=headers_a,
        json={"label": "Secret Key A"},
    )
    key_a_id = create_res.json()["id"]

    # User B attempts to list User A's keys -> 404
    list_b = await client.get(
        f"/api/v1/projects/{project_a_id}/api-keys", headers=headers_b
    )
    assert list_b.status_code == 404
    assert list_b.json()["error"]["code"] == "NOT_FOUND"

    # User B attempts to revoke User A's key -> 404
    revoke_b = await client.delete(
        f"/api/v1/projects/{project_a_id}/api-keys/{key_a_id}", headers=headers_b
    )
    assert revoke_b.status_code == 404
    assert revoke_b.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_ingestion_authentication_and_revocation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify active key authenticates for ingestion, and revoked keys are rejected."""
    reset_rate_limits()
    _, token_a, project_a_id = await _create_user_and_project(
        client, "Ingest User", "ingest@example.com", "Ingest Project"
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Create key
    create_res = await client.post(
        f"/api/v1/projects/{project_a_id}/api-keys",
        headers=headers_a,
        json={"label": "Active Ingestion Key"},
    )
    raw_key = create_res.json()["raw_key"]
    key_id = create_res.json()["id"]

    # 1. Test ingestion service authentication with valid key
    service = ApiKeyService(db_session)
    authed_proj = await service.authenticate_key(raw_key)
    assert str(authed_proj.id) == project_a_id

    # 2. Revoke the key
    revoke_res = await client.delete(
        f"/api/v1/projects/{project_a_id}/api-keys/{key_id}", headers=headers_a
    )
    assert revoke_res.status_code == 200
    assert revoke_res.json()["revoked_at"] is not None

    # 3. Test ingestion authentication with revoked key -> Must raise UnauthorizedError
    with pytest.raises(UnauthorizedError) as exc_info:
        await service.authenticate_key(raw_key)
    assert "revoked" in str(exc_info.value).lower()

    # 4. Test ingestion authentication with invalid/tampered key
    with pytest.raises(UnauthorizedError):
        await service.authenticate_key("il_live_invalidprefix_boguskey")
