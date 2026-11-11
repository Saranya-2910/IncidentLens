"""ErrorPattern SQLAlchemy model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.log_event import LogEvent
    from app.models.project import Project


class ErrorPattern(Base):
    """Represents a unique, normalized error pattern template extracted from log events."""

    __tablename__ = "error_patterns"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    template: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(String(32), default="ERROR", nullable=False)
    sample_service: Mapped[str] = mapped_column(String(128), default="unknown", nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationships
    project: Mapped["Project"] = relationship("Project")
    events: Mapped[list["LogEvent"]] = relationship(
        "LogEvent",
        primaryjoin="ErrorPattern.id == foreign(LogEvent.pattern_id)",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("project_id", "fingerprint", name="uq_error_patterns_project_fingerprint"),
        Index("ix_error_patterns_project_total_count", "project_id", "total_count"),
        Index("ix_error_patterns_project_last_seen", "project_id", "last_seen"),
    )
