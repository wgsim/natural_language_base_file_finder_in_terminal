"""Format search results for terminal output."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class FileResult:
    path: Path
    size: int
    modified: datetime

    @classmethod
    def from_path(cls, path: Path) -> FileResult:
        stat = path.stat()
        return cls(
            path=path,
            size=stat.st_size,
            modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        )


def format_plain(results: list[FileResult]) -> str:
    if not results:
        return ""
    return "\n".join(str(r.path) for r in results)


def format_verbose(results: list[FileResult]) -> str:
    if not results:
        return ""
    lines = []
    for r in results:
        size_str = human_size(r.size)
        date_str = r.modified.strftime("%b %d %Y")
        lines.append(f"{r.path}  {size_str}  {date_str}")
    return "\n".join(lines)


def format_json(results: list[FileResult]) -> str:
    data = [
        {
            "path": str(r.path),
            "size": r.size,
            "modified": r.modified.strftime("%Y-%m-%d"),
        }
        for r in results
    ]
    return json.dumps(data, indent=2)


def human_size(nbytes: int | float) -> str:
    """Convert bytes to human-readable size string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if nbytes < 1024:
            if unit == "B":
                return f"{nbytes} {unit}"
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"
