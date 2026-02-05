"""Tests for LLM response parsing."""

from askfind.llm.parser import parse_llm_response
from askfind.search.filters import SearchFilters


class TestParseLlmResponse:
    def test_simple_ext_filter(self):
        raw = '{"ext": [".py"]}'
        filters = parse_llm_response(raw)
        assert isinstance(filters, SearchFilters)
        assert filters.ext == [".py"]

    def test_multiple_filters(self):
        raw = '{"ext": [".py"], "name": "*test*", "mod": ">7d"}'
        filters = parse_llm_response(raw)
        assert filters.ext == [".py"]
        assert filters.name == "*test*"
        assert filters.mod == ">7d"

    def test_empty_json(self):
        raw = "{}"
        filters = parse_llm_response(raw)
        assert filters.ext is None
        assert filters.name is None

    def test_ignores_unknown_keys(self):
        raw = '{"ext": [".py"], "unknown_key": "value"}'
        filters = parse_llm_response(raw)
        assert filters.ext == [".py"]

    def test_handles_markdown_wrapped_json(self):
        raw = '```json\n{"ext": [".py"]}\n```'
        filters = parse_llm_response(raw)
        assert filters.ext == [".py"]

    def test_handles_plain_text_wrapped_json(self):
        raw = 'Here are the filters:\n{"ext": [".py"]}\nLet me know if you need more.'
        filters = parse_llm_response(raw)
        assert filters.ext == [".py"]

    def test_invalid_json_returns_empty_filters(self):
        raw = "not json at all"
        filters = parse_llm_response(raw)
        assert filters == SearchFilters()

    def test_has_as_single_string_converted_to_list(self):
        raw = '{"has": "TODO"}'
        filters = parse_llm_response(raw)
        assert filters.has == ["TODO"]

    def test_has_as_list(self):
        raw = '{"has": ["TODO", "FIXME"]}'
        filters = parse_llm_response(raw)
        assert filters.has == ["TODO", "FIXME"]

    def test_ext_as_single_string_converted_to_list(self):
        raw = '{"ext": ".py"}'
        filters = parse_llm_response(raw)
        assert filters.ext == [".py"]

    def test_parse_llm_response_with_errors(self):
        raw = "not json"
        filters, errors = parse_llm_response(raw, return_errors=True)
        assert isinstance(filters, SearchFilters)
        assert errors
