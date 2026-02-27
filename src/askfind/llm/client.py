"""OpenAI-compatible LLM HTTP client."""

from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from time import monotonic
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


class LLMClient:
    """Client for OpenAI-compatible chat completion APIs."""

    _EXTRACT_FILTERS_CACHE_TTL_SECONDS: ClassVar[float] = 300.0
    _EXTRACT_FILTERS_CACHE_MAX_ENTRIES: ClassVar[int] = 256
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
        data = cast(_ChatResponse, response.json())
        content = data["choices"][0]["message"]["content"]
        with cls._extract_filters_cache_lock:
            cls._extract_filters_cache[cache_key] = (
                monotonic() + cls._EXTRACT_FILTERS_CACHE_TTL_SECONDS,
                content,
            )
            cls._enforce_extract_filters_cache_size_locked()
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
        data = cast(_ChatResponse, response.json())
        content = data["choices"][0]["message"]["content"].strip()
        ranked = [line.strip() for line in content.splitlines() if line.strip()]
        # Only return paths that were in the original list
        valid = set(file_list)
        return [p for p in ranked if p in valid]

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
