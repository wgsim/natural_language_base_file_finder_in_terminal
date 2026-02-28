"""Tests for search filter dataclass and matching logic."""


from datetime import datetime, timezone
import plistlib
from types import SimpleNamespace
from unittest.mock import patch

from askfind.search.filters import (
    MAX_CONTENT_SCAN_BYTES,
    SearchFilters,
    parse_mod_datetime,
    parse_size,
    parse_time_delta,
)


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


class TestParseModDatetime:
    def test_date_only_lower_and_upper_bound(self):
        lower = parse_mod_datetime("2026-01-10", upper_bound=False)
        upper = parse_mod_datetime("2026-01-10", upper_bound=True)
        assert lower == datetime(2026, 1, 10, 0, 0, tzinfo=timezone.utc)
        assert upper == datetime(2026, 1, 11, 0, 0, tzinfo=timezone.utc)

    def test_datetime_with_offset_is_normalized_to_utc(self):
        dt = parse_mod_datetime("2026-01-10T03:00:00+03:00")
        assert dt == datetime(2026, 1, 10, 0, 0, tzinfo=timezone.utc)


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

    def test_invalid_size_filter_is_ignored(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("content")
        stat = f.stat()
        filters = SearchFilters(size=">huge")
        assert filters.matches_stat(stat) is True

    def test_invalid_mod_filter_is_ignored(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("content")
        stat = f.stat()
        filters = SearchFilters(mod=">today")
        assert filters.matches_stat(stat) is True

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

    def test_has_content_matches_terms_across_chunk_boundaries(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("A" * 7 + "TODO" + "B" * 7 + "FIXME")
        filters = SearchFilters(has=["TODO", "FIXME"])
        with patch("askfind.search.filters.CONTENT_SCAN_CHUNK_BYTES", 8):
            assert filters.matches_content(f) is True

    def test_depth_filter(self):
        filters = SearchFilters(depth="<3")
        assert filters.matches_depth(2) is True
        assert filters.matches_depth(3) is False
        assert filters.matches_depth(5) is False

    def test_depth_filter_equal_default_operator(self):
        filters = SearchFilters(depth="3")
        assert filters.matches_depth(3) is True
        assert filters.matches_depth(2) is False

    def test_depth_filter_greater_than_operator(self):
        filters = SearchFilters(depth=">3")
        assert filters.matches_depth(4) is True
        assert filters.matches_depth(3) is False

    def test_invalid_regex_is_cleared(self):
        filters = SearchFilters(regex="[")
        assert filters.regex is None
        assert filters._compiled_regex is None
        assert filters.matches_name("anything.txt") is True

    def test_fuzzy_match_true_and_false_paths(self):
        filters = SearchFilters(fuzzy="abc")
        assert filters.matches_name("a___b___c.txt") is True
        assert filters.matches_name("acb.txt") is False

    def test_type_link_and_unknown_type_fallback(self):
        filters = SearchFilters(type="link")
        assert filters.matches_type(is_file=False, is_dir=False, is_link=True) is True
        assert filters.matches_type(is_file=True, is_dir=False, is_link=False) is False

        unknown = SearchFilters(type="unknown")
        assert unknown.matches_type(is_file=False, is_dir=False, is_link=False) is True

    def test_size_filter_less_than_branch(self):
        stat = SimpleNamespace(st_size=2048)
        assert SearchFilters(size="<3KB").matches_stat(stat) is True
        assert SearchFilters(size="<1KB").matches_stat(stat) is False

    def test_mod_filter_greater_and_less_than_old_new_behavior(self):
        fixed_now = datetime(2024, 1, 10, tzinfo=timezone.utc)
        older_stat = SimpleNamespace(
            st_mtime=datetime(2024, 1, 7, tzinfo=timezone.utc).timestamp()
        )
        newer_stat = SimpleNamespace(
            st_mtime=datetime(2024, 1, 9, 12, tzinfo=timezone.utc).timestamp()
        )

        with patch("askfind.search.filters.datetime") as mock_datetime:
            mock_datetime.now.return_value = fixed_now
            mock_datetime.fromtimestamp.side_effect = (
                lambda ts, tz: datetime.fromtimestamp(ts, tz=tz)
            )

            recent = SearchFilters(mod=">1d")
            assert recent.matches_stat(newer_stat) is True
            assert recent.matches_stat(older_stat) is False

            old = SearchFilters(mod="<1d")
            assert old.matches_stat(older_stat) is True
            assert old.matches_stat(newer_stat) is False

    def test_mod_after_and_mod_before_date_range(self):
        inside = SimpleNamespace(
            st_mtime=datetime(2026, 1, 12, 8, tzinfo=timezone.utc).timestamp()
        )
        before = SimpleNamespace(
            st_mtime=datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc).timestamp()
        )
        after = SimpleNamespace(
            st_mtime=datetime(2026, 1, 16, 0, 0, tzinfo=timezone.utc).timestamp()
        )

        filters = SearchFilters(mod_after="2026-01-01", mod_before="2026-01-15")
        assert filters.matches_stat(inside) is True
        assert filters.matches_stat(before) is False
        assert filters.matches_stat(after) is False

    def test_mod_before_is_inclusive_for_date_only_queries(self):
        end_of_day = SimpleNamespace(
            st_mtime=datetime(2026, 1, 15, 23, 59, 59, tzinfo=timezone.utc).timestamp()
        )
        next_day = SimpleNamespace(
            st_mtime=datetime(2026, 1, 16, 0, 0, tzinfo=timezone.utc).timestamp()
        )

        filters = SearchFilters(mod_before="2026-01-15")
        assert filters.matches_stat(end_of_day) is True
        assert filters.matches_stat(next_day) is False

    def test_perm_filter_r_w_x_pass_and_fail_paths(self):
        full_access = SimpleNamespace(st_mode=0o777)
        assert SearchFilters(perm="r").matches_stat(full_access) is True
        assert SearchFilters(perm="w").matches_stat(full_access) is True
        assert SearchFilters(perm="x").matches_stat(full_access) is True

        assert SearchFilters(perm="r").matches_stat(SimpleNamespace(st_mode=0o333)) is False
        assert SearchFilters(perm="w").matches_stat(SimpleNamespace(st_mode=0o555)) is False
        assert SearchFilters(perm="x").matches_stat(SimpleNamespace(st_mode=0o666)) is False

    def test_matches_content_without_has_returns_true(self, tmp_path):
        filters = SearchFilters(has=None)
        assert filters.matches_content(tmp_path / "missing.txt") is True

    def test_matches_content_returns_false_for_symlink(self, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("TODO")
        link = tmp_path / "target-link.txt"
        link.symlink_to(target)
        assert SearchFilters(has=["TODO"]).matches_content(link) is False

    def test_matches_content_returns_false_for_oversized_file(self, tmp_path):
        f = tmp_path / "large.txt"
        f.write_bytes(b"a" * (MAX_CONTENT_SCAN_BYTES + 1))
        assert SearchFilters(has=["a"]).matches_content(f) is False

    def test_matches_content_returns_false_on_os_error(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("TODO")
        filters = SearchFilters(has=["TODO"])
        with patch(
            "askfind.search.filters._file_contains_all_terms", side_effect=OSError
        ):
            assert filters.matches_content(f) is False

    def test_matches_tags_returns_true_when_all_requested_tags_exist(self, tmp_path):
        f = tmp_path / "note.txt"
        f.write_text("x")
        raw_tags = plistlib.dumps(["ProjectX\n6", "Urgent\n2"])
        filters = SearchFilters(tag=["projectx", "urgent"])
        with patch("askfind.search.filters.os.getxattr", return_value=raw_tags, create=True):
            assert filters.matches_tags(f) is True

    def test_matches_tags_returns_false_when_missing_tag(self, tmp_path):
        f = tmp_path / "note.txt"
        f.write_text("x")
        raw_tags = plistlib.dumps(["ProjectX\n6"])
        filters = SearchFilters(tag=["ProjectX", "Urgent"])
        with patch("askfind.search.filters.os.getxattr", return_value=raw_tags, create=True):
            assert filters.matches_tags(f) is False

    def test_matches_tags_returns_false_when_xattr_missing(self, tmp_path):
        f = tmp_path / "note.txt"
        f.write_text("x")
        filters = SearchFilters(tag=["ProjectX"])
        with patch("askfind.search.filters.os.getxattr", side_effect=OSError, create=True):
            assert filters.matches_tags(f) is False
