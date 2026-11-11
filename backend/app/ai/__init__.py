"""AI explanation package."""

from app.ai.client import (
    BaseLLMClient,
    FakeLLMClient,
    GeminiLLMClient,
    get_llm_client,
    set_test_llm_client_override,
)
from app.ai.embeddings import (
    BaseEmbeddingClient,
    FakeEmbeddingClient,
    GeminiEmbeddingClient,
    build_report_embedding_text,
    cosine_similarity,
    get_embedding_client,
    set_test_embedding_client_override,
)
from app.ai.explainer import IncidentExplainer
from app.ai.schemas import LLMClaim, LLMStructuredReport
from app.ai.verifier import EvidenceVerifier

__all__ = [
    "BaseLLMClient",
    "FakeLLMClient",
    "GeminiLLMClient",
    "get_llm_client",
    "set_test_llm_client_override",
    "IncidentExplainer",
    "LLMStructuredReport",
    "LLMClaim",
    "EvidenceVerifier",
    "BaseEmbeddingClient",
    "FakeEmbeddingClient",
    "GeminiEmbeddingClient",
    "build_report_embedding_text",
    "cosine_similarity",
    "get_embedding_client",
    "set_test_embedding_client_override",
]
