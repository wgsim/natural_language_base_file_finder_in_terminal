"""Tests for interactive commands."""

from unittest.mock import patch

from askfind.interactive.commands import copy_content
from askfind.output.formatter import FileResult


class TestCopyContent:
    @patch("askfind.interactive.commands._copy_to_clipboard")
    def test_copy_content_handles_non_utf8_file(self, mock_clipboard, tmp_path):
        file_path = tmp_path / "binary.txt"
        file_path.write_bytes(b"\xff\xfehello")
        result = FileResult.from_path(file_path)

        copy_content(result)

        mock_clipboard.assert_called_once()
        copied_text = mock_clipboard.call_args.args[0]
        assert "hello" in copied_text

    @patch("askfind.interactive.commands._copy_to_clipboard")
    def test_copy_content_skips_symlink(self, mock_clipboard, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("secret")
        symlink = tmp_path / "target-link.txt"
        symlink.symlink_to(target)
        result = FileResult.from_path(symlink)

        copy_content(result)

        mock_clipboard.assert_not_called()
