"""Tests for LLM mode decision policy."""

from askfind.llm.mode import decide_llm_usage, normalize_llm_mode
from askfind.search.filters import SearchFilters


def test_normalize_llm_mode_accepts_valid_values():
    assert normalize_llm_mode("always") == "always"
    assert normalize_llm_mode("auto") == "auto"
    assert normalize_llm_mode("off") == "off"


def test_normalize_llm_mode_rejects_invalid_values():
    assert normalize_llm_mode("smart") == "always"
    assert normalize_llm_mode(123) == "always"


def test_decide_llm_usage_forced_modes():
    fallback_filters = SearchFilters(ext=[".py"], type="file")

    always = decide_llm_usage(query="python files", fallback_filters=fallback_filters, llm_mode="always")
    assert always.llm_called is True
    assert always.reason == "forced_always"

    off = decide_llm_usage(query="python files", fallback_filters=fallback_filters, llm_mode="off")
    assert off.llm_called is False
    assert off.reason == "forced_off"


def test_decide_llm_usage_auto_uses_fallback_for_simple_query():
    decision = decide_llm_usage(
        query="python files in src",
        fallback_filters=SearchFilters(ext=[".py"], path="src", type="file"),
        llm_mode="auto",
    )

    assert decision.llm_called is False
    assert decision.reason == "auto_simple_fallback"


def test_decide_llm_usage_auto_uses_llm_for_empty_fallback():
    decision = decide_llm_usage(
        query="find files",
        fallback_filters=SearchFilters(),
        llm_mode="auto",
    )

    assert decision.llm_called is True
    assert decision.reason == "auto_empty_fallback"


def test_decide_llm_usage_auto_uses_llm_for_ambiguous_query():
    decision = decide_llm_usage(
        query="files related to authentication",
        fallback_filters=SearchFilters(ext=[".py"], type="file"),
        llm_mode="auto",
    )

    assert decision.llm_called is True
    assert decision.reason == "auto_ambiguous_terms"

