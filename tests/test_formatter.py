"""Tests for output formatting."""

import json
from pathlib import Path

from askfind.output.formatter import format_plain, format_verbose, format_json, FileResult


class TestFileResult:
    def test_from_path(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("hello\nworld\n")
        result = FileResult.from_path(f)
        assert result.path == f
        assert result.size > 0
        assert result.modified is not None


class TestFormatPlain:
    def test_single_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("content")
        results = [FileResult.from_path(f)]
        output = format_plain(results)
        assert str(f) in output

    def test_multiple_files(self, tmp_path):
        files = []
        for name in ["a.py", "b.py", "c.py"]:
            f = tmp_path / name
            f.write_text("x")
            files.append(FileResult.from_path(f))
        output = format_plain(files)
        lines = output.strip().splitlines()
        assert len(lines) == 3

    def test_empty_results(self):
        output = format_plain([])
        assert output == ""


class TestFormatJson:
    def test_valid_json(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("content")
        results = [FileResult.from_path(f)]
        output = format_json(results)
        data = json.loads(output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert "path" in data[0]
        assert "size" in data[0]
        assert "modified" in data[0]


class TestFormatVerbose:
    def test_includes_metadata(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("content")
        results = [FileResult.from_path(f)]
        output = format_verbose(results)
        assert "test.py" in output
