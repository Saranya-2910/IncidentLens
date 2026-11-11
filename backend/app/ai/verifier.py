"""Evidence citation verifier for LLM root-cause reports."""

from dataclasses import dataclass
from typing import Any

from app.ai.schemas import LLMStructuredReport


@dataclass
class VerifiedClaim:
    text: str
    cited_line_ids: list[str]
    cited_event_ids: list[int]
    invalid_citations: list[str]
    supported: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "cited_line_ids": self.cited_line_ids,
            "cited_event_ids": self.cited_event_ids,
            "invalid_citations": self.invalid_citations,
            "supported": self.supported,
            "status": "supported" if self.supported else "unsupported",
        }


@dataclass
class VerificationResult:
    verified_claims: list[VerifiedClaim]
    unsupported_claim_count: int
    validation_status: str  # verified | partial | unverified


class EvidenceVerifier:
    """Validates LLM claims against the actual database event IDs in the evidence map."""

    @classmethod
    def verify(
        cls, report: LLMStructuredReport, id_map: dict[str, int]
    ) -> VerificationResult:
        """Cross-check every cited short ID against the real event ID map."""
        verified_claims: list[VerifiedClaim] = []
        unsupported_count = 0

        for claim in report.claims:
            clean_ids = [cid.strip().upper() for cid in claim.cited_line_ids if cid.strip()]

            valid_short_ids: list[str] = []
            valid_event_ids: list[int] = []
            invalid_citations: list[str] = []

            for cid in clean_ids:
                if cid in id_map:
                    if cid not in valid_short_ids:
                        valid_short_ids.append(cid)
                        valid_event_ids.append(id_map[cid])
                else:
                    invalid_citations.append(cid)

            # A claim is strictly supported only if it cites at least one real ID and zero nonexistent IDs
            is_supported = len(valid_short_ids) > 0 and len(invalid_citations) == 0
            if not is_supported:
                unsupported_count += 1

            verified_claims.append(
                VerifiedClaim(
                    text=claim.text,
                    cited_line_ids=valid_short_ids,
                    cited_event_ids=valid_event_ids,
                    invalid_citations=invalid_citations,
                    supported=is_supported,
                )
            )

        if not verified_claims or unsupported_count == len(verified_claims):
            validation_status = "unverified"
        elif unsupported_count > 0:
            validation_status = "partial"
        else:
            validation_status = "verified"

        return VerificationResult(
            verified_claims=verified_claims,
            unsupported_claim_count=unsupported_count,
            validation_status=validation_status,
        )
