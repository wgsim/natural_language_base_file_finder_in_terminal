"""OpenAI-compatible LLM HTTP client."""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from threading import RLock
from time import monotonic, time
from types import TracebackType
from typing import ClassVar, TypedDict, cast

import httpx

from askfind.llm.prompt import build_system_prompt


class _ChatMessage(TypedDict):
    content: str


class _ChatChoice(TypedDict):
    message: _ChatMessage


class _ChatResponse(TypedDict):
    choices: list[_ChatChoice]


class _ExtractFiltersCacheStats(TypedDict):
    size: int
    hits: int
    misses: int
    ttl_seconds: float
    max_entries: int


_ExtractFiltersCacheKey = tuple[str, str, str]
_ExtractFiltersCacheEntry = tuple[float, str]


class _ExtractFiltersDiskCacheEntry(TypedDict):
    content: str
    created_at: float
    expires_at: float


class LLMResponseSchemaError(ValueError):
    """Raised when LLM response payload does not match expected schema."""


class LLMClient:
    """Client for OpenAI-compatible chat completion APIs."""

    _EXTRACT_FILTERS_CACHE_TTL_SECONDS: ClassVar[float] = 300.0
    _EXTRACT_FILTERS_CACHE_MAX_ENTRIES: ClassVar[int] = 256
    _EXTRACT_FILTERS_DISK_CACHE_VERSION: ClassVar[int] = 1
    _EXTRACT_FILTERS_DISK_CACHE_FILE: ClassVar[Path] = (
        Path.home() / ".cache" / "askfind" / "extract_filters_cache.json"
    )
    _extract_filters_cache: ClassVar[
        OrderedDict[_ExtractFiltersCacheKey, _ExtractFiltersCacheEntry]
    ] = OrderedDict()
    _extract_filters_cache_hits: ClassVar[int] = 0
    _extract_filters_cache_misses: ClassVar[int] = 0
    _extract_filters_cache_lock: ClassVar[RLock] = RLock()

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
            verify=True,  # Explicitly verify TLS certificates
        )

    @staticmethod
    def _normalize_extract_filters_query(query: str) -> str:
        return query.strip()

    @classmethod
    def _prune_extract_filters_cache_locked(cls, now: float) -> None:
        expired_keys = [
            key for key, (expires_at, _) in cls._extract_filters_cache.items() if expires_at <= now
        ]
        for key in expired_keys:
            del cls._extract_filters_cache[key]

    @classmethod
    def _enforce_extract_filters_cache_size_locked(cls) -> None:
        while len(cls._extract_filters_cache) > cls._EXTRACT_FILTERS_CACHE_MAX_ENTRIES:
            cls._extract_filters_cache.popitem(last=False)

    @staticmethod
    def _serialize_extract_filters_cache_key(cache_key: _ExtractFiltersCacheKey) -> str:
        return json.dumps(cache_key, separators=(",", ":"))

    @classmethod
    def _prune_extract_filters_disk_entries_locked(
        cls,
        entries: OrderedDict[str, _ExtractFiltersDiskCacheEntry],
        *,
        now_wall: float,
    ) -> bool:
        changed = False
        expired_keys = [
            key for key, entry in entries.items() if entry["expires_at"] <= now_wall
        ]
        for key in expired_keys:
            del entries[key]
            changed = True

        if len(entries) <= cls._EXTRACT_FILTERS_CACHE_MAX_ENTRIES:
            return changed

        sortable = sorted(
            entries.items(),
            key=lambda item: item[1]["created_at"],
            reverse=True,
        )
        keep_keys = {
            key for key, _ in sortable[: cls._EXTRACT_FILTERS_CACHE_MAX_ENTRIES]
        }
        removable = [key for key in entries if key not in keep_keys]
        for key in removable:
            del entries[key]
            changed = True
        return changed

    @classmethod
    def _load_extract_filters_disk_entries_locked(
        cls,
        *,
        now_wall: float,
    ) -> tuple[OrderedDict[str, _ExtractFiltersDiskCacheEntry], bool]:
        try:
            with cls._EXTRACT_FILTERS_DISK_CACHE_FILE.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return OrderedDict(), False

        if not isinstance(payload, dict):
            return OrderedDict(), False
        if payload.get("version") != cls._EXTRACT_FILTERS_DISK_CACHE_VERSION:
            return OrderedDict(), False

        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, dict):
            return OrderedDict(), False

        parsed_entries: OrderedDict[str, _ExtractFiltersDiskCacheEntry] = OrderedDict()
        changed = False
        for key, raw_entry in raw_entries.items():
            if not isinstance(key, str) or not isinstance(raw_entry, dict):
                changed = True
                continue
            content = raw_entry.get("content")
            created_at = raw_entry.get("created_at")
            expires_at = raw_entry.get("expires_at")
            if not isinstance(content, str):
                changed = True
                continue
            if not isinstance(created_at, (int, float)):
                changed = True
                continue
            if not isinstance(expires_at, (int, float)):
                changed = True
                continue
            parsed_entries[key] = {
                "content": content,
                "created_at": float(created_at),
                "expires_at": float(expires_at),
            }

        changed = cls._prune_extract_filters_disk_entries_locked(
            parsed_entries,
            now_wall=now_wall,
        ) or changed
        return parsed_entries, changed

    @classmethod
    def _save_extract_filters_disk_entries_locked(
        cls,
        entries: OrderedDict[str, _ExtractFiltersDiskCacheEntry],
    ) -> None:
        try:
            cache_path = cls._EXTRACT_FILTERS_DISK_CACHE_FILE
            cache_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temp_path = cache_path.with_suffix(".tmp")
            payload = {
                "version": cls._EXTRACT_FILTERS_DISK_CACHE_VERSION,
                "entries": dict(entries),
            }
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            temp_path.replace(cache_path)
            cache_path.chmod(0o600)
        except OSError:
            return

    @classmethod
    def _get_extract_filters_from_disk_cache_locked(
        cls,
        cache_key: _ExtractFiltersCacheKey,
        *,
        now_wall: float,
    ) -> str | None:
        entries, changed = cls._load_extract_filters_disk_entries_locked(now_wall=now_wall)
        serialized_key = cls._serialize_extract_filters_cache_key(cache_key)
        entry = entries.get(serialized_key)
        if changed:
            cls._save_extract_filters_disk_entries_locked(entries)
        if entry is None:
            return None
        return entry["content"]

    @classmethod
    def _store_extract_filters_in_disk_cache_locked(
        cls,
        cache_key: _ExtractFiltersCacheKey,
        content: str,
        *,
        now_wall: float,
    ) -> None:
        entries, _ = cls._load_extract_filters_disk_entries_locked(now_wall=now_wall)
        serialized_key = cls._serialize_extract_filters_cache_key(cache_key)
        entries[serialized_key] = {
            "content": content,
            "created_at": now_wall,
            "expires_at": now_wall + cls._EXTRACT_FILTERS_CACHE_TTL_SECONDS,
        }
        cls._prune_extract_filters_disk_entries_locked(entries, now_wall=now_wall)
        cls._save_extract_filters_disk_entries_locked(entries)

    @classmethod
    def reset_extract_filters_cache(cls) -> None:
        """Clear process-local extract_filters cache and counters."""
        with cls._extract_filters_cache_lock:
            cls._extract_filters_cache.clear()
            cls._extract_filters_cache_hits = 0
            cls._extract_filters_cache_misses = 0

    @classmethod
    def extract_filters_cache_stats(cls) -> _ExtractFiltersCacheStats:
        """Return current process-local extract_filters cache stats."""
        with cls._extract_filters_cache_lock:
            cls._prune_extract_filters_cache_locked(monotonic())
            return {
                "size": len(cls._extract_filters_cache),
                "hits": cls._extract_filters_cache_hits,
                "misses": cls._extract_filters_cache_misses,
                "ttl_seconds": cls._EXTRACT_FILTERS_CACHE_TTL_SECONDS,
                "max_entries": cls._EXTRACT_FILTERS_CACHE_MAX_ENTRIES,
            }

    def extract_filters(self, query: str) -> str:
        """Send query to LLM and return raw response text."""
        cache_key: _ExtractFiltersCacheKey = (
            self.base_url,
            self.model,
            self._normalize_extract_filters_query(query),
        )
        cls = type(self)
        now = monotonic()
        with cls._extract_filters_cache_lock:
            cls._prune_extract_filters_cache_locked(now)
            cached = cls._extract_filters_cache.get(cache_key)
            if cached is not None:
                _, cached_content = cached
                cls._extract_filters_cache_hits += 1
                cls._extract_filters_cache.move_to_end(cache_key)
                return cached_content
            cls._extract_filters_cache_misses += 1
            disk_cached_content = cls._get_extract_filters_from_disk_cache_locked(
                cache_key,
                now_wall=time(),
            )
            if disk_cached_content is not None:
                cls._extract_filters_cache[cache_key] = (
                    monotonic() + cls._EXTRACT_FILTERS_CACHE_TTL_SECONDS,
                    disk_cached_content,
                )
                cls._enforce_extract_filters_cache_size_locked()
                return disk_cached_content

        response = self._http.post(
            "/chat/completions",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": query},
                ],
                "temperature": 0.0,
            },
        )
        response.raise_for_status()
        data = cast(object, response.json())
        content = self._extract_message_content(data)
        with cls._extract_filters_cache_lock:
            cls._extract_filters_cache[cache_key] = (
                monotonic() + cls._EXTRACT_FILTERS_CACHE_TTL_SECONDS,
                content,
            )
            cls._enforce_extract_filters_cache_size_locked()
            cls._store_extract_filters_in_disk_cache_locked(
                cache_key,
                content,
                now_wall=time(),
            )
        return content

    def rerank(self, query: str, file_list: list[str]) -> list[str]:
        """Send file list to LLM for semantic re-ranking. Returns ordered list."""
        file_text = "\n".join(file_list)
        prompt = (
            f"Given the query: \"{query}\"\n\n"
            f"Rank these files by relevance (most relevant first). "
            f"Return ONLY the file paths, one per line, no numbering:\n\n{file_text}"
        )
        response = self._http.post(
            "/chat/completions",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            },
        )
        response.raise_for_status()
        data = cast(object, response.json())
        content = self._extract_message_content(data)
        ranked = [line.strip() for line in content.splitlines() if line.strip()]
        # Only return paths that were in the original list
        valid = set(file_list)
        return [p for p in ranked if p in valid]

    @staticmethod
    def _extract_message_content(payload: object) -> str:
        if not isinstance(payload, dict):
            raise LLMResponseSchemaError("response is not an object")
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMResponseSchemaError("response.choices is missing or empty")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise LLMResponseSchemaError("response.choices[0] is invalid")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise LLMResponseSchemaError("response.choices[0].message is invalid")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseSchemaError("response.choices[0].message.content is empty")
        return content.strip()

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> LLMClient:
        """Support context manager protocol."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Ensure HTTP client is closed when exiting context."""
        self.close()
