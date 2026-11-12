"""Celery application configuration and free-tier inline dispatch support."""

import logging
import os
import threading
from typing import Any

from celery import Celery

from app.core.config import settings

logger = logging.getLogger("incidentlens.workers")

is_test_env = settings.ENVIRONMENT == "test" or os.getenv("TESTING") == "1"
is_inline_mode = (
    not is_test_env
    and (
        settings.TASK_DISPATCH_MODE.lower() == "inline"
        or not settings.CELERY_BROKER_URL.strip()
        or settings.CELERY_BROKER_URL.startswith("memory")
    )
)

broker_url = "memory://" if (is_test_env or is_inline_mode) else settings.CELERY_BROKER_URL
backend_url = "cache+memory://" if (is_test_env or is_inline_mode) else settings.CELERY_RESULT_BACKEND

celery_app = Celery(
    "incidentlens_worker",
    broker=broker_url,
    backend=backend_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "cleanup-old-events-daily": {
            "task": "tasks.cleanup_old_events",
            "schedule": 86400.0,
        },
    },
)

if is_test_env:
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )


def _run_inline_task(task: Any, *args: Any) -> None:
    try:
        task.run(*args)
    except Exception as exc:
        logger.error(f"Inline background task {getattr(task, 'name', task)} failed: {exc}", exc_info=True)


def dispatch_background_task(task: Any, *args: Any) -> threading.Thread | None:
    """Dispatch via Celery broker or an in-process background thread on single-service free tiers."""
    if is_test_env:
        task.delay(*args)
        return None

    if (
        settings.TASK_DISPATCH_MODE.lower() == "inline"
        or not settings.CELERY_BROKER_URL.strip()
        or settings.CELERY_BROKER_URL.startswith("memory")
    ):
        thread = threading.Thread(target=_run_inline_task, args=(task, *args), daemon=True)
        thread.start()
        return thread

    task.delay(*args)
    return None
