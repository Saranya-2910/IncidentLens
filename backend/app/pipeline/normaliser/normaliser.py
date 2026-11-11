"""Log message normaliser and template extractor.

Masks variable tokens (UUIDs, numbers, hex IDs, IP addresses, file paths,
quoted strings, durations, timestamps) and extracts robust stack trace
fingerprints based on exception types and top frames.
"""

import hashlib
import os
import re
from typing import NamedTuple


class NormalizedResult(NamedTuple):
    template: str
    fingerprint: str
    is_stack_trace: bool


# ---------------------------------------------------------------------------
# Regular Expressions for Token Masking
# ---------------------------------------------------------------------------

RE_TIMESTAMP_ISO = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)
RE_DATE = re.compile(r"\b\d{4}/\d{2}/\d{2}\b|\b\d{2}/\d{2}/\d{4}\b")
RE_TIME = re.compile(r"\b\d{2}:\d{2}:\d{2}(?:\.\d+)?\b")

RE_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

RE_HEX_PTR = re.compile(r"\b0x[0-9a-fA-F]+\b")
RE_LONG_HEX = re.compile(r"\b[0-9a-fA-F]{16,64}\b")

RE_URL = re.compile(r"https?://[^\s/$.?#].[^\s]*")
RE_INTERNAL_HOST = re.compile(
    r"\b[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*\.(?:corp|internal|local|lan)(?::\d+)?\b"
)
RE_IPV4_PORT = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d+\b")
RE_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

RE_PATH_UNIX = re.compile(r"/(?:[a-zA-Z0-9_.-]+/)+[a-zA-Z0-9_.-]+")
RE_PATH_WIN = re.compile(r"[a-zA-Z]:\\(?:[a-zA-Z0-9_.-]+\\)+[a-zA-Z0-9_.-]+")

RE_DURATION = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ms|milliseconds|second|seconds|sec|s|minute|minutes|min|m|hour|hours|hr|hrs|h|ns|us|µs)\b",
    re.IGNORECASE,
)

RE_QUOTED_VAL = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")

RE_PERCENT = re.compile(r"\b\d+(?:\.\d+)?%\b")
RE_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
RE_MULTI_WHITESPACE = re.compile(r"[ \t]+")


# ---------------------------------------------------------------------------
# Stack Trace Patterns
# ---------------------------------------------------------------------------

RE_PYTHON_TRACEBACK_START = re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE)
RE_PYTHON_FRAME = re.compile(r'File\s+"([^"]+)",\s+line\s+(\d+),\s+in\s+([a-zA-Z0-9_<>]+)')
RE_JAVA_FRAME = re.compile(r'^\s*at\s+([a-zA-Z0-9_.$]+)\(([^:]+):(\d+)\)', re.MULTILINE)


class Normaliser:
    """Deterministic log message normaliser and template extractor."""

    @classmethod
    def normalise_tokens(cls, text: str) -> str:
        """Replace variable tokens with placeholders while preserving structure."""
        if not text:
            return ""

        # 1. Timestamps and Dates
        s = RE_TIMESTAMP_ISO.sub("<TIME>", text)
        s = RE_DATE.sub("<DATE>", s)
        s = RE_TIME.sub("<TIME>", s)

        # 2. UUIDs
        s = RE_UUID.sub("<UUID>", s)

        # 3. Pointers and Hex hashes
        s = RE_HEX_PTR.sub("<HEX>", s)
        s = RE_LONG_HEX.sub("<HASH>", s)

        # 4. URLs, IPs, Hosts
        s = RE_URL.sub("<URL>", s)
        s = RE_INTERNAL_HOST.sub("<HOST>", s)
        s = RE_IPV4_PORT.sub("<HOST>", s)
        s = RE_IPV4.sub("<IP>", s)

        # 5. File paths
        s = RE_PATH_UNIX.sub("<PATH>", s)
        s = RE_PATH_WIN.sub("<PATH>", s)

        # 6. Durations
        s = RE_DURATION.sub("<NUM>ms", s)

        # 7. Quoted strings (collapse quoted tokens)
        s = RE_QUOTED_VAL.sub("'<STR>'", s)

        # 8. Percentages and Numbers
        s = RE_PERCENT.sub("<NUM>%", s)
        s = RE_NUMBER.sub("<NUM>", s)

        # 9. Clean up multiple spaces
        s = RE_MULTI_WHITESPACE.sub(" ", s).strip()
        return s

    @classmethod
    def extract_stack_trace_signature(cls, message: str) -> tuple[str, str] | None:
        """Extract top frames and normalized exception line from a multi-line stack trace."""
        if RE_PYTHON_TRACEBACK_START.search(message):
            lines = [line.strip() for line in message.strip().split("\n") if line.strip()]
            # The exception is typically the last line or lines
            exception_line = lines[-1] if lines else "Exception"
            # If the last line is a detail/caret, scan backwards for the exception class
            for line in reversed(lines):
                if ":" in line and not line.startswith("File "):
                    exception_line = line
                    break

            # Extract frames
            frames = RE_PYTHON_FRAME.findall(message)
            top_frames: list[str] = []
            for filepath, _lineno, func_name in frames[-3:]:  # take up to 3 most specific frames
                basename = os.path.basename(filepath)
                top_frames.append(f"{basename}:{func_name}")

            frames_str = " -> ".join(top_frames) if top_frames else "unknown"
            norm_exc = cls.normalise_tokens(exception_line)
            template = f"Traceback [{frames_str}]: {norm_exc}"
            return template, norm_exc

        # Java Stack Trace check
        java_frames = RE_JAVA_FRAME.findall(message)
        if java_frames:
            first_line = message.strip().split("\n")[0]
            top_frames = []
            for class_method, file_name, _ in java_frames[:2]:
                top_frames.append(f"{class_method}({file_name})")
            frames_str = " -> ".join(top_frames)
            norm_exc = cls.normalise_tokens(first_line)
            template = f"JavaException [{frames_str}]: {norm_exc}"
            return template, norm_exc

        return None

    @classmethod
    def process(cls, message: str, level: str = "ERROR") -> NormalizedResult:
        """Produce a normalized template and stable SHA-256 fingerprint."""
        stack_trace_sig = cls.extract_stack_trace_signature(message)
        if stack_trace_sig:
            template, _ = stack_trace_sig
            is_stack = True
        else:
            template = cls.normalise_tokens(message)
            is_stack = False

        # Stable fingerprint: SHA-256 hash of level + normalized template
        hash_input = f"{level.upper()}:{template}".encode()
        fingerprint = hashlib.sha256(hash_input).hexdigest()

        return NormalizedResult(
            template=template,
            fingerprint=fingerprint,
            is_stack_trace=is_stack,
        )
