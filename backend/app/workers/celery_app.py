"""Celery application configuration."""

import os

from celery import Celery

from app.core.config import settings

is_test_env = settings.ENVIRONMENT == "test" or os.getenv("TESTING") == "1"
broker_url = "memory://" if is_test_env else settings.CELERY_BROKER_URL
backend_url = "cache+memory://" if is_test_env else settings.CELERY_RESULT_BACKEND

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
