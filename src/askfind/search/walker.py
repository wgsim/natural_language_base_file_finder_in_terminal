"""Filesystem walker with filter-during-traversal."""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from askfind.search.filters import SearchFilters

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".hg", ".svn"}
IGNORE_FILES = (".gitignore", ".askfindignore")


@dataclass(frozen=True)
class _IgnoreRule:
    pattern: str
    anchored: bool
    directory_only: bool
    negated: bool

    def matches(self, relative_path: str, name: str, is_dir: bool) -> bool:
        if self.directory_only and not is_dir:
            return False

        if self.anchored:
            return fnmatch.fnmatch(relative_path, self.pattern)

        if "/" in self.pattern:
            return fnmatch.fnmatch(relative_path, self.pattern) or fnmatch.fnmatch(
                relative_path,
                f"**/{self.pattern}",
            )

        return fnmatch.fnmatch(name, self.pattern)


IgnoreMatcher = Callable[[Path, bool], bool]


def _load_ignore_rules(root: Path) -> list[_IgnoreRule]:
    rules: list[_IgnoreRule] = []
    for ignore_name in IGNORE_FILES:
        ignore_path = root / ignore_name
        if not ignore_path.is_file():
            continue
        try:
            lines = ignore_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            negated = line.startswith("!")
            if negated:
                line = line[1:].strip()
                if not line:
                    continue

            anchored = line.startswith("/")
            if anchored:
                line = line[1:]

            directory_only = line.endswith("/")
            line = line.rstrip("/")
            if not line:
                continue

            rules.append(
                _IgnoreRule(
                    pattern=line,
                    anchored=anchored,
                    directory_only=directory_only,
                    negated=negated,
                )
            )
    return rules


def _build_ignore_matcher(root: Path) -> IgnoreMatcher | None:
    rules = _load_ignore_rules(root)
    if not rules:
        return None

    def matcher(path: Path, is_dir: bool) -> bool:
        try:
            relative_path = path.relative_to(root).as_posix()
        except ValueError:
            return False

        ignored = False
        for rule in rules:
            if rule.matches(relative_path, path.name, is_dir):
                ignored = not rule.negated
        return ignored

    return matcher


def walk_and_filter(
    root: Path,
    filters: SearchFilters,
    max_results: int = 0,
    respect_ignore_files: bool = True,
) -> Generator[Path, None, None]:
    """Walk filesystem from root, yielding paths that match filters.

    Filters are applied during traversal in cheapest-first order.
    """
    ignore_matcher = _build_ignore_matcher(root) if respect_ignore_files else None
    count = 0
    for path in _scan_recursive(root, root, filters, depth=0, ignore_matcher=ignore_matcher):
        yield path
        count += 1
        if max_results and count >= max_results:
            return


def _scan_recursive(
    root: Path,
    directory: Path,
    filters: SearchFilters,
    depth: int,
    ignore_matcher: IgnoreMatcher | None,
) -> Generator[Path, None, None]:
    try:
        entries = os.scandir(directory)
    except PermissionError:
        return

    dirs_to_recurse: list[tuple[Path, int]] = []

    def schedule_recursion(is_dir: bool, path: Path, current_depth: int) -> None:
        """Schedule directory for recursion if it's a dir and within depth limit."""
        if is_dir and filters.matches_depth(current_depth + 1):
            dirs_to_recurse.append((path, current_depth + 1))

    with entries:
        for entry in entries:
            if entry.name in SKIP_DIRS:
                continue

            is_dir = entry.is_dir(follow_symlinks=False)
            is_file = entry.is_file(follow_symlinks=False)
            is_link = entry.is_symlink()
            entry_path = Path(entry.path)
            if ignore_matcher and ignore_matcher(entry_path, is_dir):
                continue

            # Tier 0: type and depth (no I/O)
            if not filters.matches_type(is_file=is_file, is_dir=is_dir, is_link=is_link):
                schedule_recursion(is_dir, entry_path, depth)
                continue

            if not filters.matches_depth(depth):
                schedule_recursion(is_dir, entry_path, depth)
                continue

            # Tier 1: name and path checks (no I/O)
            if not filters.matches_name(entry.name):
                schedule_recursion(is_dir, entry_path, depth)
                continue

            if not filters.matches_path(str(entry_path)):
                schedule_recursion(is_dir, entry_path, depth)
                continue

            # Tier 2: stat-based checks
            try:
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                schedule_recursion(is_dir, entry_path, depth)
                continue

            if not filters.matches_stat(stat):
                schedule_recursion(is_dir, entry_path, depth)
                continue

            # Tier 3: content checks (most expensive, files only)
            if filters.has:  # Content filter exists
                if is_file:
                    if not filters.matches_content(entry_path):
                        continue
                    yield entry_path
                else:
                    # Directory - skip yielding but recurse
                    schedule_recursion(is_dir, entry_path, depth)
            else:
                # No content filter - yield everything that passed
                yield entry_path
                schedule_recursion(is_dir, entry_path, depth)

    # Recurse into subdirectories
    for dir_path, next_depth in dirs_to_recurse:
        yield from _scan_recursive(root, dir_path, filters, next_depth, ignore_matcher)
