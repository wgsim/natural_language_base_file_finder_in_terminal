"""Persistent file index management for askfind."""

from __future__ import annotations

import hashlib
import json
import stat
import time
from dataclasses import dataclass
from pathlib import Path

from askfind.search.cache import CACHE_DIR, compute_root_fingerprint
from askfind.search.filters import SearchFilters
from askfind.search.walker import walk_and_filter


INDEX_VERSION = 1
INDEX_DIR = CACHE_DIR / "indexes"


@dataclass(frozen=True)
class IndexOptions:
    """Traversal options used when building or updating an index."""

    respect_ignore_files: bool
    follow_symlinks: bool
    exclude_binary_files: bool
    search_archives: bool
    traversal_workers: int


@dataclass(frozen=True)
class IndexBuildResult:
    """Summary information for index build/update operations."""

    root: Path
    index_path: Path
    file_count: int
    root_fingerprint: str


@dataclass(frozen=True)
class IndexStatusResult:
    """Summary information for index status checks."""

    root: Path
    index_path: Path
    exists: bool
    file_count: int
    stale: bool


@dataclass(frozen=True)
class IndexClearResult:
    """Summary information for index clear operations."""

    root: Path
    index_path: Path
    cleared: bool


@dataclass(frozen=True)
class _StoredIndexPayload:
    root_fingerprint: str
    paths: tuple[str, ...]
    options: IndexOptions | None


@dataclass
class IndexQueryDiagnostics:
    """Diagnostics emitted for index query fallback paths."""

    fallback_reason: str | None = None


def build_index(*, root: Path, options: IndexOptions) -> IndexBuildResult:
    """Build a new index for root and overwrite any existing one."""
    _assert_root_is_directory(root)
    normalized_options = _normalize_options(options)
    file_paths = _collect_file_paths(root=root, options=normalized_options)
    root_fingerprint = compute_root_fingerprint(root)
    index_path = _index_path_for_root(root)
    payload = {
        "version": INDEX_VERSION,
        "root": str(root),
        "created_at": time.time(),
        "root_fingerprint": root_fingerprint,
        "options": _serialize_options(normalized_options),
        "paths": file_paths,
    }
    _write_payload(index_path=index_path, payload=payload)
    return IndexBuildResult(
        root=root,
        index_path=index_path,
        file_count=len(file_paths),
        root_fingerprint=root_fingerprint,
    )


def update_index(*, root: Path, options: IndexOptions) -> IndexBuildResult:
    """Refresh an existing index; creates a new one if missing."""
    return build_index(root=root, options=options)


def get_index_status(*, root: Path) -> IndexStatusResult:
    """Return status summary for the index associated with root."""
    index_path = _index_path_for_root(root)
    payload = _read_payload(index_path=index_path)
    if payload is None:
        return IndexStatusResult(
            root=root,
            index_path=index_path,
            exists=False,
            file_count=0,
            stale=True,
        )
    current_root_fingerprint = compute_root_fingerprint(root)
    return IndexStatusResult(
        root=root,
        index_path=index_path,
        exists=True,
        file_count=len(payload.paths),
        stale=payload.root_fingerprint != current_root_fingerprint,
    )


def query_index(
    *,
    root: Path,
    filters: SearchFilters,
    max_results: int,
    options: IndexOptions,
    diagnostics: IndexQueryDiagnostics | None = None,
) -> list[Path] | None:
    """Query an existing index.

    Returns a list of matched paths when the index is usable, otherwise None.
    None means callers should fall back to live filesystem traversal.
    """
    if diagnostics is not None:
        diagnostics.fallback_reason = None
    if not isinstance(filters, SearchFilters):
        _set_fallback_reason(diagnostics, "invalid_filters")
        return None
    if not _supports_index_query(filters):
        _set_fallback_reason(diagnostics, "unsupported_filters")
        return None

    index_path = _index_path_for_root(root)
    payload = _read_payload(index_path=index_path)
    if payload is None:
        _set_fallback_reason(diagnostics, "missing_or_invalid_index")
        return None

    normalized_options = _normalize_options(options)
    if normalized_options.search_archives:
        _set_fallback_reason(diagnostics, "unsupported_search_archives")
        return None
    if payload.options is None or payload.options != normalized_options:
        _set_fallback_reason(diagnostics, "options_mismatch")
        return None

    current_root_fingerprint = compute_root_fingerprint(root)
    if payload.root_fingerprint != current_root_fingerprint:
        _set_fallback_reason(diagnostics, "stale_index")
        return None

    try:
        resolved_root = root.resolve(strict=False)
    except OSError:
        _set_fallback_reason(diagnostics, "root_resolve_failed")
        return None

    matches: list[Path] = []
    for raw_path in payload.paths:
        path = Path(raw_path)
        if _matches_indexed_path(
            root=resolved_root,
            path=path,
            filters=filters,
            follow_symlinks=normalized_options.follow_symlinks,
        ):
            matches.append(path)
            if max_results and len(matches) >= max_results:
                break
    return matches


def _set_fallback_reason(
    diagnostics: IndexQueryDiagnostics | None,
    reason: str,
) -> None:
    if diagnostics is not None:
        diagnostics.fallback_reason = reason


def clear_index(*, root: Path) -> IndexClearResult:
    """Remove the index file for root."""
    index_path = _index_path_for_root(root)
    try:
        index_path.unlink()
        cleared = True
    except FileNotFoundError:
        cleared = False
    return IndexClearResult(root=root, index_path=index_path, cleared=cleared)


def _normalize_options(options: IndexOptions) -> IndexOptions:
    return IndexOptions(
        respect_ignore_files=options.respect_ignore_files,
        follow_symlinks=options.follow_symlinks,
        exclude_binary_files=options.exclude_binary_files,
        search_archives=options.search_archives,
        traversal_workers=max(1, options.traversal_workers),
    )


def _assert_root_is_directory(root: Path) -> None:
    if not root.exists():
        raise FileNotFoundError(str(root))
    if not root.is_dir():
        raise NotADirectoryError(str(root))


def _serialize_options(options: IndexOptions) -> dict[str, object]:
    return {
        "respect_ignore_files": options.respect_ignore_files,
        "follow_symlinks": options.follow_symlinks,
        "exclude_binary_files": options.exclude_binary_files,
        "search_archives": options.search_archives,
        "traversal_workers": options.traversal_workers,
    }


def _supports_index_query(filters: SearchFilters) -> bool:
    return filters.type == "file"


def _matches_indexed_path(
    *,
    root: Path,
    path: Path,
    filters: SearchFilters,
    follow_symlinks: bool,
) -> bool:
    try:
        resolved_path = path.resolve(strict=False)
    except OSError:
        return False
    if resolved_path != root and root not in resolved_path.parents:
        return False

    try:
        is_link = path.is_symlink()
        entry_stat = path.stat(follow_symlinks=follow_symlinks)
        is_dir = stat.S_ISDIR(entry_stat.st_mode)
        is_file = stat.S_ISREG(entry_stat.st_mode)
    except OSError:
        return False

    if not filters.matches_type(is_file=is_file, is_dir=is_dir, is_link=is_link):
        return False

    try:
        relative_path = path.relative_to(root)
    except ValueError:
        return False
    depth = len(relative_path.parts) - 1
    if not filters.matches_depth(depth):
        return False

    if not filters.matches_name(path.name):
        return False
    if not filters.matches_path(str(path)):
        return False

    if not filters.matches_stat(entry_stat):
        return False

    if is_file and not filters.matches_tags(path, follow_symlinks=follow_symlinks):
        return False

    if is_file and not filters.matches_language(path, follow_symlinks=follow_symlinks):
        return False

    if is_file and not filters.matches_license(path, follow_symlinks=follow_symlinks):
        return False

    if is_file and not filters.matches_similarity(
        path,
        root=root,
        follow_symlinks=follow_symlinks,
    ):
        return False

    if is_file and not filters.matches_code_metrics(path, follow_symlinks=follow_symlinks):
        return False

    if filters.has and not filters.matches_content(path, follow_symlinks=follow_symlinks):
        return False

    return True


def _collect_file_paths(*, root: Path, options: IndexOptions) -> list[str]:
    filters = SearchFilters(type="file")
    files = walk_and_filter(
        root,
        filters,
        max_results=0,
        respect_ignore_files=options.respect_ignore_files,
        follow_symlinks=options.follow_symlinks,
        exclude_binary_files=options.exclude_binary_files,
        search_archives=options.search_archives,
        traversal_workers=max(1, options.traversal_workers),
    )
    return sorted(str(path) for path in files)


def _index_path_for_root(root: Path) -> Path:
    digest = hashlib.sha256(str(root).encode("utf-8", errors="ignore")).hexdigest()
    return INDEX_DIR / f"{digest}.json"


def _read_payload(*, index_path: Path) -> _StoredIndexPayload | None:
    try:
        with index_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != INDEX_VERSION:
        return None
    root_fingerprint = payload.get("root_fingerprint")
    raw_options = payload.get("options")
    raw_paths = payload.get("paths")
    if not isinstance(root_fingerprint, str):
        return None
    options: IndexOptions | None
    if raw_options is None:
        options = None
    else:
        options = _parse_options(raw_options)
        if options is None:
            return None
    if not isinstance(raw_paths, list) or not all(isinstance(path, str) for path in raw_paths):
        return None
    return _StoredIndexPayload(
        root_fingerprint=root_fingerprint,
        paths=tuple(raw_paths),
        options=options,
    )


def _parse_options(raw_options: object) -> IndexOptions | None:
    if not isinstance(raw_options, dict):
        return None
    respect_ignore_files = raw_options.get("respect_ignore_files")
    follow_symlinks = raw_options.get("follow_symlinks")
    exclude_binary_files = raw_options.get("exclude_binary_files")
    search_archives = raw_options.get("search_archives")
    traversal_workers = raw_options.get("traversal_workers")
    if not isinstance(respect_ignore_files, bool):
        return None
    if not isinstance(follow_symlinks, bool):
        return None
    if not isinstance(exclude_binary_files, bool):
        return None
    if not isinstance(search_archives, bool):
        return None
    if not isinstance(traversal_workers, int) or isinstance(traversal_workers, bool):
        return None
    return _normalize_options(
        IndexOptions(
            respect_ignore_files=respect_ignore_files,
            follow_symlinks=follow_symlinks,
            exclude_binary_files=exclude_binary_files,
            search_archives=search_archives,
            traversal_workers=traversal_workers,
        )
    )


def _write_payload(*, index_path: Path, payload: dict[str, object]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp_path = index_path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
    temp_path.replace(index_path)
    index_path.chmod(0o600)
