"""Tests for authentication, session handling, password hashing, and rate limiting."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import reset_rate_limits
from app.models.user import User


@pytest.fixture(autouse=True)
def clean_rate_limits() -> None:
    reset_rate_limits()


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient, db_session: AsyncSession) -> None:
    """Verify user registration returns token, sets cookie, and hashes password."""
    payload = {
        "name": "Alice Engineer",
        "email": "ALICE@Example.com",  # Should be normalized to lowercase
        "password": "SecurePassword123!",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "alice@example.com"
    assert data["user"]["name"] == "Alice Engineer"

    # Verify cookie was set
    assert "access_token" in response.cookies

    # Verify password is NEVER stored as plaintext in DB
    result = await db_session.execute(
        select(User).where(User.email == "alice@example.com")
    )
    user = result.scalar_one()
    assert user.password_hash != "SecurePassword123!"
    assert user.password_hash.startswith("$argon2id$")


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient) -> None:
    """Verify duplicate email registration returns 409 Conflict."""
    payload = {
        "name": "Bob Builder",
        "email": "bob@example.com",
        "password": "Password123!",
    }
    res1 = await client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = await client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 409
    error = res2.json()["error"]
    assert error["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient) -> None:
    """Verify successful login returns valid JWT."""
    register_payload = {
        "name": "Charlie Dev",
        "email": "charlie@example.com",
        "password": "CorrectPassword123!",
    }
    await client.post("/api/v1/auth/register", json=register_payload)

    login_payload = {
        "email": "charlie@example.com",
        "password": "CorrectPassword123!",
    }
    res = await client.post("/api/v1/auth/login", json=login_payload)
    assert res.status_code == 200
    assert "access_token" in res.json()


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient) -> None:
    """Verify wrong password returns 401 Unauthorized."""
    register_payload = {
        "name": "Dave Ops",
        "email": "dave@example.com",
        "password": "RealPassword123!",
    }
    await client.post("/api/v1/auth/register", json=register_payload)

    login_payload = {
        "email": "dave@example.com",
        "password": "WrongPassword!",
    }
    res = await client.post("/api/v1/auth/login", json=login_payload)
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_login_rate_limiting(client: AsyncClient) -> None:
    """Verify exceeding login attempt limit returns 429 Too Many Requests."""
    reset_rate_limits()
    payload = {
        "email": "ratelimit@example.com",
        "password": "RandomPassword!",
    }
    # 5 allowed attempts
    for _ in range(5):
        res = await client.post("/api/v1/auth/login", json=payload)
        assert res.status_code == 401

    # 6th attempt should be blocked by rate limiter
    res_blocked = await client.post("/api/v1/auth/login", json=payload)
    assert res_blocked.status_code == 429
    assert res_blocked.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient) -> None:
    """Verify /auth/me returns current user profile with token header."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={"name": "Eve User", "email": "eve@example.com", "password": "Password123!"},
    )
    token = reg.json()["access_token"]

    res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["email"] == "eve@example.com"


@pytest.mark.asyncio
async def test_get_me_unauthorized(client: AsyncClient) -> None:
    """Verify /auth/me returns 401 when no token is provided."""
    res = await client.get("/api/v1/auth/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_logout(client: AsyncClient) -> None:
    """Verify logout clears cookie."""
    res = await client.post("/api/v1/auth/logout")
    assert res.status_code == 200
    assert "access_token" in res.headers.get("set-cookie", "")
