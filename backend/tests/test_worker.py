"""Tests for Celery worker tasks."""

from app.workers.tasks import ping_task


def test_ping_task_execution() -> None:
    """Verify ping_task executes and returns expected status and echoed payload."""
    payload = {"message": "hello celery", "number": 42}
    result = ping_task.apply(args=[payload])

    assert result.successful()
    output = result.result
    assert output["status"] == "pong"
    assert output["echo"] == payload


def test_ping_task_empty_payload() -> None:
    """Verify ping_task handles empty payload cleanly."""
    result = ping_task.apply()
    assert result.successful()
    assert result.result["status"] == "pong"
    assert result.result["echo"] == {}
