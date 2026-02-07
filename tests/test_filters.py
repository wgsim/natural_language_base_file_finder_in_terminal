"""Tests for search filter dataclass and matching logic."""

import os
import time
from pathlib import Path

from askfind.search.filters import SearchFilters, parse_size, parse_time_delta


class TestParseSize:
    def test_bytes(self):
        assert parse_size("100") == 100

    def test_kilobytes(self):
        assert parse_size("1KB") == 1024

    def test_megabytes(self):
        assert parse_size("5MB") == 5 * 1024 * 1024

    def test_gigabytes(self):
        assert parse_size("2GB") == 2 * 1024 * 1024 * 1024

    def test_case_insensitive(self):
        assert parse_size("1kb") == 1024

    def test_decimal_bytes(self):
        assert parse_size("1.5") == 1

    def test_decimal_with_unit(self):
        assert parse_size("1.5MB") == int(1.5 * 1024 * 1024)


class TestParseTimeDelta:
    def test_days(self):
        delta = parse_time_delta("7d")
        assert delta.days == 7

    def test_hours(self):
        delta = parse_time_delta("24h")
        assert delta.total_seconds() == 86400

    def test_minutes(self):
        delta = parse_time_delta("30m")
        assert delta.total_seconds() == 1800

    def test_weeks(self):
        delta = parse_time_delta("2w")
        assert delta.days == 14


class TestSearchFilters:
    def test_empty_filters_match_everything(self, tmp_path):
        f = tmp_path / "hello.py"
        f.write_text("content")
        filters = SearchFilters()
        assert filters.matches_name(f.name) is True
        assert filters.matches_path(str(f)) is True

    def test_ext_filter(self):
        filters = SearchFilters(ext=[".py"])
        assert filters.matches_name("test.py") is True
        assert filters.matches_name("test.js") is False

    def test_not_ext_filter(self):
        filters = SearchFilters(not_ext=[".pyc"])
        assert filters.matches_name("test.py") is True
        assert filters.matches_name("test.pyc") is False

    def test_name_glob(self):
        filters = SearchFilters(name="*test*")
        assert filters.matches_name("test_auth.py") is True
        assert filters.matches_name("auth.py") is False

    def test_not_name_glob(self):
        filters = SearchFilters(not_name="*cache*")
        assert filters.matches_name("file_cache.py") is False
        assert filters.matches_name("file_auth.py") is True

    def test_path_contains(self):
        filters = SearchFilters(path="src")
        assert filters.matches_path("src/auth/login.py") is True
        assert filters.matches_path("vendor/lib.py") is False

    def test_not_path_contains(self):
        filters = SearchFilters(not_path="vendor")
        assert filters.matches_path("vendor/lib.py") is False
        assert filters.matches_path("src/auth.py") is True

    def test_regex_filter(self):
        filters = SearchFilters(regex=r"test_.*\.py$")
        assert filters.matches_name("test_auth.py") is True
        assert filters.matches_name("auth_test.py") is False

    def test_size_filter(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text("x" * 2000)
        stat = f.stat()
        filters = SearchFilters(size=">1KB")
        assert filters.matches_stat(stat) is True
        filters2 = SearchFilters(size=">1MB")
        assert filters2.matches_stat(stat) is False

    def test_type_file(self):
        filters = SearchFilters(type="file")
        assert filters.matches_type(is_file=True, is_dir=False, is_link=False) is True
        assert filters.matches_type(is_file=False, is_dir=True, is_link=False) is False

    def test_type_dir(self):
        filters = SearchFilters(type="dir")
        assert filters.matches_type(is_file=False, is_dir=True, is_link=False) is True

    def test_has_content(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("# TODO: fix this\nimport os\n")
        filters = SearchFilters(has=["TODO"])
        assert filters.matches_content(f) is True
        filters2 = SearchFilters(has=["FIXME"])
        assert filters2.matches_content(f) is False

    def test_has_multiple_terms(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("# TODO: fix this\n# FIXME: later\n")
        filters = SearchFilters(has=["TODO", "FIXME"])
        assert filters.matches_content(f) is True

    def test_depth_filter(self):
        filters = SearchFilters(depth="<3")
        assert filters.matches_depth(2) is True
        assert filters.matches_depth(3) is False
        assert filters.matches_depth(5) is False
