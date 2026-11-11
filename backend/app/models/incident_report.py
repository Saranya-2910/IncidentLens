"""IncidentReport SQLAlchemy model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.config import settings
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.incident import Incident


class IncidentReport(Base):
    """Represents an AI-generated root-cause explanation report with verified citations."""

    __tablename__ = "incident_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)

    # AI Content Fields
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    affected_services: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        default=list,
        nullable=False,
    )
    suggested_fix: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        default=list,
        nullable=False,
    )

    # Evidence & Verification Metadata
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        default=dict,
        nullable=False,
    )
    validation_status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False
    )
    unsupported_claim_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Model Telemetry & Audit
    model_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_incident_events: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    selected_evidence_lines: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Vector similarity search embedding
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.EMBEDDING_DIMENSION).with_variant(JSON(), "sqlite"),
        nullable=True,
    )

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    incident: Mapped["Incident"] = relationship("Incident")

    __table_args__ = (
        Index("ix_incident_reports_incident_version", "incident_id", "version"),
    )
