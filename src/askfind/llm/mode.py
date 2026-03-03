"""Decision policy for when to call the LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from askfind.llm.fallback import has_meaningful_filters
from askfind.search.filters import SearchFilters

LLMMode = Literal["always", "auto", "off"]
LLMDecision = Literal["llm", "fallback"]

DEFAULT_LLM_MODE: LLMMode = "always"
VALID_LLM_MODES: tuple[LLMMode, LLMMode, LLMMode] = ("always", "auto", "off")

_AMBIGUOUS_QUERY_PATTERNS = (
    re.compile(r"\brelated to\b", re.IGNORECASE),
    re.compile(r"\brelevant to\b", re.IGNORECASE),
    re.compile(r"\bsimilar to\b", re.IGNORECASE),
    re.compile(r"\babout\b", re.IGNORECASE),
    re.compile(r"\bimportant\b", re.IGNORECASE),
    re.compile(r"\bwhat(?:'s| is)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class QueryLLMDecision:
    mode: LLMMode
    decision: LLMDecision
    reason: str

    @property
    def llm_called(self) -> bool:
        return self.decision == "llm"


def normalize_llm_mode(value: object, *, default: LLMMode = DEFAULT_LLM_MODE) -> LLMMode:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALID_LLM_MODES:
            return normalized  # type: ignore[return-value]
    return default


def decide_llm_usage(
    *,
    query: str,
    fallback_filters: SearchFilters,
    llm_mode: LLMMode,
) -> QueryLLMDecision:
    if llm_mode == "always":
        return QueryLLMDecision(mode=llm_mode, decision="llm", reason="forced_always")

    if llm_mode == "off":
        return QueryLLMDecision(mode=llm_mode, decision="fallback", reason="forced_off")

    if not has_meaningful_filters(fallback_filters):
        return QueryLLMDecision(mode=llm_mode, decision="llm", reason="auto_empty_fallback")

    lowered_query = query.strip().lower()
    for pattern in _AMBIGUOUS_QUERY_PATTERNS:
        if pattern.search(lowered_query):
            return QueryLLMDecision(mode=llm_mode, decision="llm", reason="auto_ambiguous_terms")

    return QueryLLMDecision(mode=llm_mode, decision="fallback", reason="auto_simple_fallback")

