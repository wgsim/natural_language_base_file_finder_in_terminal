"""Filesystem walker with filter-during-traversal."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from askfind.search.filters import SearchFilters

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".hg", ".svn"}


def walk_and_filter(
    root: Path,
    filters: SearchFilters,
    max_results: int = 0,
) -> Generator[Path, None, None]:
    """Walk filesystem from root, yielding paths that match filters.

    Filters are applied during traversal in cheapest-first order.
    """
    count = 0
    for path in _scan_recursive(root, filters, depth=0):
        yield path
        count += 1
        if max_results and count >= max_results:
            return


def _scan_recursive(
    directory: Path,
    filters: SearchFilters,
    depth: int,
) -> Generator[Path, None, None]:
    try:
        entries = os.scandir(directory)
    except PermissionError:
        return

    dirs_to_recurse: list[tuple[Path, int]] = []

    with entries:
        for entry in entries:
            if entry.name in SKIP_DIRS:
                continue

            is_dir = entry.is_dir(follow_symlinks=False)
            is_file = entry.is_file(follow_symlinks=False)
            is_link = entry.is_symlink()
            entry_path = Path(entry.path)

            # Tier 0: type and depth (no I/O)
            if not filters.matches_type(is_file=is_file, is_dir=is_dir, is_link=is_link):
                if is_dir and filters.matches_depth(depth + 1):
                    dirs_to_recurse.append((entry_path, depth + 1))
                continue

            if not filters.matches_depth(depth):
                if is_dir and filters.matches_depth(depth + 1):
                    dirs_to_recurse.append((entry_path, depth + 1))
                continue

            # Tier 1: name and path checks (no I/O)
            if not filters.matches_name(entry.name):
                if is_dir and filters.matches_depth(depth + 1):
                    dirs_to_recurse.append((entry_path, depth + 1))
                continue

            if not filters.matches_path(str(entry_path)):
                if is_dir and filters.matches_depth(depth + 1):
                    dirs_to_recurse.append((entry_path, depth + 1))
                continue

            # Tier 2: stat-based checks
            try:
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                if is_dir and filters.matches_depth(depth + 1):
                    dirs_to_recurse.append((entry_path, depth + 1))
                continue

            if not filters.matches_stat(stat):
                if is_dir and filters.matches_depth(depth + 1):
                    dirs_to_recurse.append((entry_path, depth + 1))
                continue

            # Tier 3: content checks (most expensive, files only)
            if filters.has:  # Content filter exists
                if is_file:
                    if not filters.matches_content(entry_path):
                        continue
                    yield entry_path
                else:
                    # Directory - skip yielding but recurse
                    if is_dir and filters.matches_depth(depth + 1):
                        dirs_to_recurse.append((entry_path, depth + 1))
            else:
                # No content filter - yield everything that passed
                yield entry_path
                if is_dir and filters.matches_depth(depth + 1):
                    dirs_to_recurse.append((entry_path, depth + 1))

    # Recurse into subdirectories
    for dir_path, next_depth in dirs_to_recurse:
        yield from _scan_recursive(dir_path, filters, next_depth)
