"""Unit tests for log parser plugins, timestamp normalization, and multi-line stack traces."""

from datetime import UTC, datetime

from app.pipeline.parsers.base import normalize_level, parse_timestamp
from app.pipeline.parsers.generic_parser import GenericFallbackParser
from app.pipeline.parsers.json_parser import JsonLinesParser
from app.pipeline.parsers.pipeline import LogStreamProcessor
from app.pipeline.parsers.standard_parser import StandardLogParser


def test_timestamp_normalization() -> None:
    """Verify various timestamp representations convert accurately to UTC."""
    # ISO 8601 with Z
    t1 = parse_timestamp("2026-03-01T12:00:01Z")
    assert t1 == datetime(2026, 3, 1, 12, 0, 1, tzinfo=UTC)

    # Standard date-time with comma milliseconds
    t2 = parse_timestamp("2026-03-01 12:00:01,500")
    assert t2 == datetime(2026, 3, 1, 12, 0, 1, 500000, tzinfo=UTC)

    # Epoch milliseconds
    t3 = parse_timestamp(1772366401000)
    assert t3.year == 2026

    # Bad timestamp falls back to current time without raising exception
    t4 = parse_timestamp("not-a-valid-timestamp-xyz")
    assert isinstance(t4, datetime)
    assert t4.tzinfo == UTC


def test_level_normalization() -> None:
    """Verify log levels map to standard categories."""
    assert normalize_level("critical") == "FATAL"
    assert normalize_level("fatal") == "FATAL"
    assert normalize_level("error") == "ERROR"
    assert normalize_level("warn") == "WARN"
    assert normalize_level("warning") == "WARN"
    assert normalize_level("info") == "INFO"
    assert normalize_level("debug") == "DEBUG"
    assert normalize_level("unknown") == "INFO"
    assert normalize_level(None) == "INFO"


def test_json_lines_parser() -> None:
    """Verify JSON lines parser extracts structured fields and extra attributes."""
    parser = JsonLinesParser()
    line = (
        '{"timestamp": "2026-03-01T12:00:01Z", "service": "payment-service", '
        '"level": "ERROR", "message": "Charge failed", "trace_id": "tr-987", '
        '"user_id": 42, "ip": "192.168.1.1"}'
    )
    assert parser.can_parse(line)
    event = parser.parse(line)
    assert event is not None
    assert event.service == "payment-service"
    assert event.level == "ERROR"
    assert event.message == "Charge failed"
    assert event.trace_id == "tr-987"
    assert event.attributes == {"user_id": 42, "ip": "192.168.1.1"}
    assert event.ts == datetime(2026, 3, 1, 12, 0, 1, tzinfo=UTC)


def test_standard_text_formats() -> None:
    """Verify standard plain-text log patterns."""
    parser = StandardLogParser()

    # Pattern 1: 2026-03-01 12:00:01 ERROR payment-service message
    line1 = "2026-03-01 12:00:01 ERROR payment-service Database pool exhausted"
    assert parser.can_parse(line1)
    ev1 = parser.parse(line1)
    assert ev1 is not None
    assert ev1.service == "payment-service"
    assert ev1.level == "ERROR"
    assert ev1.message == "Database pool exhausted"

    # Pattern 1 with trace id: 2026-03-01 12:00:01 ERROR [auth-service] [trace-abc123] Token expired
    line2 = "2026-03-01 12:00:01 ERROR [auth-service] [trace-abc123] Token expired"
    ev2 = parser.parse(line2)
    assert ev2 is not None
    assert ev2.service == "auth-service"
    assert ev2.level == "ERROR"
    assert ev2.trace_id == "trace-abc123"
    assert ev2.message == "Token expired"

    # Pattern 2: 2026-03-01 12:00:01 - order-service - WARN - Slow response
    line3 = "2026-03-01 12:00:01 - order-service - WARN - Slow response"
    ev3 = parser.parse(line3)
    assert ev3 is not None
    assert ev3.service == "order-service"
    assert ev3.level == "WARN"
    assert ev3.message == "Slow response"

    # Pattern 4: [2026-03-01 12:00:01] [INFO] [gateway] Request processed
    line4 = "[2026-03-01 12:00:01] [INFO] [gateway] Request processed"
    ev4 = parser.parse(line4)
    assert ev4 is not None
    assert ev4.service == "gateway"
    assert ev4.level == "INFO"
    assert ev4.message == "Request processed"


def test_generic_fallback_parser() -> None:
    """Verify generic parser extracts whatever it can from unstructured text."""
    parser = GenericFallbackParser()
    line = "Something went terribly ERROR on worker node"
    assert parser.can_parse(line)
    ev = parser.parse(line)
    assert ev is not None
    assert ev.level == "ERROR"
    assert "Something went terribly" in ev.message


def test_python_multi_line_stack_trace_joining() -> None:
    """Verify Python multi-line tracebacks are merged into a single structured event."""
    processor = LogStreamProcessor()
    lines = [
        "2026-03-01 12:00:01 ERROR payment-service Unhandled exception in checkout",
        "Traceback (most recent call last):",
        '  File "/app/services/checkout.py", line 42, in process',
        "    res = db.execute(query)",
        "ConnectionRefusedError: [Errno 111] Connection refused",
        "2026-03-01 12:00:02 INFO gateway Request completed",
    ]

    events = list(processor.process(lines))
    assert len(events) == 2
    assert processor.parsed_events_count == 2

    # First event should contain the full stack trace joined
    first_ev = events[0]
    assert first_ev.service == "payment-service"
    assert first_ev.level == "ERROR"
    assert "Unhandled exception in checkout" in first_ev.message
    assert "Traceback (most recent call last):" in first_ev.message
    assert "ConnectionRefusedError" in first_ev.message

    # Second event is clean
    second_ev = events[1]
    assert second_ev.service == "gateway"
    assert second_ev.level == "INFO"
    assert second_ev.message == "Request completed"


def test_java_multi_line_stack_trace_joining() -> None:
    """Verify Java multi-line exception stack traces are merged into a single event."""
    processor = LogStreamProcessor()
    lines = [
        "2026-03-01 12:00:01 ERROR auth-service java.sql.SQLException: Connection timeout",
        "\tat com.zaxxer.hikari.pool.HikariPool.getConnection(HikariPool.java:182)",
        "\tat org.example.AuthService.findUser(AuthService.java:54)",
        "Caused by: java.net.SocketTimeoutException: Read timed out",
        "\tat java.base/sun.nio.ch.NioSocketImpl.timedRead(NioSocketImpl.java:283)",
        "\t... 12 more",
        "2026-03-01 12:00:02 INFO auth-service Retrying connection",
    ]

    events = list(processor.process(lines))
    assert len(events) == 2

    first_ev = events[0]
    assert "java.sql.SQLException: Connection timeout" in first_ev.message
    assert "HikariPool.getConnection" in first_ev.message
    assert "Caused by: java.net.SocketTimeoutException" in first_ev.message
    assert "... 12 more" in first_ev.message


def test_empty_input_stream() -> None:
    """Verify empty input returns 0 events."""
    processor = LogStreamProcessor()
    events = list(processor.process([]))
    assert len(events) == 0
    assert processor.total_lines == 0
    assert processor.parsed_events_count == 0


def test_malformed_lines_handling() -> None:
    """Verify malformed lines are handled gracefully without aborting the batch."""
    processor = LogStreamProcessor()
    lines = [
        "2026-03-01 12:00:01 INFO api-gateway Started successfully",
        "",  # Empty line
        "   ",  # Blank line
        "2026-03-01 12:00:02 ERROR auth-service Failure occurred",
    ]
    events = list(processor.process(lines))
    assert len(events) == 2
