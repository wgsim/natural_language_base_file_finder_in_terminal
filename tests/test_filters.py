"""Tests for search filter dataclass and matching logic."""


from datetime import datetime, timezone
import plistlib
from types import SimpleNamespace
from unittest.mock import patch

import askfind.search.filters as filters_module
import pytest
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

    def test_matches_language_detects_from_extension(self, tmp_path):
        py_file = tmp_path / "app.py"
        py_file.write_text("print('ok')\n")
        assert SearchFilters(lang=["python"]).matches_language(py_file) is True
        assert SearchFilters(lang=["javascript"]).matches_language(py_file) is False

    def test_matches_language_detects_from_shebang(self, tmp_path):
        script = tmp_path / "run"
        script.write_text("#!/usr/bin/env python\nprint('ok')\n")
        assert SearchFilters(lang=["python"]).matches_language(script) is True

    def test_matches_language_supports_not_lang(self, tmp_path):
        py_file = tmp_path / "app.py"
        py_file.write_text("print('ok')\n")
        assert SearchFilters(not_lang=["python"]).matches_language(py_file) is False
        assert SearchFilters(not_lang=["javascript"]).matches_language(py_file) is True

    def test_matches_license_detects_from_spdx_header(self, tmp_path):
        file_path = tmp_path / "main.py"
        file_path.write_text("# SPDX-License-Identifier: MIT\nprint('ok')\n")
        assert SearchFilters(license=["mit"]).matches_license(file_path) is True
        assert SearchFilters(license=["apache-2.0"]).matches_license(file_path) is False

    def test_matches_license_supports_not_license(self, tmp_path):
        file_path = tmp_path / "main.py"
        file_path.write_text("# SPDX-License-Identifier: Apache-2.0\nprint('ok')\n")
        assert SearchFilters(not_license=["apache-2.0"]).matches_license(file_path) is False
        assert SearchFilters(not_license=["mit"]).matches_license(file_path) is True

    def test_parse_mod_datetime_handles_z_suffix_and_space_separator(self):
        zulu = parse_mod_datetime("2026-01-01T01:00:00Z")
        spaced = parse_mod_datetime("2026-01-01 01:00:00+00:00")
        assert zulu == datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)
        assert spaced == datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)

    def test_decode_macos_tags_handles_invalid_and_non_list_payloads(self):
        assert filters_module._decode_macos_tags(b"not-plist") == set()
        assert filters_module._decode_macos_tags(plistlib.dumps({"k": "v"})) == set()
        assert filters_module._decode_macos_tags(plistlib.dumps([1, "Tag\n6"])) == {"tag"}

    def test_read_user_tags_xattr_rejects_non_bytes_payload(self, tmp_path):
        f = tmp_path / "note.txt"
        f.write_text("x")
        with patch("askfind.search.filters.os.getxattr", return_value="oops", create=True):
            assert filters_module._read_user_tags_xattr(f, follow_symlinks=True) == set()

    def test_normalize_language_and_license_empty_values(self):
        assert filters_module._normalize_language_name("   ") == ""
        assert filters_module._normalize_license_name("   ") == ""

    def test_detect_language_from_various_shebangs(self, tmp_path):
        node_script = tmp_path / "node_script"
        node_script.write_text("#!/usr/bin/env node\n")
        ruby_script = tmp_path / "ruby_script"
        ruby_script.write_text("#!/usr/bin/env ruby\n")
        perl_script = tmp_path / "perl_script"
        perl_script.write_text("#!/usr/bin/env perl\n")
        php_script = tmp_path / "php_script"
        php_script.write_text("#!/usr/bin/env php\n")
        plain_text = tmp_path / "plain_text"
        plain_text.write_text("not shebang")
        empty_file = tmp_path / "empty"
        empty_file.write_text("")

        assert filters_module._detect_language_from_shebang(node_script) == "javascript"
        assert filters_module._detect_language_from_shebang(ruby_script) == "ruby"
        assert filters_module._detect_language_from_shebang(perl_script) == "perl"
        assert filters_module._detect_language_from_shebang(php_script) == "php"
        assert filters_module._detect_language_from_shebang(plain_text) is None
        assert filters_module._detect_language_from_shebang(empty_file) is None

    def test_read_text_sample_handles_oserror_and_empty_file(self, tmp_path):
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")
        assert filters_module._read_text_sample(empty_file, max_bytes=128) is None
        with patch("pathlib.Path.open", side_effect=OSError):
            assert filters_module._read_text_sample(empty_file, max_bytes=128) is None

    def test_detect_license_heuristics_cover_common_branches(self, tmp_path):
        samples = {
            "mit.txt": "Permission is hereby granted, free of charge, to any person obtaining a copy.",
            "apache.txt": "Apache License\nVersion 2.0, January 2004",
            "gpl3.txt": "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007",
            "gpl2.txt": "GNU GENERAL PUBLIC LICENSE\nVersion 2, June 1991",
            "mpl.txt": "Mozilla Public License Version 2.0",
            "unlicense.txt": "This is free and unencumbered software released into the public domain.\nThe Unlicense",
            "isc.txt": "Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted.",
            "bsd3.txt": "Redistribution and use in source and binary forms...\nNeither the name of the project nor contributors may be used.",
            "bsd2.txt": "Redistribution and use in source and binary forms...",
        }
        expected = {
            "mit.txt": "mit",
            "apache.txt": "apache-2.0",
            "gpl3.txt": "gpl-3.0",
            "gpl2.txt": "gpl-2.0",
            "mpl.txt": "mpl-2.0",
            "unlicense.txt": "unlicense",
            "isc.txt": "isc",
            "bsd3.txt": "bsd-3-clause",
            "bsd2.txt": "bsd-2-clause",
        }
        for filename, content in samples.items():
            path = tmp_path / filename
            path.write_text(content)
            assert filters_module._detect_license(path) == expected[filename]

    def test_matches_stat_invalid_absolute_date_filters_are_ignored(self):
        stat = SimpleNamespace(st_mtime=datetime(2026, 1, 12, tzinfo=timezone.utc).timestamp())
        filters = SearchFilters(mod_after="bad-date", mod_before="bad-date")
        assert filters.matches_stat(stat) is True

    def test_matches_tags_empty_requested_values_short_circuit_true(self, tmp_path):
        f = tmp_path / "note.txt"
        f.write_text("x")
        assert SearchFilters(tag=["", "   "]).matches_tags(f) is True

    def test_matches_language_and_license_symlink_branches(self, tmp_path):
        target = tmp_path / "target.py"
        target.write_text("# SPDX-License-Identifier: MIT\nprint('ok')\n")
        link = tmp_path / "link.py"
        try:
            link.symlink_to(target)
        except (NotImplementedError, OSError):
            pytest.skip("Symlinks are not supported in this test environment")

        assert SearchFilters(lang=["python"]).matches_language(link) is False
        assert SearchFilters(not_lang=["python"]).matches_language(link) is True
        assert SearchFilters(license=["mit"]).matches_license(link) is False
        assert SearchFilters(not_license=["mit"]).matches_license(link) is True
