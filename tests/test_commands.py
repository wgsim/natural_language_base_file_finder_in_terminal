"""Tests for interactive commands."""

from unittest.mock import patch

from askfind.interactive.commands import copy_content
from askfind.interactive.commands import preview
from askfind.output.formatter import FileResult


def test_copy_content_handles_decode_error(tmp_path):
    f = tmp_path / "bin.dat"
    f.write_bytes(b"\xff\xfe\xfd")
    result = FileResult.from_path(f)
    with patch("askfind.interactive.commands._copy_to_clipboard") as mocked:
        copy_content(result)
        mocked.assert_called_once()


def test_copy_content_reports_missing_clipboard_tool(tmp_path, capsys):
    f = tmp_path / "note.txt"
    f.write_text("hello")
    result = FileResult.from_path(f)
    with patch("askfind.interactive.commands.sys.platform", "linux"):
        with patch("askfind.interactive.commands.subprocess.run", side_effect=FileNotFoundError()):
            copy_content(result)
    captured = capsys.readouterr()
    assert "Install xclip or xsel" in captured.out
    assert "Copied content of" not in captured.out


def test_copy_content_skips_binary(tmp_path, capsys):
    f = tmp_path / "bin.dat"
    f.write_bytes(b"\x00\xff\x00\xff")
    result = FileResult.from_path(f)
    with patch("askfind.interactive.commands._copy_to_clipboard") as mocked:
        copy_content(result)
        mocked.assert_not_called()
    captured = capsys.readouterr()
    assert "binary" in captured.out.lower()


def test_copy_content_uses_wl_copy_when_available(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("hello")
    result = FileResult.from_path(f)
    with patch("askfind.interactive.commands.sys.platform", "linux"):
        with patch("askfind.interactive.commands.shutil.which", return_value="/usr/bin/wl-copy"):
            with patch("askfind.interactive.commands.subprocess.run") as mocked:
                copy_content(result)
                assert mocked.called
                args, kwargs = mocked.call_args
                assert args[0] == ["/usr/bin/wl-copy"]


def test_copy_content_reports_missing_clipboard_tool_on_windows(tmp_path, capsys):
    f = tmp_path / "note.txt"
    f.write_text("hello")
    result = FileResult.from_path(f)
    with patch("askfind.interactive.commands.sys.platform", "win32"):
        with patch("askfind.interactive.commands.subprocess.run", side_effect=FileNotFoundError()):
            copy_content(result)
    captured = capsys.readouterr()
    assert "Clipboard tool not found" in captured.out


def test_preview_skips_binary(tmp_path, capsys):
    f = tmp_path / "bin.dat"
    f.write_bytes(b"\x00\xff")
    result = FileResult.from_path(f)
    preview(result)
    captured = capsys.readouterr()
    assert "Skipping binary file" in captured.out


def test_preview_reports_line_limit(tmp_path, capsys):
    f = tmp_path / "many.txt"
    f.write_text("\n".join(["x"] * 60))
    result = FileResult.from_path(f)
    preview(result)
    captured = capsys.readouterr()
    assert "more lines" in captured.out


def test_copy_and_preview_binary_message_consistent(tmp_path, capsys):
    f = tmp_path / "bin.dat"
    f.write_bytes(b"\x00\xff")
    result = FileResult.from_path(f)
    copy_content(result)
    preview(result)
    out = capsys.readouterr().out
    assert out.count("Skipping binary file") == 2
