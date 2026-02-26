"""Filesystem walker with filter-during-traversal."""

from __future__ import annotations

import fnmatch
import os
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

from askfind.search.filters import SearchFilters

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".hg", ".svn"}
IGNORE_FILES = (".gitignore", ".askfindignore")
BINARY_PROBE_BYTES = 4096


@dataclass(frozen=True)
class _IgnoreRule:
    base_dir: Path
    pattern: str
    anchored: bool
    directory_only: bool
    negated: bool

    def matches(self, path: Path, is_dir: bool) -> bool:
        try:
            relative_path = path.relative_to(self.base_dir).as_posix()
        except ValueError:
            return False
        if not relative_path or relative_path == ".":
            return False
        if self.directory_only and not is_dir:
            return False

        if self.anchored:
            return fnmatch.fnmatch(relative_path, self.pattern)

        if "/" in self.pattern:
            return fnmatch.fnmatch(relative_path, self.pattern)

        # Pattern without slash applies to path components recursively.
        return any(fnmatch.fnmatch(part, self.pattern) for part in relative_path.split("/"))


@dataclass(frozen=True)
class _ScanOutcome:
    matches: tuple[Path, ...]
    recurse_dirs: tuple[tuple[Path, int, list[_IgnoreRule] | None], ...]


def _load_ignore_rules(base_dir: Path) -> list[_IgnoreRule]:
    rules: list[_IgnoreRule] = []
    for ignore_name in IGNORE_FILES:
        ignore_path = base_dir / ignore_name
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
                    base_dir=base_dir,
                    pattern=line,
                    anchored=anchored,
                    directory_only=directory_only,
                    negated=negated,
                )
            )
    return rules


def _is_ignored(path: Path, is_dir: bool, rules: list[_IgnoreRule]) -> bool:
    ignored = False
    for rule in rules:
        if rule.matches(path, is_dir):
            ignored = not rule.negated
    return ignored


def _is_within_root(root: Path, path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return resolved == root or root in resolved.parents


def _directory_visit_key(path: Path, follow_symlinks: bool) -> tuple[int, int] | None:
    try:
        stat = path.stat() if follow_symlinks else path.lstat()
    except OSError:
        return None
    return (stat.st_dev, stat.st_ino)


def _is_binary_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            sample = handle.read(BINARY_PROBE_BYTES)
    except OSError:
        return False
    if not sample:
        return False
    if b"\x00" in sample:
        return True
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def walk_and_filter(
    root: Path,
    filters: SearchFilters,
    max_results: int = 0,
    respect_ignore_files: bool = True,
    follow_symlinks: bool = False,
    exclude_binary_files: bool = True,
    traversal_workers: int = 1,
) -> Generator[Path, None, None]:
    """Walk filesystem from root, yielding paths that match filters.

    Filters are applied during traversal in cheapest-first order.
    """
    resolved_root = root.resolve()
    ignore_rules = _load_ignore_rules(resolved_root) if respect_ignore_files else None
    visited_dirs: set[tuple[int, int]] = set()
    root_key = _directory_visit_key(resolved_root, follow_symlinks=follow_symlinks)
    if root_key is not None:
        visited_dirs.add(root_key)

    workers = max(1, traversal_workers)
    scanner: Generator[Path, None, None]
    if workers > 1:
        scanner = _scan_parallel(
            root=resolved_root,
            filters=filters,
            ignore_rules=ignore_rules,
            follow_symlinks=follow_symlinks,
            exclude_binary_files=exclude_binary_files,
            visited_dirs=visited_dirs,
            workers=workers,
        )
    else:
        scanner = _scan_recursive(
            root=resolved_root,
            directory=resolved_root,
            filters=filters,
            depth=0,
            ignore_rules=ignore_rules,
            follow_symlinks=follow_symlinks,
            exclude_binary_files=exclude_binary_files,
            visited_dirs=visited_dirs,
        )

    count = 0
    try:
        for path in scanner:
            yield path
            count += 1
            if max_results and count >= max_results:
                return
    finally:
        scanner.close()


def _scan_directory(
    *,
    root: Path,
    directory: Path,
    filters: SearchFilters,
    depth: int,
    ignore_rules: list[_IgnoreRule] | None,
    follow_symlinks: bool,
    exclude_binary_files: bool,
) -> _ScanOutcome:
    try:
        entries = os.scandir(directory)
    except PermissionError:
        return _ScanOutcome(matches=(), recurse_dirs=())

    active_ignore_rules = ignore_rules
    if active_ignore_rules is not None and directory != root:
        local_rules = _load_ignore_rules(directory)
        if local_rules:
            active_ignore_rules = [*active_ignore_rules, *local_rules]

    matched_paths: list[Path] = []
    dirs_to_recurse: list[tuple[Path, int, list[_IgnoreRule] | None]] = []

    def schedule_recursion(is_dir: bool, path: Path, current_depth: int) -> None:
        """Schedule directory for recursion if it's a dir and within depth limit."""
        if not is_dir:
            return
        if not filters.matches_depth(current_depth + 1):
            return
        if follow_symlinks and not _is_within_root(root, path):
            return
        dirs_to_recurse.append((path, current_depth + 1, active_ignore_rules))

    with entries:
        for entry in entries:
            if entry.name in SKIP_DIRS:
                continue

            try:
                is_link = entry.is_symlink()
                is_dir = entry.is_dir(follow_symlinks=follow_symlinks)
                is_file = entry.is_file(follow_symlinks=follow_symlinks)
            except OSError:
                continue
            entry_path = Path(entry.path)
            if follow_symlinks and is_link and (is_dir or is_file) and not _is_within_root(root, entry_path):
                continue
            if active_ignore_rules and _is_ignored(entry_path, is_dir, active_ignore_rules):
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
                stat = entry.stat(follow_symlinks=follow_symlinks)
            except OSError:
                schedule_recursion(is_dir, entry_path, depth)
                continue

            if not filters.matches_stat(stat):
                schedule_recursion(is_dir, entry_path, depth)
                continue

            if exclude_binary_files and is_file and _is_binary_file(entry_path):
                continue

            # Tier 3: content checks (most expensive, files only)
            if filters.has:  # Content filter exists
                if is_file:
                    if not filters.matches_content(
                        entry_path,
                        follow_symlinks=follow_symlinks,
                    ):
                        continue
                    matched_paths.append(entry_path)
                else:
                    # Directory - skip yielding but recurse
                    schedule_recursion(is_dir, entry_path, depth)
            else:
                # No content filter - yield everything that passed
                matched_paths.append(entry_path)
                schedule_recursion(is_dir, entry_path, depth)

    return _ScanOutcome(
        matches=tuple(matched_paths),
        recurse_dirs=tuple(dirs_to_recurse),
    )


def _scan_recursive(
    root: Path,
    directory: Path,
    filters: SearchFilters,
    depth: int,
    ignore_rules: list[_IgnoreRule] | None,
    follow_symlinks: bool,
    exclude_binary_files: bool,
    visited_dirs: set[tuple[int, int]],
) -> Generator[Path, None, None]:
    outcome = _scan_directory(
        root=root,
        directory=directory,
        filters=filters,
        depth=depth,
        ignore_rules=ignore_rules,
        follow_symlinks=follow_symlinks,
        exclude_binary_files=exclude_binary_files,
    )
    for path in outcome.matches:
        yield path

    for dir_path, next_depth, next_ignore_rules in outcome.recurse_dirs:
        if follow_symlinks:
            dir_key = _directory_visit_key(dir_path, follow_symlinks=True)
            if dir_key is None:
                continue
            if dir_key in visited_dirs:
                continue
            visited_dirs.add(dir_key)
        yield from _scan_recursive(
            root=root,
            directory=dir_path,
            filters=filters,
            depth=next_depth,
            ignore_rules=next_ignore_rules,
            follow_symlinks=follow_symlinks,
            exclude_binary_files=exclude_binary_files,
            visited_dirs=visited_dirs,
        )


def _scan_parallel(
    *,
    root: Path,
    filters: SearchFilters,
    ignore_rules: list[_IgnoreRule] | None,
    follow_symlinks: bool,
    exclude_binary_files: bool,
    visited_dirs: set[tuple[int, int]],
    workers: int,
) -> Generator[Path, None, None]:
    pending: dict[Future[_ScanOutcome], None] = {}
    executor = ThreadPoolExecutor(max_workers=workers)
    try:
        root_future = executor.submit(
            _scan_directory,
            root=root,
            directory=root,
            filters=filters,
            depth=0,
            ignore_rules=ignore_rules,
            follow_symlinks=follow_symlinks,
            exclude_binary_files=exclude_binary_files,
        )
        pending[root_future] = None

        while pending:
            done, _ = wait(tuple(pending.keys()), return_when=FIRST_COMPLETED)
            for future in done:
                pending.pop(future, None)
                outcome = future.result()
                for path in outcome.matches:
                    yield path

                for dir_path, next_depth, next_ignore_rules in outcome.recurse_dirs:
                    if follow_symlinks:
                        dir_key = _directory_visit_key(dir_path, follow_symlinks=True)
                        if dir_key is None:
                            continue
                        if dir_key in visited_dirs:
                            continue
                        visited_dirs.add(dir_key)

                    next_future = executor.submit(
                        _scan_directory,
                        root=root,
                        directory=dir_path,
                        filters=filters,
                        depth=next_depth,
                        ignore_rules=next_ignore_rules,
                        follow_symlinks=follow_symlinks,
                        exclude_binary_files=exclude_binary_files,
                    )
                    pending[next_future] = None
    finally:
        for future in pending:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
