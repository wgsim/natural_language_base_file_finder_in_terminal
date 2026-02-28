"""Tests for LLM response parsing."""

import json
from unittest.mock import patch

from askfind.llm.parser import (
    _extract_json,
    _validate_and_sanitize_value,
    parse_llm_response,
)
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

    def test_invalid_json_object_returns_empty_filters(self):
        raw = '{"ext": [".py",}'
        filters = parse_llm_response(raw)
        assert filters == SearchFilters()

    def test_non_object_json_returns_empty_filters(self):
        raw = '["not", "an", "object"]'
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

    def test_tag_as_single_string_converted_to_list(self):
        raw = '{"tag": "ProjectX"}'
        filters = parse_llm_response(raw)
        assert filters.tag == ["ProjectX"]

    def test_tag_as_list(self):
        raw = '{"tag": ["ProjectX", "Urgent"]}'
        filters = parse_llm_response(raw)
        assert filters.tag == ["ProjectX", "Urgent"]

    def test_lang_as_single_string_converted_to_list(self):
        raw = '{"lang": "python"}'
        filters = parse_llm_response(raw)
        assert filters.lang == ["python"]

    def test_license_as_single_string_converted_to_list(self):
        raw = '{"license": "mit"}'
        filters = parse_llm_response(raw)
        assert filters.license == ["mit"]

    def test_similar_as_string(self):
        raw = '{"similar": "auth.py"}'
        filters = parse_llm_response(raw)
        assert filters.similar == "auth.py"

    def test_loc_and_complexity_constraints(self):
        raw = '{"loc": ">200", "complexity": "<15"}'
        filters = parse_llm_response(raw)
        assert filters.loc == ">200"
        assert filters.complexity == "<15"

    def test_ext_as_single_string_converted_to_list(self):
        raw = '{"ext": ".py"}'
        filters = parse_llm_response(raw)
        assert filters.ext == [".py"]

    def test_rejects_non_list_ext_type(self):
        raw = '{"ext": 42}'
        filters = parse_llm_response(raw)
        assert filters.ext is None

    def test_rejects_empty_list_terms_after_normalization(self):
        raw = '{"has": ["", "   "]}'
        filters = parse_llm_response(raw)
        assert filters.has is None

    def test_multiple_filters_combined(self):
        """Should handle multiple filters in one query."""
        raw = '{"ext": [".py", ".js"], "type": "file", "depth": "<3"}'
        filters = parse_llm_response(raw)
        assert filters.ext == [".py", ".js"]
        assert filters.type == "file"
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

    def test_rejects_parent_only_path_values(self):
        raw = '{"path": "..", "not_path": "src/.."}'
        filters = parse_llm_response(raw)
        assert filters.path is None
        assert filters.not_path is None

    def test_rejects_home_expansion_path_values(self):
        raw = '{"path": "~/.ssh"}'
        filters = parse_llm_response(raw)
        assert filters.path is None

    def test_rejects_non_string_path_values(self):
        raw = '{"path": 123}'
        filters = parse_llm_response(raw)
        assert filters.path is None

    def test_handles_path_constructor_exceptions(self):
        with patch("askfind.llm.parser.Path", side_effect=ValueError("bad path")):
            raw = '{"path": "src"}'
            filters = parse_llm_response(raw)
            assert filters.path is None

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

    def test_rejects_invalid_type_values(self):
        raw = '{"type": "f"}'
        filters = parse_llm_response(raw)
        assert filters.type is None

    def test_rejects_non_string_name_fields(self):
        raw = '{"name": 1, "not_name": 2, "regex": 3, "fuzzy": 4, "similar": 5}'
        filters = parse_llm_response(raw)
        assert filters.name is None
        assert filters.not_name is None
        assert filters.regex is None
        assert filters.fuzzy is None
        assert filters.similar is None

    def test_rejects_non_string_type_perm_depth_size_mod(self):
        raw = '{"type": 1, "perm": 2, "depth": 3, "size": 4, "mod": 5, "mod_after": 6, "mod_before": 7}'
        filters = parse_llm_response(raw)
        assert filters.type is None
        assert filters.perm is None
        assert filters.depth is None
        assert filters.size is None
        assert filters.mod is None
        assert filters.mod_after is None
        assert filters.mod_before is None

    def test_rejects_non_list_lang_and_license_types(self):
        raw = '{"lang": 1, "not_lang": 2, "license": 3, "not_license": 4}'
        filters = parse_llm_response(raw)
        assert filters.lang is None
        assert filters.not_lang is None
        assert filters.license is None
        assert filters.not_license is None

    def test_rejects_invalid_loc_and_complexity_constraints(self):
        raw = '{"loc": "many", "complexity": ">"}'
        filters = parse_llm_response(raw)
        assert filters.loc is None
        assert filters.complexity is None

    def test_accepts_valid_path_size_and_metric_constraints(self):
        raw = '{"path": "src/utils", "size": ">10KB", "loc": "10", "complexity": "<3"}'
        filters = parse_llm_response(raw)
        assert filters.path == "src/utils"
        assert filters.size == ">10KB"
        assert filters.loc == "10"
        assert filters.complexity == "<3"

    def test_rejects_out_of_range_metric_and_absolute_year_values(self):
        raw = '{"loc": "1000001", "mod_after": "1969-12-31", "mod_before": "3000-01-01"}'
        filters = parse_llm_response(raw)
        assert filters.loc is None
        assert filters.mod_after is None
        assert filters.mod_before is None

    def test_rejects_non_string_loc_and_complexity(self):
        raw = '{"loc": 10, "complexity": 3}'
        filters = parse_llm_response(raw)
        assert filters.loc is None
        assert filters.complexity is None

    def test_rejects_invalid_permission_values(self):
        raw = '{"perm": "rwa"}'
        filters = parse_llm_response(raw)
        assert filters.perm is None

    def test_normalizes_permission_values(self):
        raw = '{"perm": "xwr"}'
        filters = parse_llm_response(raw)
        assert filters.perm == "rwx"

    def test_rejects_invalid_depth_constraint(self):
        raw = '{"depth": ">>3"}'
        filters = parse_llm_response(raw)
        assert filters.depth is None

    def test_rejects_empty_depth_constraint(self):
        raw = '{"depth": "<"}'
        filters = parse_llm_response(raw)
        assert filters.depth is None

    def test_rejects_out_of_range_depth_constraint(self):
        raw = '{"depth": "4096"}'
        filters = parse_llm_response(raw)
        assert filters.depth is None

    def test_rejects_invalid_size_constraint(self):
        raw = '{"size": "many"}'
        filters = parse_llm_response(raw)
        assert filters.size is None

    def test_rejects_empty_size_constraint(self):
        raw = '{"size": ">"}'
        filters = parse_llm_response(raw)
        assert filters.size is None

    def test_rejects_negative_and_too_large_size_constraint(self):
        raw = '{"size": "-1", "mod": ">1d"}'
        filters = parse_llm_response(raw)
        assert filters.size is None
        raw2 = '{"size": "2000000TB"}'
        filters2 = parse_llm_response(raw2)
        assert filters2.size is None

    def test_rejects_invalid_mod_constraint(self):
        raw = '{"mod": ">0d"}'
        filters = parse_llm_response(raw)
        assert filters.mod is None

    def test_accepts_absolute_mod_date_range(self):
        raw = '{"mod_after": "2026-01-01", "mod_before": "2026-01-15"}'
        filters = parse_llm_response(raw)
        assert filters.mod_after == "2026-01-01"
        assert filters.mod_before == "2026-01-15"

    def test_accepts_absolute_mod_datetime_and_normalizes_timezone(self):
        raw = '{"mod_after": "2026-01-01T03:00:00+03:00"}'
        filters = parse_llm_response(raw)
        assert filters.mod_after == "2026-01-01T00:00:00+00:00"

    def test_rejects_invalid_absolute_mod_values(self):
        raw = '{"mod_after": "2026-13-40", "mod_before": ""}'
        filters = parse_llm_response(raw)
        assert filters.mod_after is None
        assert filters.mod_before is None

    def test_rejects_empty_and_unparseable_mod_constraint(self):
        raw = '{"mod": ">"}'
        filters = parse_llm_response(raw)
        assert filters.mod is None
        raw2 = '{"mod": "abc"}'
        filters2 = parse_llm_response(raw2)
        assert filters2.mod is None

    def test_extracts_balanced_json_with_nested_braces(self):
        raw = 'prefix {"name": "literal { brace }", "ext": [".py"]} suffix'
        filters = parse_llm_response(raw)
        assert filters.name == "literal { brace }"
        assert filters.ext == [".py"]

    def test_extract_json_handles_escaped_quotes(self):
        raw = 'prefix {"name":"a\\\\\\"b","ext":[".py"]} suffix'
        filters = parse_llm_response(raw)
        assert filters.ext == [".py"]

    def test_extract_json_returns_none_for_unbalanced_braces(self):
        raw = 'prefix {"ext": [".py"]'
        filters = parse_llm_response(raw)
        assert filters == SearchFilters()

    def test_markdown_json_array_hits_non_object_branch(self):
        raw = "```json\n[1, 2, 3]\n```"
        assert parse_llm_response(raw) == SearchFilters()

    def test_unknown_key_type_branch_returns_none(self):
        assert _validate_and_sanitize_value("unknown_key", "value") is None

    def test_extract_json_returns_none_without_object(self):
        assert _extract_json("there is no json here") is None
