"""Filter dataclass and matching logic for file search."""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path


def parse_size(s: str) -> int:
    s = s.strip().upper()
    multipliers = {"KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for suffix, mult in multipliers.items():
        if s.endswith(suffix):
            return int(float(s[: -len(suffix)]) * mult)
    return int(s)


def parse_time_delta(s: str) -> timedelta:
    s = s.strip().lower()
    units = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
    for suffix, kwarg in units.items():
        if s.endswith(suffix):
            value = int(s[: -len(suffix)])
            return timedelta(**{kwarg: value})
    return timedelta(days=int(s))


def _parse_constraint(s: str) -> tuple[str, str]:
    """Parse '>7d' into ('>', '7d') or '<1MB' into ('<', '1MB')."""
    if s.startswith(">"):
        return ">", s[1:]
    if s.startswith("<"):
        return "<", s[1:]
    return "=", s


@dataclass
class SearchFilters:
    ext: list[str] | None = None
    not_ext: list[str] | None = None
    name: str | None = None
    not_name: str | None = None
    path: str | None = None
    not_path: str | None = None
    regex: str | None = None
    fuzzy: str | None = None
    mod: str | None = None
    cre: str | None = None
    acc: str | None = None
    newer: str | None = None
    size: str | None = None
    lines: str | None = None
    has: list[str] | None = None
    type: str | None = None
    cat: str | None = None
    depth: str | None = None
    perm: str | None = None
    owner: str | None = None

    def matches_name(self, filename: str) -> bool:
        if self.ext is not None:
            _, file_ext = os.path.splitext(filename)
            if file_ext.lower() not in [e.lower() for e in self.ext]:
                return False
        if self.not_ext is not None:
            _, file_ext = os.path.splitext(filename)
            if file_ext.lower() in [e.lower() for e in self.not_ext]:
                return False
        if self.name and not fnmatch.fnmatch(filename, self.name):
            return False
        if self.not_name and fnmatch.fnmatch(filename, self.not_name):
            return False
        if self.regex and not re.search(self.regex, filename):
            return False
        if self.fuzzy:
            if not _fuzzy_match(self.fuzzy.lower(), filename.lower()):
                return False
        return True

    def matches_path(self, filepath: str) -> bool:
        if self.path and self.path not in filepath:
            return False
        if self.not_path and self.not_path in filepath:
            return False
        return True

    def matches_type(self, is_file: bool, is_dir: bool, is_link: bool) -> bool:
        if self.type is None:
            return True
        if self.type == "file":
            return is_file
        if self.type == "dir":
            return is_dir
        if self.type == "link":
            return is_link
        return True

    def matches_depth(self, depth: int) -> bool:
        if self.depth is None:
            return True
        op, val = _parse_constraint(self.depth)
        limit = int(val)
        if op == "<":
            return depth < limit
        if op == ">":
            return depth > limit
        return depth == limit

    def matches_stat(self, stat: os.stat_result) -> bool:
        if self.size:
            op, val = _parse_constraint(self.size)
            size_bytes = parse_size(val)
            if op == ">" and stat.st_size <= size_bytes:
                return False
            if op == "<" and stat.st_size >= size_bytes:
                return False
        if self.mod:
            op, val = _parse_constraint(self.mod)
            delta = parse_time_delta(val)
            cutoff = datetime.now(timezone.utc) - delta
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            if op == ">" and mtime < cutoff:
                return False
            if op == "<" and mtime > cutoff:
                return False
        if self.perm:
            mode = stat.st_mode
            if "x" in self.perm and not (mode & 0o111):
                return False
            if "w" in self.perm and not (mode & 0o222):
                return False
            if "r" in self.perm and not (mode & 0o444):
                return False
        return True

    def matches_content(self, filepath: Path) -> bool:
        if not self.has:
            return True
        try:
            text = filepath.read_text(errors="ignore")
            return all(term in text for term in self.has)
        except (OSError, UnicodeDecodeError):
            return False


def _fuzzy_match(pattern: str, text: str) -> bool:
    """Simple subsequence fuzzy match."""
    p_idx = 0
    for char in text:
        if p_idx < len(pattern) and char == pattern[p_idx]:
            p_idx += 1
    return p_idx == len(pattern)
