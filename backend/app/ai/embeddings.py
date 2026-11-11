"""Embedding client abstraction, Gemini Embeddings SDK, and offline deterministic fake."""

import hashlib
import math
import os
import re
import time
from abc import ABC, abstractmethod

from app.core.config import settings


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two equal-length float vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def build_report_embedding_text(
    summary: str | None,
    root_cause: str | None,
    patterns: list[str],
) -> str:
    """Construct canonical text representation of an incident report for vector embedding."""
    parts = []
    if summary:
        parts.append(f"Summary: {summary}")
    if root_cause:
        parts.append(f"Root Cause: {root_cause}")
    if patterns:
        parts.append("Key Patterns: " + " | ".join(patterns[:5]))
    return "\n".join(parts)


class BaseEmbeddingClient(ABC):
    """Abstract interface for embedding providers."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Convert text into a normalized floating-point embedding vector."""
        raise NotImplementedError


class GeminiEmbeddingClient(BaseEmbeddingClient):
    """Google Gemini text embeddings implementation using google-genai SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        dimension: int | None = None,
        max_retries: int = 3,
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.dimension = dimension or settings.EMBEDDING_DIMENSION
        self.max_retries = max_retries

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY must be set to use GeminiEmbeddingClient")

    def embed(self, text: str) -> list[float]:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)
        config = types.EmbedContentConfig(output_dimensionality=self.dimension)

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = client.models.embed_content(
                    model=self.model_name,
                    contents=text,
                    config=config,
                )
                return list(response.embeddings[0].values)
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt - 1))

        raise RuntimeError(
            f"Gemini embedding call failed after {self.max_retries} retries: {last_exc}"
        )


class FakeEmbeddingClient(BaseEmbeddingClient):
    """Deterministic offline embedding client using hashed semantic token projection."""

    def __init__(self, dimension: int | None = None):
        self.dimension = dimension or settings.EMBEDDING_DIMENSION
        self.calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        vec = [0.0] * self.dimension
        if not text.strip():
            return vec

        # Tokenize words (ignoring trivial stop words) and bigrams
        stop_words = {"the", "a", "an", "in", "on", "at", "for", "of", "to", "with", "due", "and", "or", "is"}
        tokens = [
            t for t in re.findall(r"[a-z0-9_]+", text.lower())
            if len(t) > 1 and t not in stop_words
        ]

        if not tokens:
            tokens = ["empty"]

        # Unigrams + word bigrams
        features = list(tokens) + [
            f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1)
        ]

        for feat in features:
            digest = hashlib.sha256(feat.encode()).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dimension
            # Weight feature positively so shared vocabulary yields positive cosine similarity
            vec[idx] += 1.0

        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0.0:
            vec = [x / norm for x in vec]
        return vec


_test_embedding_client_override: BaseEmbeddingClient | None = None


def set_test_embedding_client_override(client: BaseEmbeddingClient | None) -> None:
    """Override the embedding client globally during automated tests."""
    global _test_embedding_client_override
    _test_embedding_client_override = client


def get_embedding_client() -> BaseEmbeddingClient:
    """Factory returning the configured embedding client or Fake client in testing mode."""
    if _test_embedding_client_override is not None:
        return _test_embedding_client_override

    if os.getenv("TESTING") == "1" or not settings.GEMINI_API_KEY:
        return FakeEmbeddingClient()

    return GeminiEmbeddingClient()
