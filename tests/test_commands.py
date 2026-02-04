"""Tests for interactive commands."""

from unittest.mock import patch

from askfind.interactive.commands import copy_content
from askfind.output.formatter import FileResult


def test_copy_content_handles_decode_error(tmp_path):
    f = tmp_path / "bin.dat"
    f.write_bytes(b"\xff\xfe\xfd")
    result = FileResult.from_path(f)
    with patch("askfind.interactive.commands._copy_to_clipboard") as mocked:
        copy_content(result)
        mocked.assert_called_once()
