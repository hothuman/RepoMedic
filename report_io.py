"""Atomic local report export; never leave an incomplete output file."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_save_text(destination: Path, content: str) -> None:
    """Write UTF-8 to a temporary sibling, then replace the target atomically.

    No directory creation is performed. Existing outputs are replaced only once
    the entire report was written successfully. Temp files are cleaned on error.
    """
    target = Path(destination)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=target.parent, prefix=".repomedic-",
                                         suffix=".tmp", delete=False) as stream:
            temporary = stream.name
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
