"""Celery background tasks."""

import logging
from typing import Any

from app.workers.celery_app import celery_app

logger = logging.getLogger("incidentlens.tasks")


@celery_app.task(name="tasks.ping")
def ping_task(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Test task to verify worker execution and connectivity."""
    logger.info(f"Ping task executing with payload: {payload}")
    return {
        "status": "pong",
        "echo": payload or {},
    }
