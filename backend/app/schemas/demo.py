"""Demo scenario request and response schemas."""

import uuid

from pydantic import BaseModel


class LoadDemoDataRequest(BaseModel):
    scenario_id: str | None = None


class LoadDemoDataResponse(BaseModel):
    batch_id: uuid.UUID
    scenario_id: str
    status: str
    total_lines: int
    message: str = "Demo incident dataset queued for background ingestion"


class DemoScenarioItem(BaseModel):
    scenario_id: str
    has_incident: bool
    root_cause_category: str
    origin_service: str
    start_time: str
    end_time: str
    expected_key_patterns: list[str]
    noise_level: str
    service_scope: str
    total_lines: int
    summary: str
