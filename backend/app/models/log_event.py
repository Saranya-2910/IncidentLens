"""LogEvent SQLAlchemy model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
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

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.log_batch import LogBatch
    from app.models.project import Project


class LogEvent(Base):
    """Represents an individual structured log event extracted from a batch."""

    __tablename__ = "log_events"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("log_batches.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    service: Mapped[str] = mapped_column(
        String(128), default="unknown", index=True, nullable=False
    )
    level: Mapped[str] = mapped_column(
        String(32), default="INFO", index=True, nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    pattern_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        default=dict,
        nullable=False,
    )
    raw_line: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    batch: Mapped["LogBatch"] = relationship("LogBatch", back_populates="events")
    project: Mapped["Project"] = relationship("Project")

    __table_args__ = (
        Index("ix_log_events_project_ts", "project_id", "ts"),
        Index("ix_log_events_project_pattern", "project_id", "pattern_id"),
        Index("ix_log_events_project_service_level", "project_id", "service", "level"),
    )
