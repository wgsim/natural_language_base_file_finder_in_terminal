"""Tests for heuristic fallback query parsing."""

from askfind.llm.fallback import has_meaningful_filters, parse_query_fallback
from askfind.search.filters import SearchFilters


def test_parse_query_fallback_infers_ext_path_and_has_markers():
    filters = parse_query_fallback("python files in src containing TODO or FIXME")

    assert filters.ext == [".py"]
    assert filters.path == "src"
    assert filters.has == ["TODO", "FIXME"]
    assert filters.type == "file"


def test_parse_query_fallback_returns_empty_for_unspecific_query():
    filters = parse_query_fallback("find files")
    assert filters == SearchFilters()
    assert has_meaningful_filters(filters) is False


def test_parse_query_fallback_respects_quoted_content_terms():
    filters = parse_query_fallback('markdown files containing "release checklist"')

    assert filters.ext == [".md"]
    assert filters.has == ["release checklist"]


def test_parse_query_fallback_infers_size_mod_and_not_path():
    filters = parse_query_fallback("python files larger than 10MB in last 7 days excluding tests")

    assert filters.ext == [".py"]
    assert filters.size == ">10MB"
    assert filters.mod == ">7d"
    assert filters.not_path == "tests"


def test_parse_query_fallback_avoids_path_false_positive_for_size_and_time_phrases():
    filters = parse_query_fallback("find files under 10MB in the last 7 days")

    assert filters.path is None
    assert filters.size == "<10MB"
    assert filters.mod == ">7d"


def test_parse_query_fallback_handles_optional_determiner_in_path_clause():
    filters = parse_query_fallback("python files in the src containing TODO")

    assert filters.ext == [".py"]
    assert filters.path == "src"
    assert filters.has == ["TODO"]


def test_parse_query_fallback_preserves_quoted_has_phrase_with_in():
    filters = parse_query_fallback('files containing "error in auth"')

    assert filters.has == ["error in auth"]
