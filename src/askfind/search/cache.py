"""Lightweight file-based cache for repeated search queries."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias


CACHE_DIR = Path.home() / ".cache" / "askfind"
CACHE_FILE = CACHE_DIR / "search_cache.json"
CACHE_VERSION = 1
MAX_CACHE_ENTRIES = 256
ROOT_FINGERPRINT_SAMPLE_LIMIT = 256


CacheEntry: TypeAlias = dict[str, object]
CacheEntries: TypeAlias = dict[str, CacheEntry]


@dataclass
class SearchCacheStats:
    hits: int = 0
    misses: int = 0
    sets: int = 0


def build_search_cache_key(
    *,
    query: str,
    root: Path,
    model: str,
    base_url: str,
    max_results: int,
    no_rerank: bool,
    respect_ignore_files: bool,
    follow_symlinks: bool,
    exclude_binary_files: bool,
    search_archives: bool,
    traversal_workers: int,
) -> str:
    payload = {
        "query": query,
        "root": str(root),
        "model": model,
        "base_url": base_url,
        "max_results": max_results,
        "no_rerank": no_rerank,
        "respect_ignore_files": respect_ignore_files,
        "follow_symlinks": follow_symlinks,
        "exclude_binary_files": exclude_binary_files,
        "search_archives": search_archives,
        "traversal_workers": traversal_workers,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compute_root_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    digest.update(str(root).encode("utf-8", errors="ignore"))

    try:
        root_stat = root.stat()
    except OSError:
        digest.update(b":missing")
        return digest.hexdigest()

    digest.update(f":{root_stat.st_dev}:{root_stat.st_ino}:{root_stat.st_mtime_ns}".encode("utf-8"))

    entries: list[tuple[str, int, int, int]] = []
    try:
        with os.scandir(root) as scanned:
            for entry in scanned:
                try:
                    stat = entry.stat(follow_symlinks=False)
                    is_dir = 1 if entry.is_dir(follow_symlinks=False) else 0
                except OSError:
                    continue
                entries.append((entry.name, is_dir, stat.st_mtime_ns, stat.st_size))
    except OSError:
        return digest.hexdigest()

    entries.sort(key=lambda item: item[0])
    for name, is_dir, mtime_ns, size in entries[:ROOT_FINGERPRINT_SAMPLE_LIMIT]:
        digest.update(name.encode("utf-8", errors="ignore"))
        digest.update(f":{is_dir}:{mtime_ns}:{size}".encode("utf-8"))
    return digest.hexdigest()


class SearchCache:
    def __init__(
        self,
        *,
        cache_path: Path = CACHE_FILE,
        ttl_seconds: int = 300,
        max_entries: int = MAX_CACHE_ENTRIES,
    ) -> None:
        self.cache_path = cache_path
        self.ttl_seconds = max(1, ttl_seconds)
        self.max_entries = max(1, max_entries)
        self._stats = SearchCacheStats()

    def get(self, *, key: str, root_fingerprint: str) -> list[Path] | None:
        entries = self._load_entries()
        now = time.time()
        changed = self._prune(entries, now=now)

        entry = entries.get(key)
        if entry is None:
            self._stats.misses += 1
            if changed:
                self._save_entries(entries)
            return None

        if entry.get("root_fingerprint") != root_fingerprint:
            self._stats.misses += 1
            if changed:
                self._save_entries(entries)
            return None

        paths_obj = entry.get("paths")
        if not isinstance(paths_obj, list) or not all(isinstance(p, str) for p in paths_obj):
            self._stats.misses += 1
            if changed:
                self._save_entries(entries)
            return None

        self._stats.hits += 1
        if changed:
            self._save_entries(entries)
        return [Path(p) for p in paths_obj]

    def set(self, *, key: str, root_fingerprint: str, paths: list[Path]) -> None:
        entries = self._load_entries()
        now = time.time()
        entries[key] = {
            "created_at": now,
            "root_fingerprint": root_fingerprint,
            "paths": [str(p) for p in paths],
        }
        self._stats.sets += 1
        self._prune(entries, now=now)
        self._save_entries(entries)

    def stats(self) -> dict[str, int]:
        return {
            "hits": self._stats.hits,
            "misses": self._stats.misses,
            "sets": self._stats.sets,
        }

    def _load_entries(self) -> CacheEntries:
        try:
            with self.cache_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(payload, dict):
            return {}
        if payload.get("version") != CACHE_VERSION:
            return {}
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, dict):
            return {}

        parsed: CacheEntries = {}
        for key, value in raw_entries.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            parsed[key] = {str(k): v for k, v in value.items() if isinstance(k, str)}
        return parsed

    def _save_entries(self, entries: CacheEntries) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = {
            "version": CACHE_VERSION,
            "entries": entries,
        }
        temp_path = self.cache_path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
        temp_path.replace(self.cache_path)
        self.cache_path.chmod(0o600)

    def _prune(self, entries: CacheEntries, *, now: float) -> bool:
        changed = False
        expired_keys: list[str] = []
        for key, entry in entries.items():
            created_at = entry.get("created_at")
            if not isinstance(created_at, (int, float)):
                expired_keys.append(key)
                continue
            if now - float(created_at) > self.ttl_seconds:
                expired_keys.append(key)
        for key in expired_keys:
            entries.pop(key, None)
            changed = True

        if len(entries) <= self.max_entries:
            return changed

        sortable: list[tuple[str, float]] = []
        for key, entry in entries.items():
            created_at = entry.get("created_at")
            if isinstance(created_at, (int, float)):
                sortable.append((key, float(created_at)))
        sortable.sort(key=lambda item: item[1], reverse=True)
        keep_keys = {key for key, _ in sortable[: self.max_entries]}
        removable = [key for key in entries if key not in keep_keys]
        for key in removable:
            entries.pop(key, None)
            changed = True
        return changed
