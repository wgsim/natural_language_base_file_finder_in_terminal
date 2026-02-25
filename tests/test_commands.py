"""Tests for interactive commands."""

import subprocess
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import call, patch

from askfind.interactive.commands import (
    MAX_CLIPBOARD_SIZE,
    MAX_PREVIEW_SIZE,
    _copy_to_clipboard,
    copy_content,
    copy_path,
    open_in_editor,
    preview,
)
from askfind.output.formatter import FileResult
from rich.syntax import Syntax


class TestCopyPath:
    @patch("askfind.interactive.commands.console.print")
    @patch("askfind.interactive.commands._copy_to_clipboard")
    def test_copy_path_copies_and_prints_success(self, mock_clipboard, mock_print, tmp_path):
        file_path = tmp_path / "example.txt"
        file_path.write_text("hello")
        result = FileResult.from_path(file_path)

        copy_path(result)

        mock_clipboard.assert_called_once_with(str(file_path))
        mock_print.assert_called_once_with(f"[green]Copied: {file_path}[/green]")


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

    @patch("askfind.interactive.commands.console.print")
    @patch("askfind.interactive.commands._copy_to_clipboard")
    def test_copy_content_rejects_large_files(self, mock_clipboard, mock_print, tmp_path):
        file_path = tmp_path / "large.txt"
        file_path.write_text("x")
        result = FileResult.from_path(file_path)

        with patch.object(type(result.path), "stat", return_value=SimpleNamespace(st_size=MAX_CLIPBOARD_SIZE + 1)):
            copy_content(result)

        mock_clipboard.assert_not_called()
        mock_print.assert_called_once()
        assert "File too large" in mock_print.call_args.args[0]

    @patch("askfind.interactive.commands.console.print")
    @patch("askfind.interactive.commands._copy_to_clipboard")
    def test_copy_content_handles_oserror(self, mock_clipboard, mock_print, tmp_path):
        missing = tmp_path / "missing.txt"
        result = FileResult(path=missing, size=0, modified=datetime.now(timezone.utc))

        copy_content(result)

        mock_clipboard.assert_not_called()
        mock_print.assert_called_once()
        assert "Error reading file:" in mock_print.call_args.args[0]


class TestPreview:
    @patch("askfind.interactive.commands.console.print")
    def test_preview_prints_syntax_and_truncation(self, mock_print, tmp_path):
        file_path = tmp_path / "example.py"
        file_path.write_text("\n".join(f"line {i}" for i in range(55)))
        result = FileResult.from_path(file_path)

        preview(result)

        mock_print.assert_any_call(f"[bold]── {file_path} ──[/bold]")
        assert any(call_.args and isinstance(call_.args[0], Syntax) for call_ in mock_print.call_args_list)
        mock_print.assert_any_call("[dim]... (5 more lines)[/dim]")

    @patch("askfind.interactive.commands.console.print")
    def test_preview_rejects_large_files(self, mock_print, tmp_path):
        file_path = tmp_path / "large.txt"
        file_path.write_text("x")
        result = FileResult.from_path(file_path)

        with patch.object(type(result.path), "stat", return_value=SimpleNamespace(st_size=MAX_PREVIEW_SIZE + 1)):
            preview(result)

        mock_print.assert_called_once()
        assert "File too large" in mock_print.call_args.args[0]

    @patch("askfind.interactive.commands.console.print")
    def test_preview_rejects_symlink(self, mock_print, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("secret")
        symlink = tmp_path / "target-link.txt"
        symlink.symlink_to(target)
        result = FileResult.from_path(symlink)

        preview(result)

        mock_print.assert_called_once_with(f"[red]Skipping symlink: {symlink}[/red]")

    @patch("askfind.interactive.commands.console.print")
    def test_preview_handles_oserror(self, mock_print, tmp_path):
        missing = tmp_path / "missing.txt"
        result = FileResult(path=missing, size=0, modified=datetime.now(timezone.utc))

        preview(result)

        mock_print.assert_called_once()
        assert "Error reading file:" in mock_print.call_args.args[0]


class TestOpenInEditor:
    @patch("askfind.interactive.commands.console.print")
    @patch("askfind.interactive.commands.subprocess.run")
    @patch("askfind.interactive.commands.shutil.which")
    def test_open_in_editor_rejects_invalid_editor(self, mock_which, mock_run, mock_print, tmp_path):
        file_path = tmp_path / "example.txt"
        file_path.write_text("hello")
        result = FileResult.from_path(file_path)

        open_in_editor(result, "vim;rm")

        mock_which.assert_not_called()
        mock_run.assert_not_called()
        mock_print.assert_called_once_with("[red]Invalid editor value: 'vim;rm'[/red]")

    @patch("askfind.interactive.commands.console.print")
    @patch("askfind.interactive.commands.subprocess.run")
    @patch("askfind.interactive.commands.shutil.which", return_value=None)
    def test_open_in_editor_handles_missing_editor(self, mock_which, mock_run, mock_print, tmp_path):
        file_path = tmp_path / "example.txt"
        file_path.write_text("hello")
        result = FileResult.from_path(file_path)

        open_in_editor(result, "missing-editor")

        mock_which.assert_called_once_with("missing-editor")
        mock_run.assert_not_called()
        mock_print.assert_called_once_with("[red]Editor 'missing-editor' not found in PATH.[/red]")

    @patch("askfind.interactive.commands.subprocess.run")
    @patch("askfind.interactive.commands.shutil.which", return_value="/usr/bin/vim")
    def test_open_in_editor_runs_subprocess_when_editor_exists(self, mock_which, mock_run, tmp_path):
        file_path = tmp_path / "example.txt"
        file_path.write_text("hello")
        result = FileResult.from_path(file_path)

        open_in_editor(result, "vim")

        mock_which.assert_called_once_with("vim")
        mock_run.assert_called_once_with(["/usr/bin/vim", str(file_path)], check=False)

    @patch("askfind.interactive.commands.console.print")
    @patch("askfind.interactive.commands.subprocess.run", side_effect=subprocess.SubprocessError("boom"))
    @patch("askfind.interactive.commands.shutil.which", return_value="/usr/bin/vim")
    def test_open_in_editor_handles_subprocess_error(self, mock_which, mock_run, mock_print, tmp_path):
        file_path = tmp_path / "example.txt"
        file_path.write_text("hello")
        result = FileResult.from_path(file_path)

        open_in_editor(result, "vim")

        mock_which.assert_called_once_with("vim")
        mock_run.assert_called_once_with(["/usr/bin/vim", str(file_path)], check=False)
        mock_print.assert_called_once_with("[red]Error opening editor: boom[/red]")


class TestCopyToClipboard:
    @patch("askfind.interactive.commands.subprocess.run")
    def test_copy_to_clipboard_uses_pbcopy_on_darwin(self, mock_run):
        with patch("askfind.interactive.commands.sys.platform", "darwin"):
            _copy_to_clipboard("hello")

        mock_run.assert_called_once_with(["pbcopy"], input=b"hello", check=True)

    @patch("askfind.interactive.commands.subprocess.run")
    def test_copy_to_clipboard_linux_falls_back_to_xsel(self, mock_run):
        mock_run.side_effect = [FileNotFoundError(), None]

        with patch("askfind.interactive.commands.sys.platform", "linux"):
            _copy_to_clipboard("hello")

        assert mock_run.call_args_list == [
            call(["xclip", "-selection", "clipboard"], input=b"hello", check=True),
            call(["xsel", "--clipboard", "--input"], input=b"hello", check=True),
        ]

    @patch("askfind.interactive.commands.subprocess.run")
    def test_copy_to_clipboard_uses_clip_on_windows(self, mock_run):
        with patch("askfind.interactive.commands.sys.platform", "win32"):
            _copy_to_clipboard("hello")

        mock_run.assert_called_once_with(["clip"], input=b"hello", check=True)
