"""Persistent file index management for askfind."""

from __future__ import annotations

import hashlib
import json
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


def build_index(*, root: Path, options: IndexOptions) -> IndexBuildResult:
    """Build a new index for root and overwrite any existing one."""
    _assert_root_is_directory(root)
    file_paths = _collect_file_paths(root=root, options=options)
    root_fingerprint = compute_root_fingerprint(root)
    index_path = _index_path_for_root(root)
    payload = {
        "version": INDEX_VERSION,
        "root": str(root),
        "created_at": time.time(),
        "root_fingerprint": root_fingerprint,
        "options": {
            "respect_ignore_files": options.respect_ignore_files,
            "follow_symlinks": options.follow_symlinks,
            "exclude_binary_files": options.exclude_binary_files,
            "traversal_workers": options.traversal_workers,
        },
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


def clear_index(*, root: Path) -> IndexClearResult:
    """Remove the index file for root."""
    index_path = _index_path_for_root(root)
    try:
        index_path.unlink()
        cleared = True
    except FileNotFoundError:
        cleared = False
    return IndexClearResult(root=root, index_path=index_path, cleared=cleared)


def _assert_root_is_directory(root: Path) -> None:
    if not root.exists():
        raise FileNotFoundError(str(root))
    if not root.is_dir():
        raise NotADirectoryError(str(root))


def _collect_file_paths(*, root: Path, options: IndexOptions) -> list[str]:
    filters = SearchFilters(type="file")
    files = walk_and_filter(
        root,
        filters,
        max_results=0,
        respect_ignore_files=options.respect_ignore_files,
        follow_symlinks=options.follow_symlinks,
        exclude_binary_files=options.exclude_binary_files,
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
    raw_paths = payload.get("paths")
    if not isinstance(root_fingerprint, str):
        return None
    if not isinstance(raw_paths, list) or not all(isinstance(path, str) for path in raw_paths):
        return None
    return _StoredIndexPayload(root_fingerprint=root_fingerprint, paths=tuple(raw_paths))


def _write_payload(*, index_path: Path, payload: dict[str, object]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp_path = index_path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
    temp_path.replace(index_path)
    index_path.chmod(0o600)
