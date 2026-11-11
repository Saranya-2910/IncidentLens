"""Tests proving multi-tenant project isolation (User A cannot access User B's projects)."""

import pytest
from httpx import AsyncClient


async def _create_user_and_token(client: AsyncClient, name: str, email: str) -> tuple[str, str]:
    """Helper to register a user and return (user_id, bearer_token)."""
    res = await client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": "TestPassword123!"},
    )
    data = res.json()
    return data["user"]["id"], data["access_token"]


@pytest.mark.asyncio
async def test_project_crud_and_isolation(client: AsyncClient) -> None:
    """Comprehensive test verifying project CRUD and strict isolation across users."""
    # 1. Register User A and User B
    user_a_id, token_a = await _create_user_and_token(client, "User A", "user_a@example.com")
    user_b_id, token_b = await _create_user_and_token(client, "User B", "user_b@example.com")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 2. User A creates Project A
    res_a = await client.post(
        "/api/v1/projects",
        headers=headers_a,
        json={"name": "Project Alpha", "description": "User A secret project"},
    )
    assert res_a.status_code == 201
    project_a = res_a.json()
    project_a_id = project_a["id"]
    assert project_a["name"] == "Project Alpha"

    # 3. User B creates Project B
    res_b = await client.post(
        "/api/v1/projects",
        headers=headers_b,
        json={"name": "Project Beta", "description": "User B project"},
    )
    assert res_b.status_code == 201
    project_b = res_b.json()
    project_b_id = project_b["id"]

    # 4. User A lists projects -> sees only Project A
    list_a = await client.get("/api/v1/projects", headers=headers_a)
    assert list_a.status_code == 200
    ids_for_a = [p["id"] for p in list_a.json()]
    assert project_a_id in ids_for_a
    assert project_b_id not in ids_for_a

    # 5. User B lists projects -> sees only Project B
    list_b = await client.get("/api/v1/projects", headers=headers_b)
    assert list_b.status_code == 200
    ids_for_b = [p["id"] for p in list_b.json()]
    assert project_b_id in ids_for_b
    assert project_a_id not in ids_for_b

    # 6. User B attempts to READ Project A -> Must return 404 (not 403, no existence leak)
    read_a_by_b = await client.get(f"/api/v1/projects/{project_a_id}", headers=headers_b)
    assert read_a_by_b.status_code == 404
    assert read_a_by_b.json()["error"]["code"] == "NOT_FOUND"

    # 7. User B attempts to UPDATE Project A -> Must return 404
    update_a_by_b = await client.patch(
        f"/api/v1/projects/{project_a_id}",
        headers=headers_b,
        json={"name": "Hacked Project Alpha"},
    )
    assert update_a_by_b.status_code == 404
    assert update_a_by_b.json()["error"]["code"] == "NOT_FOUND"

    # 8. User B attempts to DELETE Project A -> Must return 404
    delete_a_by_b = await client.delete(
        f"/api/v1/projects/{project_a_id}", headers=headers_b
    )
    assert delete_a_by_b.status_code == 404
    assert delete_a_by_b.json()["error"]["code"] == "NOT_FOUND"

    # 9. User A updates Project A -> Succeeds
    update_a = await client.patch(
        f"/api/v1/projects/{project_a_id}",
        headers=headers_a,
        json={"name": "Project Alpha Renamed", "description": "Updated description"},
    )
    assert update_a.status_code == 200
    assert update_a.json()["name"] == "Project Alpha Renamed"

    # 10. User A deletes Project A -> Succeeds
    delete_a = await client.delete(
        f"/api/v1/projects/{project_a_id}", headers=headers_a
    )
    assert delete_a.status_code == 204

    # 11. User A verifies Project A is gone -> 404
    verify_a_gone = await client.get(
        f"/api/v1/projects/{project_a_id}", headers=headers_a
    )
    assert verify_a_gone.status_code == 404
