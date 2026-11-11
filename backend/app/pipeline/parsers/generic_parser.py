"""Generic fallback log parser for unstructured text."""

import re
from datetime import UTC, datetime

from app.pipeline.parsers.base import BaseParser, ParsedLogEvent, normalize_level, parse_timestamp


class GenericFallbackParser(BaseParser):
    """Fallback parser that extracts whatever timestamp and level it can find."""

    name: str = "generic_fallback"

    LEVEL_REGEX = re.compile(
        r"\b(CRITICAL|FATAL|ERROR|ERR|WARN|WARNING|INFO|DEBUG|TRACE)\b", re.IGNORECASE
    )
    TIMESTAMP_REGEX = re.compile(
        r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
    )

    def can_parse(self, line: str) -> bool:
        # Generic fallback can attempt to parse any non-empty string
        return bool(line and line.strip())

    def parse(self, line: str) -> ParsedLogEvent | None:
        s = line.strip()
        if not s:
            return None

        # Look for timestamp
        ts_match = self.TIMESTAMP_REGEX.search(s)
        if ts_match:
            ts = parse_timestamp(ts_match.group(1))
            # Remove timestamp from message
            s_clean = s[: ts_match.start()] + s[ts_match.end() :]
        else:
            ts = datetime.now(UTC)
            s_clean = s

        # Look for level
        level_match = self.LEVEL_REGEX.search(s_clean)
        if level_match:
            level = normalize_level(level_match.group(1))
        else:
            level = "INFO"

        return ParsedLogEvent(
            ts=ts,
            service="unknown",
            level=level,
            message=s.strip(),
            trace_id=None,
            attributes={},
            raw_line=line,
        )
