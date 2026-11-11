"""Standard plain-text application log parser."""

import re

from app.pipeline.parsers.base import BaseParser, ParsedLogEvent, normalize_level, parse_timestamp


class StandardLogParser(BaseParser):
    """Parses common plain-text application log formats."""

    name: str = "standard_text"

    # Compiled regex patterns ordered by specificity
    PATTERNS = [
        # Pattern 1: 2026-03-01 12:00:01 ERROR payment-service message (with optional trace id in brackets)
        # e.g.: 2026-03-01 12:00:01 ERROR [payment-service] [trace-123] Database connection failed
        re.compile(
            r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+"
            r"(?:\[?([A-Z]+)\]?)\s+"
            r"(?:\[?([a-zA-Z0-9_.-]+)\]?:?\s+)"
            r"(?:\[(?:trace[_-]?id:?\s*)?([a-zA-Z0-9_.-]+)\]\s+)?"
            r"(.*)$"
        ),
        # Pattern 2: 2026-03-01 12:00:01 - payment-service - ERROR - message
        re.compile(
            r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\s+-\s+"
            r"([a-zA-Z0-9_.-]+)\s+-\s+"
            r"([A-Z]+)\s+-\s+"
            r"(.*)$"
        ),
        # Pattern 3: Log4j / Spring style: 2026-03-01 12:00:01.123 [main] ERROR com.example.PaymentService - message
        re.compile(
            r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\s+"
            r"\[([^\]]+)\]\s+"
            r"([A-Z]+)\s+"
            r"([a-zA-Z0-9_.-]+)\s+-\s+"
            r"(.*)$"
        ),
        # Pattern 4: [2026-03-01 12:00:01] [ERROR] [payment-service] message
        re.compile(
            r"^\[(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\]\s+"
            r"\[([A-Z]+)\]\s+"
            r"\[([a-zA-Z0-9_.-]+)\]\s+"
            r"(.*)$"
        ),
        # Pattern 5: Syslog style: Mar 01 12:00:01 hostname payment-service[1234]: [ERROR] message
        re.compile(
            r"^([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
            r"(\S+)\s+"
            r"([a-zA-Z0-9_.-]+)(?:\[\d+\])?:\s+"
            r"(?:\[?([A-Z]+)\]?\s+)?"
            r"(.*)$"
        ),
    ]

    def can_parse(self, line: str) -> bool:
        s = line.strip()
        if not s or s.startswith("{"):
            return False
        # Fast check: first character is digit or bracket or letter
        return any(p.match(s) is not None for p in self.PATTERNS)

    def parse(self, line: str) -> ParsedLogEvent | None:
        s = line.strip()

        # Try pattern 1
        m = self.PATTERNS[0].match(s)
        if m:
            raw_ts, raw_level, raw_service, raw_trace, msg = m.groups()
            return ParsedLogEvent(
                ts=parse_timestamp(raw_ts),
                service=raw_service.strip("[]:"),
                level=normalize_level(raw_level),
                message=msg.strip(),
                trace_id=raw_trace.strip() if raw_trace else None,
                attributes={},
                raw_line=line,
            )

        # Try pattern 2 (hyphen-separated)
        m = self.PATTERNS[1].match(s)
        if m:
            raw_ts, raw_service, raw_level, msg = m.groups()
            return ParsedLogEvent(
                ts=parse_timestamp(raw_ts),
                service=raw_service.strip(),
                level=normalize_level(raw_level),
                message=msg.strip(),
                trace_id=None,
                attributes={},
                raw_line=line,
            )

        # Try pattern 3 (Log4j/Spring)
        m = self.PATTERNS[2].match(s)
        if m:
            raw_ts, thread_name, raw_level, raw_service, msg = m.groups()
            return ParsedLogEvent(
                ts=parse_timestamp(raw_ts),
                service=raw_service.split(".")[-1],  # Short class name
                level=normalize_level(raw_level),
                message=msg.strip(),
                trace_id=None,
                attributes={"thread": thread_name, "logger": raw_service},
                raw_line=line,
            )

        # Try pattern 4 (bracket-delimited)
        m = self.PATTERNS[3].match(s)
        if m:
            raw_ts, raw_level, raw_service, msg = m.groups()
            return ParsedLogEvent(
                ts=parse_timestamp(raw_ts),
                service=raw_service.strip(),
                level=normalize_level(raw_level),
                message=msg.strip(),
                trace_id=None,
                attributes={},
                raw_line=line,
            )

        # Try pattern 5 (Syslog)
        m = self.PATTERNS[4].match(s)
        if m:
            raw_ts, hostname, raw_service, raw_level, msg = m.groups()
            return ParsedLogEvent(
                ts=parse_timestamp(raw_ts),
                service=raw_service.strip(),
                level=normalize_level(raw_level or "INFO"),
                message=msg.strip(),
                trace_id=None,
                attributes={"hostname": hostname},
                raw_line=line,
            )

        return None
