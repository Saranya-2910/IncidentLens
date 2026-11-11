"""Incident and IncidentPattern SQLAlchemy models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

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

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.error_pattern import ErrorPattern
    from app.models.project import Project


class IncidentPattern(Base):
    """Association table linking an incident with its constituent error patterns."""

    __tablename__ = "incident_patterns"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    pattern_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("error_patterns.id", ondelete="CASCADE"),
        primary_key=True,
    )
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_seen_in_incident: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    pattern: Mapped["ErrorPattern"] = relationship("ErrorPattern")
    incident: Mapped["Incident"] = relationship("Incident", back_populates="pattern_associations")


class Incident(Base):
    """Represents a clustered incident spanning one or more error patterns across time."""

    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    origin_pattern_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("error_patterns.id", ondelete="SET NULL"),
        nullable=True,
    )
    affected_services: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        default=list,
        nullable=False,
    )
    origin_candidates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        default=list,
        nullable=False,
    )
    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    project: Mapped["Project"] = relationship("Project")
    origin_pattern: Mapped["ErrorPattern"] = relationship("ErrorPattern")
    pattern_associations: Mapped[list["IncidentPattern"]] = relationship(
        "IncidentPattern",
        back_populates="incident",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_incidents_project_started_at", "project_id", "started_at"),
        Index("ix_incidents_project_status", "project_id", "status"),
    )
