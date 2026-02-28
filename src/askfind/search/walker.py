"""Filesystem walker with filter-during-traversal."""

from __future__ import annotations

import fnmatch
import os
import tarfile
import zipfile
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from askfind.search.filters import CONTENT_SCAN_CHUNK_BYTES, MAX_CONTENT_SCAN_BYTES, SearchFilters

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".hg", ".svn"}
IGNORE_FILES = (".gitignore", ".askfindignore")
BINARY_PROBE_BYTES = 4096
ARCHIVE_SUFFIXES = (".zip", ".tar.gz")
ARCHIVE_MEMBER_PATH_DELIMITER = "::"


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


@dataclass
class _SearchBudget:
    remaining: int | None

    def exhausted(self) -> bool:
        return self.remaining == 0

    def consume_match(self) -> None:
        if self.remaining is None:
            return
        if self.remaining > 0:
            self.remaining -= 1


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


def _is_supported_archive(path: Path, *, is_file: bool) -> bool:
    if not is_file:
        return False
    lowered = path.name.lower()
    return any(lowered.endswith(suffix) for suffix in ARCHIVE_SUFFIXES)


def _member_matches_name_and_path(
    *,
    archive_path: Path,
    member_path: str,
    filters: SearchFilters,
) -> bool:
    member_name = Path(member_path).name
    synthetic_path = (
        f"{archive_path.as_posix()}{ARCHIVE_MEMBER_PATH_DELIMITER}{member_path}"
    )
    if not filters.matches_name(member_name):
        return False
    if not filters.matches_path(synthetic_path):
        return False
    return True


def _stream_contains_all_terms(handle: IO[bytes], terms: list[str]) -> bool:
    pending_terms = set(terms)
    max_term_len = max(len(term) for term in pending_terms)
    overlap = max(0, max_term_len - 1)
    tail = ""

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


def _zip_archive_matches_filters(archive_path: Path, filters: SearchFilters) -> bool:
    try:
        with zipfile.ZipFile(archive_path, "r") as handle:
            for info in handle.infolist():
                if info.is_dir():
                    continue
                member_path = info.filename
                if not _member_matches_name_and_path(
                    archive_path=archive_path,
                    member_path=member_path,
                    filters=filters,
                ):
                    continue
                if not filters.has:
                    return True
                if info.file_size > MAX_CONTENT_SCAN_BYTES:
                    continue
                try:
                    with handle.open(info, "r") as member_handle:
                        if _stream_contains_all_terms(member_handle, filters.has):
                            return True
                except OSError:
                    continue
    except (OSError, zipfile.BadZipFile):
        return False
    return False


def _tar_gz_archive_matches_filters(archive_path: Path, filters: SearchFilters) -> bool:
    try:
        with tarfile.open(archive_path, "r:gz") as handle:
            for member in handle.getmembers():
                if not member.isfile():
                    continue
                member_path = member.name
                if not _member_matches_name_and_path(
                    archive_path=archive_path,
                    member_path=member_path,
                    filters=filters,
                ):
                    continue
                if not filters.has:
                    return True
                if member.size > MAX_CONTENT_SCAN_BYTES:
                    continue
                try:
                    extracted = handle.extractfile(member)
                except (tarfile.TarError, OSError):
                    continue
                if extracted is None:
                    continue
                with extracted:
                    if _stream_contains_all_terms(extracted, filters.has):
                        return True
    except (OSError, tarfile.TarError):
        return False
    return False


def _should_scan_archive_members(
    *,
    search_archives: bool,
    supported_archive: bool,
    direct_match: bool,
    has_content_filter: bool,
) -> bool:
    if not search_archives or not supported_archive:
        return False
    if has_content_filter:
        return True
    return not direct_match


def _archive_matches_filters(archive_path: Path, filters: SearchFilters) -> bool:
    lowered = archive_path.name.lower()
    if lowered.endswith(".zip"):
        return _zip_archive_matches_filters(archive_path, filters)
    if lowered.endswith(".tar.gz"):
        return _tar_gz_archive_matches_filters(archive_path, filters)
    return False


def walk_and_filter(
    root: Path,
    filters: SearchFilters,
    max_results: int = 0,
    respect_ignore_files: bool = True,
    follow_symlinks: bool = False,
    exclude_binary_files: bool = True,
    search_archives: bool = False,
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
    budget = _SearchBudget(remaining=max_results if max_results > 0 else None)
    scanner: Generator[Path, None, None]
    if workers > 1:
        scanner = _scan_parallel(
            root=resolved_root,
            filters=filters,
            ignore_rules=ignore_rules,
            follow_symlinks=follow_symlinks,
            exclude_binary_files=exclude_binary_files,
            search_archives=search_archives,
            visited_dirs=visited_dirs,
            workers=workers,
            budget=budget,
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
            search_archives=search_archives,
            visited_dirs=visited_dirs,
            budget=budget,
        )

    try:
        for path in scanner:
            yield path
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
    search_archives: bool,
    remaining_matches: int | None,
) -> _ScanOutcome:
    if remaining_matches == 0:
        return _ScanOutcome(matches=(), recurse_dirs=())

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
            direct_name_match = filters.matches_name(entry.name)
            direct_path_match = filters.matches_path(str(entry_path))
            direct_match = direct_name_match and direct_path_match
            supported_archive = _is_supported_archive(entry_path, is_file=is_file)
            archive_match = False
            if _should_scan_archive_members(
                search_archives=search_archives,
                supported_archive=supported_archive,
                direct_match=direct_match,
                has_content_filter=bool(filters.has),
            ):
                archive_match = _archive_matches_filters(entry_path, filters)

            if not direct_match and not archive_match:
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

            if is_file and not filters.matches_tags(
                entry_path,
                follow_symlinks=follow_symlinks,
            ):
                continue

            if exclude_binary_files and is_file and _is_binary_file(entry_path) and not archive_match:
                continue

            if is_file and not filters.matches_language(
                entry_path,
                follow_symlinks=follow_symlinks,
            ):
                continue

            if is_file and not filters.matches_license(
                entry_path,
                follow_symlinks=follow_symlinks,
            ):
                continue

            # Tier 3: content checks (most expensive, files only)
            if filters.has:  # Content filter exists
                if is_file:
                    if supported_archive and search_archives:
                        if not archive_match:
                            continue
                    else:
                        if not filters.matches_content(
                            entry_path,
                            follow_symlinks=follow_symlinks,
                        ):
                            continue
                    matched_paths.append(entry_path)
                    if remaining_matches is not None and len(matched_paths) >= remaining_matches:
                        break
                else:
                    # Directory - skip yielding but recurse
                    schedule_recursion(is_dir, entry_path, depth)
            else:
                # No content filter - yield everything that passed
                matched_paths.append(entry_path)
                if remaining_matches is not None and len(matched_paths) >= remaining_matches:
                    break
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
    search_archives: bool,
    visited_dirs: set[tuple[int, int]],
    budget: _SearchBudget,
) -> Generator[Path, None, None]:
    if budget.exhausted():
        return

    outcome = _scan_directory(
        root=root,
        directory=directory,
        filters=filters,
        depth=depth,
        ignore_rules=ignore_rules,
        follow_symlinks=follow_symlinks,
        exclude_binary_files=exclude_binary_files,
        search_archives=search_archives,
        remaining_matches=budget.remaining,
    )
    for path in outcome.matches:
        if budget.exhausted():
            return
        yield path
        budget.consume_match()
        if budget.exhausted():
            return

    for dir_path, next_depth, next_ignore_rules in outcome.recurse_dirs:
        if budget.exhausted():
            return
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
            search_archives=search_archives,
            visited_dirs=visited_dirs,
            budget=budget,
        )


def _scan_parallel(
    *,
    root: Path,
    filters: SearchFilters,
    ignore_rules: list[_IgnoreRule] | None,
    follow_symlinks: bool,
    exclude_binary_files: bool,
    search_archives: bool,
    visited_dirs: set[tuple[int, int]],
    workers: int,
    budget: _SearchBudget,
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
            search_archives=search_archives,
            remaining_matches=budget.remaining,
        )
        pending[root_future] = None

        while pending and not budget.exhausted():
            done, _ = wait(tuple(pending.keys()), return_when=FIRST_COMPLETED)
            for future in done:
                if budget.exhausted():
                    break
                pending.pop(future, None)
                outcome = future.result()
                for path in outcome.matches:
                    if budget.exhausted():
                        break
                    yield path
                    budget.consume_match()
                if budget.exhausted():
                    break

                for dir_path, next_depth, next_ignore_rules in outcome.recurse_dirs:
                    if budget.exhausted():
                        break
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
                        search_archives=search_archives,
                        remaining_matches=budget.remaining,
                    )
                    pending[next_future] = None
    finally:
        for future in pending:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
