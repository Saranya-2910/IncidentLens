"""Local storage utilities for raw log batches."""

import uuid
from collections.abc import Generator
from pathlib import Path

# Base storage directory
STORAGE_DIR = Path("storage/batches")


def get_batch_file_path(batch_id: uuid.UUID | str) -> Path:
    """Return the absolute Path for a given batch ID."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return STORAGE_DIR / f"{batch_id}.log"


def save_batch_content(batch_id: uuid.UUID | str, content: str | bytes) -> str:
    """Save raw batch content to local storage file, returning path string."""
    file_path = get_batch_file_path(batch_id)
    if isinstance(content, str):
        file_path.write_text(content, encoding="utf-8", errors="replace")
    else:
        file_path.write_bytes(content)
    return str(file_path.resolve())


def stream_batch_lines(file_path_str: str) -> Generator[str, None, None]:
    """Stream lines from a batch file without loading entire file into memory."""
    path = Path(file_path_str)
    if not path.exists():
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        yield from f


def delete_batch_file(file_path_str: str | None) -> None:
    """Remove a batch file from storage if it exists."""
    if file_path_str:
        p = Path(file_path_str)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
