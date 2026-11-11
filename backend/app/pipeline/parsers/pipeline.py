"""Stream processor joining multi-line stack traces and orchestrating parser registry."""

import re
from collections.abc import Generator, Iterable

from app.pipeline.parsers.base import ParsedLogEvent, ParserRegistry
from app.pipeline.parsers.generic_parser import GenericFallbackParser
from app.pipeline.parsers.json_parser import JsonLinesParser
from app.pipeline.parsers.standard_parser import StandardLogParser

# Continuation line indicators for stack traces across Python, Java, Go, Node.js
STACK_TRACE_START = re.compile(
    r"^(Traceback \(most recent call last\):|Caused by:|Exception in thread|panic:)"
)
STACK_TRACE_FRAME = re.compile(
    r"^(\s+at\s+|\s+File\s+\"|at\s+[a-zA-Z0-9_$.]+\(|[a-zA-Z0-9_$.]*(?:Exception|Error|Timeout|Failure|Warning|Interrupt|Exit):|\.\.\.\s+\d+\s+more)"
)


def is_stack_trace_continuation(line: str) -> bool:
    """Determine whether a line is part of a multi-line stack trace belonging to the preceding event."""
    if not line:
        return False
    # Check leading whitespace
    if line.startswith((" ", "\t")):
        return True
    s = line.strip()
    if STACK_TRACE_START.match(s):
        return True
    if STACK_TRACE_FRAME.match(s):
        return True
    return False


def get_default_parser_registry() -> ParserRegistry:
    """Construct and configure the standard parser registry."""
    registry = ParserRegistry()
    registry.register(JsonLinesParser(), priority=10)
    registry.register(StandardLogParser(), priority=20)
    registry.register(GenericFallbackParser(), priority=90)
    return registry


class LogStreamProcessor:
    """Processes a stream of log lines into individual structured events, joining multi-line stack traces."""

    def __init__(self, registry: ParserRegistry | None = None) -> None:
        self.registry = registry or get_default_parser_registry()
        self.total_lines: int = 0
        self.malformed_lines: int = 0
        self.parsed_events_count: int = 0

    def process(self, lines: Iterable[str]) -> Generator[ParsedLogEvent, None, None]:
        """Stream log lines, joining stack traces and yielding complete ParsedLogEvent instances."""
        current_event: ParsedLogEvent | None = None

        for raw_line in lines:
            self.total_lines += 1
            line = raw_line.rstrip("\r\n")

            # Check for empty line
            if not line.strip():
                if current_event:
                    # Append empty newline to stack trace formatting
                    current_event.message += "\n"
                    current_event.raw_line += "\n"
                continue

            # Check if this line continues a multi-line stack trace
            if current_event and is_stack_trace_continuation(line):
                current_event.message += "\n" + line
                current_event.raw_line += "\n" + raw_line
                continue

            # A new event has started: yield previous event if exists
            if current_event is not None:
                self.parsed_events_count += 1
                yield current_event
                current_event = None

            # Parse new line
            event, _ = self.registry.parse_line(line)
            if event is not None:
                current_event = event
            else:
                self.malformed_lines += 1

        # Yield any trailing event at end of stream
        if current_event is not None:
            self.parsed_events_count += 1
            yield current_event
