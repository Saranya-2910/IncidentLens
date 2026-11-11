"""Celery background tasks."""

import logging
import uuid
from typing import Any

from app.core.storage import stream_batch_lines
from app.db.session import get_sync_db
from app.pipeline.parsers.pipeline import LogStreamProcessor
from app.repositories.batch_repo import SyncBatchRepository
from app.repositories.event_repo import SyncEventRepository
from app.workers.celery_app import celery_app

logger = logging.getLogger("incidentlens.tasks")

CHUNK_SIZE = 2000


@celery_app.task(name="tasks.ping")
def ping_task(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Test task to verify worker execution and connectivity."""
    logger.info(f"Ping task executing with payload: {payload}")
    return {
        "status": "pong",
        "echo": payload or {},
    }


@celery_app.task(name="tasks.process_log_batch")
def process_log_batch(batch_id_str: str) -> dict[str, Any]:
    """Process a raw log batch in the background, parsing and inserting structured events."""
    logger.info(f"Starting background processing for log batch: {batch_id_str}")
    batch_uuid = uuid.UUID(batch_id_str)

    with get_sync_db() as db:
        batch_repo = SyncBatchRepository(db)
        event_repo = SyncEventRepository(db)

        batch = batch_repo.get_by_id(batch_uuid)
        if not batch:
            logger.error(f"Log batch not found: {batch_id_str}")
            return {"error": "batch_not_found", "status": "failed"}

        # Mark batch as processing
        batch_repo.update_status(batch, status="processing")

        try:
            # Delete any existing events for this batch to ensure safe, idempotent retries
            event_repo.delete_by_batch_id(batch_uuid)

            if not batch.storage_path:
                raise ValueError("Batch has no storage path associated")

            processor = LogStreamProcessor()
            lines_stream = stream_batch_lines(batch.storage_path)

            chunk: list[dict[str, Any]] = []
            for parsed_event in processor.process(lines_stream):
                chunk.append(
                    {
                        "project_id": batch.project_id,
                        "batch_id": batch.id,
                        "ts": parsed_event.ts,
                        "service": parsed_event.service,
                        "level": parsed_event.level,
                        "message": parsed_event.message,
                        "trace_id": parsed_event.trace_id,
                        "pattern_id": None,
                        "attributes": parsed_event.attributes,
                        "raw_line": parsed_event.raw_line,
                    }
                )

                if len(chunk) >= CHUNK_SIZE:
                    event_repo.bulk_insert(chunk)
                    chunk.clear()

            # Insert any remaining events
            if chunk:
                event_repo.bulk_insert(chunk)
                chunk.clear()

            # Mark batch as done with final event count
            batch_repo.update_status(
                batch,
                status="done",
                line_count=processor.parsed_events_count,
            )
            logger.info(
                f"Successfully completed log batch {batch_id_str}: "
                f"{processor.parsed_events_count} events from {processor.total_lines} lines "
                f"({processor.malformed_lines} malformed lines)"
            )
            return {
                "batch_id": batch_id_str,
                "status": "done",
                "events_count": processor.parsed_events_count,
                "total_lines": processor.total_lines,
                "malformed_lines": processor.malformed_lines,
            }

        except Exception as exc:
            logger.error(f"Error processing log batch {batch_id_str}: {exc}", exc_info=True)
            batch_repo.update_status(
                batch,
                status="failed",
                error=str(exc),
            )
            return {
                "batch_id": batch_id_str,
                "status": "failed",
                "error": str(exc),
            }
