"""Orchestrator for AI incident explanation generation, validation, and verification."""

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.client import BaseLLMClient, get_llm_client
from app.ai.prompts import SYSTEM_INSTRUCTION, build_repair_prompt, build_user_prompt
from app.ai.schemas import LLMStructuredReport
from app.ai.verifier import EvidenceVerifier
from app.models.incident import Incident
from app.models.incident_report import IncidentReport
from app.pipeline.evidence.selector import EvidenceSelector


class IncidentExplainer:
    """Runs evidence selection, redaction, LLM invocation, repair retry, and verification."""

    def __init__(self, session: Session, llm_client: BaseLLMClient | None = None):
        self.session = session
        self.llm_client = llm_client or get_llm_client()

    def explain_report(self, report_id: uuid.UUID) -> IncidentReport:
        """Process a queued IncidentReport end-to-end."""
        report = self.session.get(IncidentReport, report_id)
        if not report:
            raise ValueError(f"IncidentReport {report_id} not found")

        incident = self.session.get(Incident, report.incident_id)
        if not incident:
            report.status = "failed"
            report.validation_status = "failed"
            report.error = "Parent incident not found"
            self.session.commit()
            return report

        report.status = "processing"
        self.session.commit()

        try:
            # 1. Select & redact compact evidence
            selector = EvidenceSelector(self.session)
            ev_res = selector.select_evidence(incident)

            incident_meta: dict[str, Any] = {
                "started_at": incident.started_at.isoformat(),
                "ended_at": incident.ended_at.isoformat() if incident.ended_at else None,
                "severity": incident.severity,
                "event_count": incident.event_count,
                "affected_services": incident.affected_services,
            }

            user_prompt = build_user_prompt(incident_meta, ev_res.formatted_block)

            # 2. Invoke LLM
            gen_res = self.llm_client.generate(SYSTEM_INSTRUCTION, user_prompt)
            total_input_tokens = gen_res.input_tokens
            total_output_tokens = gen_res.output_tokens

            # 3. Validate JSON structure (retry once with repair prompt if invalid)
            parsed_report: LLMStructuredReport | None = None
            validation_err_str: str | None = None

            try:
                parsed_report = LLMStructuredReport.model_validate_json(gen_res.raw_text)
            except (ValidationError, ValueError) as exc:
                validation_err_str = str(exc)
                repair_prompt = build_repair_prompt(gen_res.raw_text, validation_err_str)
                repair_res = self.llm_client.generate(SYSTEM_INSTRUCTION, repair_prompt)
                total_input_tokens += repair_res.input_tokens
                total_output_tokens += repair_res.output_tokens

                try:
                    parsed_report = LLMStructuredReport.model_validate_json(repair_res.raw_text)
                    gen_res = repair_res
                except (ValidationError, ValueError) as exc2:
                    report.status = "failed"
                    report.validation_status = "failed"
                    report.error = f"LLM returned invalid structured JSON even after repair retry: {exc2}"
                    report.input_tokens = total_input_tokens
                    report.output_tokens = total_output_tokens
                    report.model_name = repair_res.model_name
                    report.prompt_version = repair_res.prompt_version
                    self.session.commit()
                    return report

            # 4. Verify all claim citations strictly against real database event IDs
            verification = EvidenceVerifier.verify(parsed_report, ev_res.id_map)

            # 5. Store complete report
            report.status = "done"
            report.summary = parsed_report.summary
            report.root_cause = parsed_report.probable_root_cause
            report.confidence = parsed_report.confidence
            report.severity = parsed_report.severity
            report.affected_services = parsed_report.affected_services
            report.suggested_fix = parsed_report.suggested_fixes

            report.evidence = {
                "claims": [c.to_dict() for c in verification.verified_claims],
                "evidence_lines": [
                    {
                        "short_id": line.short_id,
                        "event_id": line.event_id,
                        "ts": line.ts,
                        "service": line.service,
                        "level": line.level,
                        "message": line.message,
                    }
                    for line in ev_res.lines
                ],
                "id_map": ev_res.id_map,
            }
            report.validation_status = verification.validation_status
            report.unsupported_claim_count = verification.unsupported_claim_count
            report.model_name = gen_res.model_name
            report.prompt_version = gen_res.prompt_version
            report.input_tokens = total_input_tokens
            report.output_tokens = total_output_tokens
            report.total_incident_events = ev_res.total_incident_events
            report.selected_evidence_lines = ev_res.selected_count
            report.error = None

            self.session.commit()
            return report

        except Exception as exc:
            report.status = "failed"
            report.validation_status = "failed"
            report.error = str(exc)
            self.session.commit()
            return report
