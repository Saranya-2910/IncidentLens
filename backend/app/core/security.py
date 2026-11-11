"""Cryptographic and authentication utilities for IncidentLens."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

# Initialize Argon2id password hasher with secure defaults
pwd_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MiB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return pwd_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its Argon2id hash."""
    try:
        return pwd_hasher.verify(hashed_password, password)
    except (VerifyMismatchError, Exception):
        return False


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT access token."""
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a signed JWT access token. Returns None if invalid or expired."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except (jwt.PyJWTError, Exception):
        return None


def generate_api_key() -> tuple[str, str, str]:
    """Generate a cryptographically secure project ingestion API key.

    Returns:
        tuple[raw_key, key_prefix, key_hash]:
        - raw_key: Returned once to the client (never stored in DB).
        - key_prefix: Short prefix stored in DB to index/identify keys quickly.
        - key_hash: SHA-256 hash stored in DB to securely verify incoming keys.
    """
    prefix_rand = secrets.token_hex(4)  # 8 hex chars
    secret_part = secrets.token_urlsafe(32)  # ~43 chars
    raw_key = f"il_live_{prefix_rand}_{secret_part}"
    key_prefix = f"il_live_{prefix_rand}"
    key_hash = hash_api_key(raw_key)
    return raw_key, key_prefix, key_hash


def hash_api_key(raw_key: str) -> str:
    """Hash raw API key with SHA-256."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_api_key_hash(raw_key: str, stored_hash: str) -> bool:
    """Verify a raw API key against a stored SHA-256 hash using constant-time comparison."""
    computed = hash_api_key(raw_key)
    return hmac.compare_digest(computed, stored_hash)
