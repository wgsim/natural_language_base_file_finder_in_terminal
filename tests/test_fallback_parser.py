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
