"""Filter dataclass and matching logic for file search."""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Maximum file size for content scanning (10 MB)
MAX_CONTENT_SCAN_BYTES = 10 * 1024 * 1024
CONTENT_SCAN_CHUNK_BYTES = 64 * 1024


def parse_size(s: str) -> int:
    s = s.strip().upper()
    multipliers = {"KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for suffix, mult in multipliers.items():
        if s.endswith(suffix):
            return int(float(s[: -len(suffix)]) * mult)
    # Handle both integer and decimal bytes (e.g., "100" or "1.5")
    return int(float(s))


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


def _file_contains_all_terms(filepath: Path, terms: list[str]) -> bool:
    """Scan file in chunks and return True when all terms are found."""
    pending_terms = set(terms)
    max_term_len = max(len(term) for term in pending_terms)
    overlap = max(0, max_term_len - 1)
    tail = ""

    with filepath.open("rb") as handle:
        while True:
            chunk = handle.read(CONTENT_SCAN_CHUNK_BYTES)
            if not chunk:
                break

            text = tail + chunk.decode("utf-8", errors="ignore")
            matched = {term for term in pending_terms if term in text}
            pending_terms -= matched
            if not pending_terms:
                return True

            tail = text[-overlap:] if overlap else ""

    return False


@dataclass
class SearchFilters:
    """Search filters extracted from natural language queries.

    Implemented filters:
    - ext, not_ext: File extension filtering
    - name, not_name: Glob pattern matching on filename
    - path, not_path: Path substring matching
    - regex: Regex matching on filename
    - fuzzy: Fuzzy subsequence matching on filename
    - mod: Modification time constraints
    - size: File size constraints
    - has: Content matching (all terms must be present)
    - type: File type (file, dir, link)
    - depth: Directory depth constraints
    - perm: Permission checks (r, w, x)

    Future/unimplemented filters (removed to avoid confusion):
    - cre: Creation time (not portable across filesystems)
    - acc: Access time (often disabled for performance)
    - newer: Newer than reference file
    - lines: Line count
    - cat: File category detection
    - owner: File owner matching
    """
    ext: list[str] | None = None
    not_ext: list[str] | None = None
    name: str | None = None
    not_name: str | None = None
    path: str | None = None
    not_path: str | None = None
    regex: str | None = None
    fuzzy: str | None = None
    mod: str | None = None
    size: str | None = None
    has: list[str] | None = None
    type: str | None = None
    depth: str | None = None
    perm: str | None = None
    _compiled_regex: re.Pattern[str] | None = field(default=None, init=False, repr=False)
    _ext_lower: frozenset[str] | None = field(default=None, init=False, repr=False)
    _not_ext_lower: frozenset[str] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        """Pre-compile regex and normalize extension sets for performance and safety."""
        # Pre-compile regex pattern with error handling to prevent ReDoS
        if self.regex:
            try:
                self._compiled_regex = re.compile(self.regex)
            except re.error:
                # Invalid regex from LLM - treat as no regex filter
                self._compiled_regex = None
                self.regex = None

        # Pre-compute lowercase extension sets for performance
        if self.ext:
            self._ext_lower = frozenset(e.lower() for e in self.ext)
        if self.not_ext:
            self._not_ext_lower = frozenset(e.lower() for e in self.not_ext)

    def matches_name(self, filename: str) -> bool:
        # Use pre-computed extension sets for better performance
        if self._ext_lower is not None:
            _, file_ext = os.path.splitext(filename)
            if file_ext.lower() not in self._ext_lower:
                return False
        if self._not_ext_lower is not None:
            _, file_ext = os.path.splitext(filename)
            if file_ext.lower() in self._not_ext_lower:
                return False
        if self.name and not fnmatch.fnmatch(filename, self.name):
            return False
        if self.not_name and fnmatch.fnmatch(filename, self.not_name):
            return False
        # Use pre-compiled regex to prevent ReDoS and handle invalid patterns
        if self._compiled_regex is not None:
            if not self._compiled_regex.search(filename):
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
            try:
                size_bytes = parse_size(val)
            except (ValueError, OverflowError):
                size_bytes = None
            if size_bytes is not None:
                if op == ">" and stat.st_size <= size_bytes:
                    return False
                if op == "<" and stat.st_size >= size_bytes:
                    return False
        if self.mod:
            op, val = _parse_constraint(self.mod)
            try:
                delta = parse_time_delta(val)
            except (ValueError, OverflowError):
                delta = None
            if delta is not None:
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
            # Skip symlinks to prevent reading files outside search root
            if filepath.is_symlink():
                return False
            # Check file size to prevent OOM on large files
            file_size = filepath.stat().st_size
            if file_size > MAX_CONTENT_SCAN_BYTES:
                return False
            return _file_contains_all_terms(filepath, self.has)
        except (OSError, UnicodeDecodeError):
            return False


def _fuzzy_match(pattern: str, text: str) -> bool:
    """Simple subsequence fuzzy match."""
    p_idx = 0
    for char in text:
        if p_idx < len(pattern) and char == pattern[p_idx]:
            p_idx += 1
    return p_idx == len(pattern)
