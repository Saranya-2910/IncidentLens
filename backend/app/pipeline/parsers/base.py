"""Base classes, data models, and timestamp normalization for log parsers."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from dateutil import parser as dateutil_parser

LOG_LEVEL_MAPPINGS = {
    "CRITICAL": "FATAL",
    "FATAL": "FATAL",
    "ALERT": "FATAL",
    "EMERGENCY": "FATAL",
    "ERROR": "ERROR",
    "ERR": "ERROR",
    "WARN": "WARN",
    "WARNING": "WARN",
    "INFO": "INFO",
    "NOTICE": "INFO",
    "DEBUG": "DEBUG",
    "TRACE": "DEBUG",
}


def normalize_level(raw_level: str | None) -> str:
    """Normalize log level string to standard enum (DEBUG, INFO, WARN, ERROR, FATAL)."""
    if not raw_level:
        return "INFO"
    clean = raw_level.strip().upper()
    return LOG_LEVEL_MAPPINGS.get(clean, "INFO")


def parse_timestamp(val: Any) -> datetime:
    """Parse various timestamp representations into a timezone-aware UTC datetime."""
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=UTC)
        return val.astimezone(UTC)

    if isinstance(val, int | float):
        # Epoch timestamp: detect seconds vs milliseconds vs microseconds
        if val > 1e14:  # microseconds
            val = val / 1e6
        elif val > 1e11:  # milliseconds
            val = val / 1e3
        return datetime.fromtimestamp(val, tz=UTC)

    if not isinstance(val, str) or not val.strip():
        return datetime.now(UTC)

    clean_str = val.strip()

    # Try fast ISO 8601 parsing first
    try:
        dt = datetime.fromisoformat(clean_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (ValueError, TypeError):
        pass

    # Try common formats with comma millisecond separators (e.g. 2026-03-01 12:00:01,123)
    standard_match = re.match(
        r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})[,.](\d{1,6})?(.*)$", clean_str
    )
    if standard_match:
        base_part = standard_match.group(1).replace("T", " ")
        millis_part = standard_match.group(2) or "0"
        millis_padded = (millis_part + "000000")[:6]
        try:
            dt = datetime.strptime(
                f"{base_part}.{millis_padded}", "%Y-%m-%d %H:%M:%S.%f"
            )
            return dt.replace(tzinfo=UTC)
        except ValueError:
            pass

    # Generic dateutil parser fallback
    try:
        dt = dateutil_parser.parse(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        return datetime.now(UTC)


@dataclass
class ParsedLogEvent:
    """Structured representation of a parsed log line."""

    ts: datetime
    service: str
    level: str
    message: str
    trace_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    raw_line: str = ""


class BaseParser(ABC):
    """Abstract base class for log format parsers."""

    name: str = "base"

    @abstractmethod
    def can_parse(self, line: str) -> bool:
        """Check if parser can handle this log line format."""
        pass

    @abstractmethod
    def parse(self, line: str) -> ParsedLogEvent | None:
        """Parse raw log line into a structured ParsedLogEvent."""
        pass


class ParserRegistry:
    """Registry maintaining prioritized list of log parsers."""

    def __init__(self) -> None:
        self._parsers: list[tuple[int, BaseParser]] = []

    def register(self, parser: BaseParser, priority: int = 100) -> None:
        """Register a parser with a given priority (lower number = higher precedence)."""
        self._parsers.append((priority, parser))
        self._parsers.sort(key=lambda item: item[0])

    def parse_line(self, line: str) -> tuple[ParsedLogEvent | None, str | None]:
        """Try parsers in order of priority; returns (parsed_event, parser_name)."""
        for _, parser in self._parsers:
            if parser.can_parse(line):
                event = parser.parse(line)
                if event is not None:
                    return event, parser.name
        return None, None
