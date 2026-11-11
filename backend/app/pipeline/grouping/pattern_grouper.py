"""Pattern grouping engine for collapsing log events into error patterns."""

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.error_pattern import ErrorPattern
from app.models.log_event import LogEvent
from app.pipeline.normaliser.normaliser import Normaliser


class BatchPatternSummary:
    """Summary of patterns extracted from a batch."""

    def __init__(
        self,
        total_events: int,
        unique_patterns: int,
        created_patterns: int,
        updated_patterns: int,
    ):
        self.total_events = total_events
        self.unique_patterns = unique_patterns
        self.created_patterns = created_patterns
        self.updated_patterns = updated_patterns

    @property
    def reduction_ratio(self) -> float:
        """Ratio of log line reduction: 1 - (unique_patterns / total_events)."""
        if self.total_events == 0:
            return 0.0
        return round(1.0 - (self.unique_patterns / self.total_events), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_events": self.total_events,
            "unique_patterns": self.unique_patterns,
            "created_patterns": self.created_patterns,
            "updated_patterns": self.updated_patterns,
            "reduction_ratio": self.reduction_ratio,
        }


class PatternGrouper:
    """Extracts templates and links log events to unique error patterns."""

    def __init__(self, session: Session):
        self.session = session

    def group_batch_events(self, project_id: uuid.UUID, batch_id: uuid.UUID) -> BatchPatternSummary:
        """Process unlinked events for a batch, upsert ErrorPatterns, and update event pattern_ids."""
        # 1. Fetch unlinked events for this batch
        stmt = (
            select(LogEvent.id, LogEvent.ts, LogEvent.service, LogEvent.level, LogEvent.message)
            .where(LogEvent.batch_id == batch_id)
            .where(LogEvent.project_id == project_id)
            .order_by(LogEvent.id.asc())
        )
        events = self.session.execute(stmt).all()
        if not events:
            return BatchPatternSummary(0, 0, 0, 0)

        total_events = len(events)

        # 2. Group events in memory by fingerprint
        # fingerprint -> list of event info dicts
        groups: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "template": "",
            "level": "",
            "sample_service": "",
            "first_seen": None,
            "last_seen": None,
            "event_ids": [],
        })

        for evt_id, ts, service, level, message in events:
            norm_res = Normaliser.process(message, level=level)
            grp = groups[norm_res.fingerprint]

            if not grp["template"]:
                grp["template"] = norm_res.template
                grp["level"] = level
                grp["sample_service"] = service
                grp["first_seen"] = ts
                grp["last_seen"] = ts
            else:
                if ts < grp["first_seen"]:
                    grp["first_seen"] = ts
                if ts > grp["last_seen"]:
                    grp["last_seen"] = ts

            grp["event_ids"].append(evt_id)

        # 3. Retrieve existing patterns for this project matching fingerprints
        fingerprints = list(groups.keys())
        existing_stmt = select(ErrorPattern).where(
            ErrorPattern.project_id == project_id,
            ErrorPattern.fingerprint.in_(fingerprints),
        )
        existing_patterns = {p.fingerprint: p for p in self.session.execute(existing_stmt).scalars().all()}

        created_count = 0
        updated_count = 0

        # 4. Upsert patterns and update LogEvent.pattern_id
        for fp, grp in groups.items():
            evt_ids = grp["event_ids"]
            batch_count = len(evt_ids)

            if fp in existing_patterns:
                pattern = existing_patterns[fp]
                pattern.total_count += batch_count
                if grp["last_seen"] > pattern.last_seen:
                    pattern.last_seen = grp["last_seen"]
                if grp["first_seen"] < pattern.first_seen:
                    pattern.first_seen = grp["first_seen"]
                pattern_id = pattern.id
                updated_count += 1
            else:
                pattern_id = uuid.uuid4()
                new_pattern = ErrorPattern(
                    id=pattern_id,
                    project_id=project_id,
                    fingerprint=fp,
                    template=grp["template"],
                    level=grp["level"],
                    sample_service=grp["sample_service"],
                    first_seen=grp["first_seen"],
                    last_seen=grp["last_seen"],
                    total_count=batch_count,
                )
                self.session.add(new_pattern)
                # Flush to ensure new pattern exists before updating event FKs
                self.session.flush()
                created_count += 1

            # 5. Bulk update LogEvent.pattern_id in chunks of 1000
            chunk_size = 1000
            for i in range(0, len(evt_ids), chunk_size):
                chunk = evt_ids[i:i + chunk_size]
                self.session.execute(
                    update(LogEvent)
                    .where(LogEvent.id.in_(chunk))
                    .values(pattern_id=pattern_id)
                )

        self.session.commit()

        return BatchPatternSummary(
            total_events=total_events,
            unique_patterns=len(groups),
            created_patterns=created_count,
            updated_patterns=updated_count,
        )

    def reconcile_project_pattern_counts(self, project_id: uuid.UUID) -> None:
        """Reconcile and synchronize total_count and timestamps for all patterns in a project."""
        # Query actual counts from log_events grouped by pattern_id
        stats_stmt = (
            select(
                LogEvent.pattern_id,
                func.count(LogEvent.id).label("actual_count"),
                func.min(LogEvent.ts).label("min_ts"),
                func.max(LogEvent.ts).label("max_ts"),
            )
            .where(LogEvent.project_id == project_id)
            .where(LogEvent.pattern_id.is_not(None))
            .group_by(LogEvent.pattern_id)
        )
        stats = self.session.execute(stats_stmt).all()

        for pattern_id, count, min_ts, max_ts in stats:
            self.session.execute(
                update(ErrorPattern)
                .where(ErrorPattern.id == pattern_id)
                .values(
                    total_count=count,
                    first_seen=min_ts,
                    last_seen=max_ts,
                )
            )
        self.session.commit()
