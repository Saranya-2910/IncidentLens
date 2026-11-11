"""LLM Client abstraction, Gemini SDK implementation, and offline Fake client."""

import json
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.ai.prompts import PROMPT_VERSION
from app.ai.schemas import LLMStructuredReport
from app.core.config import settings


@dataclass
class LLMGenerationResult:
    raw_text: str
    model_name: str
    prompt_version: str
    input_tokens: int
    output_tokens: int


class BaseLLMClient(ABC):
    """Abstract interface for all LLM providers."""

    @abstractmethod
    def generate(self, system_instruction: str, user_prompt: str) -> LLMGenerationResult:
        """Generate a raw JSON text completion given system instruction and user prompt."""
        raise NotImplementedError


class GeminiLLMClient(BaseLLMClient):
    """Google Gemini API implementation using the official google-genai SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        max_retries: int = 3,
        timeout_seconds: float = 45.0,
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY must be set to use GeminiLLMClient")

    def generate(self, system_instruction: str, user_prompt: str) -> LLMGenerationResult:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=self.api_key,
            http_options={"timeout": self.timeout_seconds},
        )
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=LLMStructuredReport,
            temperature=0.1,
        )

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=user_prompt,
                    config=config,
                )
                raw_text = response.text or ""
                usage = getattr(response, "usage_metadata", None)
                input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0) if usage else 0
                output_tokens = (
                    int(getattr(usage, "candidates_token_count", 0) or 0) if usage else 0
                )

                return LLMGenerationResult(
                    raw_text=raw_text,
                    model_name=self.model_name,
                    prompt_version=PROMPT_VERSION,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt - 1))

        raise RuntimeError(f"Gemini API call failed after {self.max_retries} retries: {last_exc}")


class FakeLLMClient(BaseLLMClient):
    """Deterministic offline LLM fake for unit testing, CI, and zero-key evaluation."""

    def __init__(self, override_responses: list[str] | None = None):
        self.override_responses = list(override_responses) if override_responses else []
        self.calls: list[dict[str, str]] = []

    def generate(self, system_instruction: str, user_prompt: str) -> LLMGenerationResult:
        self.calls.append({
            "system_instruction": system_instruction,
            "user_prompt": user_prompt,
        })

        # Estimate token counts (~4 chars per token)
        input_tokens = max(1, (len(system_instruction) + len(user_prompt)) // 4)

        if self.override_responses:
            raw_text = self.override_responses.pop(0)
            return LLMGenerationResult(
                raw_text=raw_text,
                model_name="fake-gemini-override",
                prompt_version=PROMPT_VERSION,
                input_tokens=input_tokens,
                output_tokens=max(1, len(raw_text) // 4),
            )

        # Parse line IDs and messages from <UNTRUSTED_LOG_EVIDENCE>
        evidence_match = re.search(
            r"<UNTRUSTED_LOG_EVIDENCE>(.*?)</UNTRUSTED_LOG_EVIDENCE>",
            user_prompt,
            re.DOTALL,
        )
        evidence_text = evidence_match.group(1) if evidence_match else user_prompt
        line_matches = re.findall(r"^\[(L\d+)\]\s+([^\n]+)", evidence_text, re.MULTILINE)

        lines_by_id: dict[str, str] = dict(line_matches)
        all_ids = list(lines_by_id.keys())
        error_ids = [lid for lid, msg in line_matches if "[ERROR]" in msg or "[FATAL]" in msg]
        cite_pool = error_ids if error_ids else all_ids
        first_cite = [cite_pool[0]] if cite_pool else []
        multi_cite = cite_pool[:2] if len(cite_pool) >= 2 else first_cite

        # Extract affected services mentioned in brackets [service-name]
        srv_matches = re.findall(r"\[(?:INFO|WARN|ERROR|FATAL|DEBUG)\]\s+\[([a-zA-Z0-9_-]+)\]", evidence_text)
        affected = sorted(set(srv_matches)) or ["application"]

        # Heuristic matching for realistic deterministic domain explanations across all 8 scenarios
        lower_ev = evidence_text.lower()
        if "queuepool" in lower_ev or "timeouterror" in lower_ev:
            summary = "PostgreSQL connection pool exhaustion in checkout-service led to cascading HTTP 504 gateway timeouts."
            root_cause = "SQLAlchemy QueuePool (size 20, overflow 10) reached saturation due to long-held database connections."
            fixes = [
                "Increase QueuePool size and max_overflow or configure PgBouncer transaction pooling.",
                "Audit slow queries holding transactions open inside checkout transactions.",
            ]
            severity = "critical"
        elif "maxmemory" in lower_ev or "redis" in lower_ev:
            summary = "Redis out-of-memory errors blocked session token writes, causing authentication failures."
            root_cause = "Redis instance exceeded maxmemory threshold under a noeviction policy."
            fixes = [
                "Increase Redis maxmemory allocation or switch eviction policy to allkeys-lru.",
                "Verify TTL expiration settings on session keys.",
            ]
            severity = "high"
        elif "stripe_api_key" in lower_ev or "settings" in lower_ev:
            summary = "Payment service deployment failed to start due to missing STRIPE_API_KEY configuration."
            root_cause = "Release v2.4.1 was deployed without mandatory STRIPE_API_KEY environment variable, triggering Pydantic validation crash loop."
            fixes = [
                "Add STRIPE_API_KEY secret to Kubernetes deployment manifest and roll out fix.",
                "Roll back to previous stable deployment until configuration check passes.",
            ]
            severity = "critical"
        elif "inventory_locks" in lower_ev or "readtimeout" in lower_ev:
            summary = "Inventory lock contention triggered cascading 5-second HTTP read timeouts across order-service and gateway."
            root_cause = "Database deadlock on table inventory_locks held downstream HTTP workers until client read timeouts fired."
            fixes = [
                "Refactor inventory reservation query to acquire row locks in consistent order.",
                "Implement circuit breaking and tighten downstream pool timeouts.",
            ]
            severity = "high"
        elif "no space left on device" in lower_ev or "errno 28" in lower_ev:
            summary = "Disk exhaustion on worker volume aborted background invoice PDF generation tasks."
            root_cause = "Worker node filesystem /var/tmp reached 100% disk utilization (Errno 28)."
            fixes = [
                "Clear temporary PDF artifacts in /var/tmp and add automated log/temp cleanup cron.",
                "Configure disk utilization alerts at 80% threshold.",
            ]
            severity = "high"
        elif "503" in lower_ev and ("stripe" in lower_ev or "gateway" in lower_ev or "circuit breaker" in lower_ev):
            summary = "External payment gateway 503 outage tripped payment-service circuit breaker to OPEN."
            root_cause = "Third-party Stripe API returned HTTP 503 Service Unavailable across consecutive retries."
            fixes = [
                "Monitor upstream Stripe status and allow half-open circuit breaker probes to recover automatically.",
                "Queue non-critical checkout retries cleanly for delayed processing.",
            ]
            severity = "high"
        elif "oomkilled" in lower_ev or "exit code 137" in lower_ev or "out of memory" in lower_ev:
            summary = "Unbounded memory growth in recommendation-service triggered Linux kernel OOM killer (exit code 137)."
            root_cause = "Memory leak from unbounded cache retention exhausted container 4096MB cgroup limit."
            fixes = [
                "Set strict max-entries and LRU eviction bounds on embedding_cache.",
                "Capture heap snapshot before OOM threshold to verify object release.",
            ]
            severity = "critical"
        elif "certificate_verify_failed" in lower_ev or "certificate has expired" in lower_ev:
            summary = "Expired internal mTLS TLS certificate on auth-service broke inter-service RPC authentication."
            root_cause = "TLS certificate for auth.internal.corp expired, causing SSL handshake rejections across calling services."
            fixes = [
                "Renew and rotate the internal TLS certificate immediately via cert-manager.",
                "Add automated certificate expiry monitoring 30 days prior to expiration.",
            ]
            severity = "critical"
        else:
            summary = "Error spike observed across logged services requiring investigation."
            root_cause = "Concentrated service errors correlated within the incident window."
            fixes = ["Inspect top error pattern traces and correlate with recent service changes."]
            severity = "medium"

        payload: dict[str, Any] = {
            "summary": summary,
            "probable_root_cause": root_cause,
            "confidence": "high",
            "affected_services": affected,
            "severity": severity,
            "suggested_fixes": fixes,
            "claims": [
                {
                    "text": summary,
                    "cited_line_ids": first_cite,
                },
                {
                    "text": root_cause,
                    "cited_line_ids": multi_cite,
                },
            ],
        }
        raw_text = json.dumps(payload)
        return LLMGenerationResult(
            raw_text=raw_text,
            model_name="fake-gemini-offline",
            prompt_version=PROMPT_VERSION,
            input_tokens=input_tokens,
            output_tokens=max(1, len(raw_text) // 4),
        )


# Test injection hook
_test_llm_client_override: BaseLLMClient | None = None


def set_test_llm_client_override(client: BaseLLMClient | None) -> None:
    """Override the LLM client globally during automated testing."""
    global _test_llm_client_override
    _test_llm_client_override = client


def get_llm_client() -> BaseLLMClient:
    """Factory returning the configured LLM client or Fake client in testing/offline mode."""
    if _test_llm_client_override is not None:
        return _test_llm_client_override

    if os.getenv("TESTING") == "1" or not settings.GEMINI_API_KEY:
        return FakeLLMClient()

    return GeminiLLMClient()
