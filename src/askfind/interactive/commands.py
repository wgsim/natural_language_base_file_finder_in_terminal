"""Action commands for interactive mode."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.syntax import Syntax

from askfind.output.formatter import FileResult

console = Console()

# Maximum file size for content operations (1 MB for clipboard, 10 MB for preview)
MAX_CLIPBOARD_SIZE = 1 * 1024 * 1024
MAX_PREVIEW_SIZE = 10 * 1024 * 1024


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(1024)
    except OSError:
        return False
    return b"\x00" in chunk


def copy_path(result: FileResult) -> None:
    path_str = str(result.path)
    if not _copy_to_clipboard(path_str):
        return
    console.print(f"[green]Copied: {path_str}[/green]")


def copy_content(result: FileResult) -> None:
    try:
        # Check if file is a symlink for security
        if result.path.is_symlink():
            console.print(f"[red]Skipping symlink: {result.path}[/red]")
            return
        # Check file size before reading
        file_size = result.path.stat().st_size
        if file_size > MAX_CLIPBOARD_SIZE:
            console.print(f"[yellow]File too large ({file_size / 1024 / 1024:.1f} MB). Max: {MAX_CLIPBOARD_SIZE / 1024 / 1024:.0f} MB[/yellow]")
            return
        if _is_binary(result.path):
            console.print(f"[yellow]Skipping binary file: {result.path}[/yellow]")
            return
        content = result.path.read_text(errors="replace")
        if not _copy_to_clipboard(content):
            return
        console.print(f"[green]Copied content of: {result.path.name}[/green]")
    except (OSError, UnicodeDecodeError) as e:
        console.print(f"[red]Error reading file: {e}[/red]")


def preview(result: FileResult) -> None:
    try:
        # Check if file is a symlink for security
        if result.path.is_symlink():
            console.print(f"[red]Skipping symlink: {result.path}[/red]")
            return
        # Check file size before reading
        file_size = result.path.stat().st_size
        if file_size > MAX_PREVIEW_SIZE:
            console.print(f"[yellow]File too large ({file_size / 1024 / 1024:.1f} MB). Max: {MAX_PREVIEW_SIZE / 1024 / 1024:.0f} MB[/yellow]")
            return
        if _is_binary(result.path):
            console.print(f"[yellow]Skipping binary file: {result.path}[/yellow]")
            return
        content = result.path.read_text(errors="replace")
        # Show first 50 lines
        lines = content.splitlines()[:50]
        text = "\n".join(lines)
        suffix = result.path.suffix.lstrip(".")
        syntax = Syntax(text, suffix or "text", theme="monokai", line_numbers=True)
        console.print(f"[bold]── {result.path} ──[/bold]")
        console.print(syntax)
        if len(content.splitlines()) > 50:
            console.print(f"[dim]... ({len(content.splitlines()) - 50} more lines)[/dim]")
    except OSError as e:
        console.print(f"[red]Error reading file: {e}[/red]")


def open_in_editor(result: FileResult, editor: str = "vim") -> None:
    # Validate editor to prevent command injection
    # Only allow simple executable names, no paths or shell metacharacters
    if not editor or any(c in editor for c in ["/", "\\", ";", "&", "|", "$", "`", "\n", "\r"]):
        console.print(f"[red]Invalid editor value: '{editor}'[/red]")
        return

    # Verify editor exists using shutil.which
    editor_path = shutil.which(editor)
    if not editor_path:
        console.print(f"[red]Editor '{editor}' not found in PATH.[/red]")
        return

    try:
        subprocess.run([editor_path, str(result.path)], check=False)
    except (OSError, subprocess.SubprocessError) as e:
        console.print(f"[red]Error opening editor: {e}[/red]")


def _copy_to_clipboard(text: str) -> bool:
    if sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
        return True
    elif sys.platform == "linux":
        try:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
            return True
        except FileNotFoundError:
            try:
                subprocess.run(["xsel", "--clipboard", "--input"], input=text.encode(), check=True)
                return True
            except FileNotFoundError:
                console.print("[red]Clipboard tool not found (xclip/xsel). Install xclip or xsel to enable copy.[/red]")
                return False
    else:
        # Windows
        subprocess.run(["clip"], input=text.encode(), check=True)
        return True
