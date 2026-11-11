"""Incident detection, spike analysis, and origin candidate ranking engine."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.deployment_marker import DeploymentMarker
from app.models.error_pattern import ErrorPattern
from app.models.incident import Incident, IncidentPattern
from app.models.log_event import LogEvent

GATEWAY_SERVICES = {
    "api-gateway",
    "gateway",
    "frontend-service",
    "frontend",
    "ingress",
    "edge-proxy",
    "proxy",
    "nginx",
}


class IncidentDetector:
    """Detects incidents from log error spikes, clusters windows, and ranks origin patterns."""

    def __init__(
        self,
        session: Session,
        spike_threshold_count: int = 2,
        window_merge_minutes: int = 15,
        quiet_period_minutes: int = 10,
    ):
        self.session = session
        self.spike_threshold_count = spike_threshold_count
        self.window_merge_minutes = window_merge_minutes
        self.quiet_period_minutes = quiet_period_minutes

    def detect_incidents_for_project(self, project_id: uuid.UUID) -> list[Incident]:
        """Run full incident detection pipeline for a project, storing incidents and patterns."""
        # 1. Fetch all error and fatal events for the project
        stmt = (
            select(
                LogEvent.id,
                LogEvent.ts,
                LogEvent.service,
                LogEvent.level,
                LogEvent.pattern_id,
                LogEvent.message,
            )
            .where(LogEvent.project_id == project_id)
            .where(LogEvent.level.in_(["ERROR", "FATAL", "CRITICAL"]))
            .order_by(LogEvent.ts.asc())
        )
        events = self.session.execute(stmt).all()
        if not events:
            # Control dataset or no errors: no incidents
            return []

        # 2. Bucket events into 1-minute intervals
        buckets: dict[datetime, list[Any]] = defaultdict(list)
        for evt in events:
            # Normalize timestamp to minute bucket
            ts = evt.ts
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            bucket_minute = ts.replace(second=0, microsecond=0)
            buckets[bucket_minute].append(evt)

        # 3. Identify spike buckets
        spike_minutes = sorted(
            [m for m, b_events in buckets.items() if len(b_events) >= self.spike_threshold_count]
        )

        # If individual buckets don't reach threshold but we have concentrated errors,
        # fallback to all error minutes
        if not spike_minutes and len(events) >= self.spike_threshold_count:
            spike_minutes = sorted(buckets.keys())

        if not spike_minutes:
            return []

        # 4. Cluster spike buckets into incident time windows
        incident_windows: list[list[datetime]] = []
        current_window = [spike_minutes[0]]

        for m in spike_minutes[1:]:
            prev_m = current_window[-1]
            if (m - prev_m) <= timedelta(minutes=self.window_merge_minutes):
                current_window.append(m)
            else:
                incident_windows.append(current_window)
                current_window = [m]
        if current_window:
            incident_windows.append(current_window)

        # 5. Fetch deployment markers for correlation
        deploy_stmt = (
            select(DeploymentMarker)
            .where(DeploymentMarker.project_id == project_id)
            .order_by(DeploymentMarker.ts.asc())
        )
        deployment_markers = list(self.session.execute(deploy_stmt).scalars().all())

        # 6. Fetch all project error patterns for fast lookup
        patterns_stmt = select(ErrorPattern).where(ErrorPattern.project_id == project_id)
        patterns_by_id = {p.id: p for p in self.session.execute(patterns_stmt).scalars().all()}

        # Purge prior open incidents for clean idempotent re-detection
        self.session.execute(
            delete(Incident).where(Incident.project_id == project_id, Incident.status == "open")
        )
        self.session.flush()

        detected_incidents: list[Incident] = []

        # 7. Process each incident window
        for window in incident_windows:
            win_start = window[0] - timedelta(minutes=2)
            win_end = window[-1] + timedelta(minutes=2)

            # Filter events in this window
            win_events = [
                e for e in events
                if win_start <= (e.ts if e.ts.tzinfo else e.ts.replace(tzinfo=UTC)) <= win_end
            ]
            if not win_events:
                continue

            event_count = len(win_events)
            started_at = min(e.ts for e in win_events)
            ended_at = max(e.ts for e in win_events)

            # Find affected services
            affected_services = sorted({e.service for e in win_events})

            # Group patterns participating in this incident
            # pattern_id -> { "count": int, "first_seen": datetime, "sample_service": str }
            pattern_stats: dict[uuid.UUID, dict[str, Any]] = defaultdict(lambda: {
                "count": 0,
                "first_seen": None,
                "sample_service": "unknown",
            })

            for e in win_events:
                if e.pattern_id:
                    st = pattern_stats[e.pattern_id]
                    st["count"] += 1
                    if st["first_seen"] is None or e.ts < st["first_seen"]:
                        st["first_seen"] = e.ts
                    st["sample_service"] = e.service

            # 8. Rank Origin Candidates
            origin_candidates = self._rank_origin_candidates(
                pattern_stats=pattern_stats,
                patterns_by_id=patterns_by_id,
                incident_start=started_at,
                deployment_markers=deployment_markers,
            )

            top_origin_id = (
                uuid.UUID(origin_candidates[0]["pattern_id"])
                if origin_candidates
                else None
            )

            # 9. Compute Severity
            severity = self._compute_severity(
                event_count=event_count,
                affected_services_count=len(affected_services),
                has_fatal=any(e.level in ("FATAL", "CRITICAL") for e in win_events),
            )

            # 10. Persist Incident
            incident_id = uuid.uuid4()
            incident = Incident(
                id=incident_id,
                project_id=project_id,
                status="open",
                severity=severity,
                started_at=started_at,
                ended_at=ended_at,
                origin_pattern_id=top_origin_id,
                affected_services=affected_services,
                origin_candidates=origin_candidates,
                event_count=event_count,
                created_at=datetime.now(UTC),
            )
            self.session.add(incident)
            self.session.flush()

            # 11. Persist IncidentPattern associations
            for p_id, st in pattern_stats.items():
                inc_pat = IncidentPattern(
                    incident_id=incident_id,
                    pattern_id=p_id,
                    count=st["count"],
                    first_seen_in_incident=st["first_seen"] or started_at,
                )
                self.session.add(inc_pat)

            detected_incidents.append(incident)

        self.session.commit()
        return detected_incidents

    def _rank_origin_candidates(
        self,
        pattern_stats: dict[uuid.UUID, dict[str, Any]],
        patterns_by_id: dict[uuid.UUID, ErrorPattern],
        incident_start: datetime,
        deployment_markers: list[DeploymentMarker],
    ) -> list[dict[str, Any]]:
        """Rank root cause candidates based on time precedence, topology, and growth."""
        candidates: list[dict[str, Any]] = []

        # Check for correlated deploy marker
        deploy_hint = None
        deploy_marker_label = None
        i_start = incident_start if incident_start.tzinfo else incident_start.replace(tzinfo=UTC)
        for marker in deployment_markers:
            m_ts = marker.ts if marker.ts.tzinfo else marker.ts.replace(tzinfo=UTC)
            diff = (i_start - m_ts).total_seconds()
            if 0 <= diff <= 1800:  # deploy occurred within 30 min before incident
                deploy_hint = f"Incident began {int(diff // 60)}m after deploy of {marker.label} ({marker.version})"
                deploy_marker_label = marker.label.lower()
                break

        for p_id, stats in pattern_stats.items():
            pattern = patterns_by_id.get(p_id)
            if not pattern:
                continue

            score = 100.0
            reasons = []

            first_seen = stats["first_seen"] or incident_start
            delta_seconds = max(0.0, (first_seen - incident_start).total_seconds())

            # Penalty for arriving late: lose 2 points per minute after incident start
            time_penalty = min(50.0, (delta_seconds / 60.0) * 2.0)
            score -= time_penalty
            if delta_seconds < 15:
                reasons.append("Appeared at initial incident onset")
            else:
                reasons.append(f"Appeared {int(delta_seconds)}s after initial onset")

            # Topology preference: give preference to origin backend services over gateway/frontend proxies
            service = (stats["sample_service"] or pattern.sample_service or "").lower()
            if service in GATEWAY_SERVICES:
                score -= 30.0
                reasons.append(f"Downstream proxy/gateway service ({service})")
            else:
                score += 20.0
                reasons.append(f"Backend origin service ({service})")

            # Stack trace / Exception bonus
            if "Traceback [" in pattern.template or "JavaException [" in pattern.template:
                score += 15.0
                reasons.append("Contains direct application stack trace")

            # Severity bonus
            if pattern.level in ("FATAL", "CRITICAL"):
                score += 15.0
                reasons.append(f"Critical log severity ({pattern.level})")

            # Deployment correlation bonus
            if deploy_hint and (
                (deploy_marker_label and deploy_marker_label in service) or delta_seconds < 60
            ):
                score += 25.0
                reasons.append(deploy_hint)

            candidates.append({
                "pattern_id": str(p_id),
                "score": round(score, 2),
                "service": stats["sample_service"] or pattern.sample_service,
                "template": pattern.template,
                "level": pattern.level,
                "count": stats["count"],
                "first_seen": first_seen.isoformat(),
                "reason": "; ".join(reasons),
            })

        # Sort descending by score, then ascending by first_seen
        candidates.sort(key=lambda c: (-c["score"], c["first_seen"]))
        return candidates

    @staticmethod
    def _compute_severity(
        event_count: int, affected_services_count: int, has_fatal: bool
    ) -> str:
        """Derive rule-based severity level."""
        if has_fatal or affected_services_count >= 3 or event_count >= 50:
            return "critical"
        if affected_services_count >= 2 or event_count >= 15:
            return "high"
        if event_count >= 4:
            return "medium"
        return "low"
