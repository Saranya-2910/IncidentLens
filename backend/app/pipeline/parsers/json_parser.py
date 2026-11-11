"""JSON lines log parser."""

import json
from typing import Any

from app.pipeline.parsers.base import BaseParser, ParsedLogEvent, normalize_level, parse_timestamp


class JsonLinesParser(BaseParser):
    """Parses newline-delimited JSON (NDJSON) application logs."""

    name: str = "json_lines"

    TIMESTAMP_KEYS = ["timestamp", "ts", "time", "@timestamp", "datetime", "date"]
    LEVEL_KEYS = ["level", "severity", "loglevel", "lvl", "log_level", "status"]
    SERVICE_KEYS = ["service", "service_name", "app", "application", "component", "logger"]
    MESSAGE_KEYS = ["message", "msg", "log", "text", "body"]
    TRACE_KEYS = ["trace_id", "traceId", "traceid", "correlation_id", "requestId", "request_id"]

    def can_parse(self, line: str) -> bool:
        s = line.strip()
        return s.startswith("{") and s.endswith("}")

    def parse(self, line: str) -> ParsedLogEvent | None:
        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                return None
        except Exception:
            return None

        # Extract timestamp
        raw_ts: Any = None
        for key in self.TIMESTAMP_KEYS:
            if key in data and data[key] is not None:
                raw_ts = data[key]
                break
        ts = parse_timestamp(raw_ts)

        # Extract level
        raw_level: str = "INFO"
        for key in self.LEVEL_KEYS:
            if key in data and data[key] is not None:
                raw_level = str(data[key])
                break
        level = normalize_level(raw_level)

        # Extract service
        service: str = "unknown"
        for key in self.SERVICE_KEYS:
            if key in data and data[key] is not None:
                service = str(data[key])
                break

        # Extract message
        message: str = ""
        for key in self.MESSAGE_KEYS:
            if key in data and data[key] is not None:
                message = str(data[key])
                break
        if not message:
            # Fallback message
            message = str(data)

        # Extract trace_id
        trace_id: str | None = None
        for key in self.TRACE_KEYS:
            if key in data and data[key] is not None:
                trace_id = str(data[key])
                break

        # Collect remaining attributes
        reserved = set(
            self.TIMESTAMP_KEYS
            + self.LEVEL_KEYS
            + self.SERVICE_KEYS
            + self.MESSAGE_KEYS
            + self.TRACE_KEYS
        )
        attributes = {k: v for k, v in data.items() if k not in reserved}

        return ParsedLogEvent(
            ts=ts,
            service=service,
            level=level,
            message=message,
            trace_id=trace_id,
            attributes=attributes,
            raw_line=line,
        )
