"""Sensitive PII and secret redaction module.

Masks emails, JWTs, API keys, Bearer tokens, credentials/passwords,
and IP addresses before any log evidence leaves the backend to an LLM provider.
"""

import re

RE_EMAIL = re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b")
RE_JWT = re.compile(r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b")
RE_BEARER = re.compile(
    r"((?:Authorization\s*:\s*)?Bearer\s+)[a-zA-Z0-9._~+/=-]{8,}",
    re.IGNORECASE,
)
RE_PREFIXED_KEY = re.compile(
    r"\b(?:"
    r"il_live_[a-zA-Z0-9_]{8,}"
    r"|(?:sk|pk|rk)_(?:live|test)_[a-zA-Z0-9]{10,}"
    r"|AIza[0-9A-Za-z_-]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|(?:ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{20,}"
    r")\b"
)
RE_SECRET_KV = re.compile(
    r"(\b(?:password|passwd|pwd|secret|api_key|apikey|token|access_token|refresh_token|client_secret)\s*[=:]\s*['\"]?)([^'\"\s&,;]+)(['\"]?)",
    re.IGNORECASE,
)
RE_IPV4 = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)
RE_IPV6 = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){3,7}[0-9a-fA-F]{1,4}\b")


class Redactor:
    """Deterministic log sanitizer for outbound LLM prompts."""

    @classmethod
    def redact(cls, text: str) -> str:
        """Redact secrets, tokens, emails, and IP addresses from raw text."""
        if not text:
            return text

        s = RE_JWT.sub("<JWT_REDACTED>", text)
        s = RE_BEARER.sub(r"\1<TOKEN_REDACTED>", s)
        s = RE_PREFIXED_KEY.sub("<API_KEY_REDACTED>", s)
        s = RE_SECRET_KV.sub(r"\1<SECRET_REDACTED>\3", s)
        s = RE_EMAIL.sub("<EMAIL_REDACTED>", s)
        s = RE_IPV4.sub("<IP_REDACTED>", s)
        s = RE_IPV6.sub("<IP_REDACTED>", s)
        return s
