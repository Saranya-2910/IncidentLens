"""Incident report API request and response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel

AI_DISCLAIMER = (
    "AI-generated root-cause hypothesis based on redacted log evidence; "
    "always verify findings against raw events before taking production action."
)


class ExplainTriggerRequest(BaseModel):
    force: bool = False


class ExplainTriggerResponse(BaseModel):
    report_id: uuid.UUID
    incident_id: uuid.UUID
    version: int
    status: str
    message: str


class VerifiedClaimResponse(BaseModel):
    text: str
    cited_line_ids: list[str]
    cited_event_ids: list[int]
    invalid_citations: list[str] = []
    supported: bool
    status: str


class EvidenceLineResponse(BaseModel):
    short_id: str
    event_id: int
    ts: str
    service: str
    level: str
    message: str


class IncidentReportResponse(BaseModel):
    id: uuid.UUID | None = None
    incident_id: uuid.UUID
    version: int = 0
    status: str
    summary: str | None = None
    root_cause: str | None = None
    confidence: str | None = None
    severity: str | None = None
    affected_services: list[str] = []
    suggested_fixes: list[str] = []
    claims: list[VerifiedClaimResponse] = []
    evidence_lines: list[EvidenceLineResponse] = []
    validation_status: str = "not_generated"
    unsupported_claim_count: int = 0
    model_name: str | None = None
    prompt_version: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_incident_events: int = 0
    selected_evidence_lines: int = 0
    error: str | None = None
    created_at: datetime | None = None
    disclaimer: str = AI_DISCLAIMER
