"""Tests for LLM response parsing."""

import json

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

    def test_multiple_filters_combined(self):
        """Should handle multiple filters in one query."""
        raw = '{"ext": [".py", ".js"], "type": "f", "depth": "<3"}'
        filters = parse_llm_response(raw)
        assert filters.ext == [".py", ".js"]
        assert filters.type == "f"
        assert filters.depth == "<3"

    def test_rejects_absolute_path_values(self):
        raw = '{"path": "/etc", "not_path": "/var/log"}'
        filters = parse_llm_response(raw)
        assert filters.path is None
        assert filters.not_path is None

    def test_rejects_parent_traversal_path_values(self):
        raw = '{"path": "../secrets", "not_path": "src/../private"}'
        filters = parse_llm_response(raw)
        assert filters.path is None
        assert filters.not_path is None

    def test_truncates_list_fields_to_max_length(self):
        ext_list = [f".ext{i}" for i in range(30)]
        raw = json.dumps({"ext": ext_list})
        filters = parse_llm_response(raw)
        assert filters.ext is not None
        assert len(filters.ext) == 20

    def test_truncates_long_string_terms(self):
        long_term = "x" * 500
        raw = json.dumps({"has": [long_term], "name": long_term})
        filters = parse_llm_response(raw)
        assert filters.has == ["x" * 200]
        assert filters.name == "x" * 200

    def test_extracts_balanced_json_with_nested_braces(self):
        raw = 'prefix {"name": "literal { brace }", "ext": [".py"]} suffix'
        filters = parse_llm_response(raw)
        assert filters.name == "literal { brace }"
        assert filters.ext == [".py"]
