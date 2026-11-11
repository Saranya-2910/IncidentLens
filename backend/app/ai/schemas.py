"""Structured Pydantic schemas for LLM incident explanation output."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LLMClaim(BaseModel):
    """A single factual claim made by the LLM backed by cited log line IDs."""

    text: str = Field(..., min_length=1, description="Clear technical claim about the incident")
    cited_line_ids: list[str] = Field(
        default_factory=list,
        description="List of short evidence line IDs supporting this claim (e.g. ['L1', 'L3'])",
    )


class LLMStructuredReport(BaseModel):
    """Structured incident explanation schema validated via Pydantic."""

    summary: str = Field(..., min_length=1, description="Concise executive summary of what failed")
    probable_root_cause: str = Field(
        ..., min_length=1, description="Likely root cause hypothesis grounded in evidence"
    )
    confidence: Literal["low", "medium", "high"] = Field(
        ..., description="Confidence level based on available evidence"
    )
    affected_services: list[str] = Field(
        default_factory=list, description="Services impacted during the incident"
    )
    severity: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="Assessed operational severity"
    )
    suggested_fixes: list[str] = Field(
        default_factory=list, description="Actionable remediation and mitigation steps"
    )
    claims: list[LLMClaim] = Field(
        default_factory=list,
        description="List of discrete claims where each claim cites specific log line IDs",
    )

    @field_validator("confidence", "severity", mode="before")
    @classmethod
    def lowercase_enums(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v
