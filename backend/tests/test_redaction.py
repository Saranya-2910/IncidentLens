"""Unit tests for PII, credentials, token, and IP redaction before LLM calls."""

from app.pipeline.redaction.redactor import Redactor


def test_redact_emails():
    raw = "Failed login attempt for alice.smith+ops@company-domain.co.uk and bob@example.org"
    redacted = Redactor.redact(raw)
    assert "alice.smith+ops@company-domain.co.uk" not in redacted
    assert "bob@example.org" not in redacted
    assert redacted.count("<EMAIL_REDACTED>") == 2


def test_redact_jwts_and_bearer_tokens():
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    raw = f"Authorization: Bearer {jwt} failed validation with token Bearer my_custom_secret_token_xyz"
    redacted = Redactor.redact(raw)
    assert jwt not in redacted
    assert "my_custom_secret_token_xyz" not in redacted
    assert "<JWT_REDACTED>" in redacted or "<TOKEN_REDACTED>" in redacted


def test_redact_api_keys_and_passwords():
    il_dummy = "il_live_" + "abcdef12_secret9876543210"
    stripe_dummy = "sk_" + "live_51ABCdef1234567890"
    gemini_dummy = "AIza" + "SyDummyGoogleKey1234567890123456"
    aws_dummy = "AKIA" + "IOSFODNN7EXAMPLE"
    gh_dummy = "ghp_" + "1234567890abcdefghij1234567890"
    raw = (
        f"Config error: {il_dummy}, "
        f"stripe={stripe_dummy}, "
        f"gemini={gemini_dummy}, "
        f"aws={aws_dummy}, "
        f"gh={gh_dummy}, "
        "password='SuperSecretPassword99!'"
    )
    redacted = Redactor.redact(raw)
    assert il_dummy not in redacted
    assert stripe_dummy not in redacted
    assert gemini_dummy not in redacted
    assert aws_dummy not in redacted
    assert gh_dummy not in redacted
    assert "SuperSecretPassword99!" not in redacted
    assert "<API_KEY_REDACTED>" in redacted
    assert "<SECRET_REDACTED>" in redacted


def test_redact_ip_addresses_preserving_versions():
    raw = "Upstream 10.0.4.12:5432 and client 198.51.100.4 failed running service v2.4.1"
    redacted = Redactor.redact(raw)
    assert "10.0.4.12" not in redacted
    assert "198.51.100.4" not in redacted
    assert redacted.count("<IP_REDACTED>") == 2
    assert "v2.4.1" in redacted
