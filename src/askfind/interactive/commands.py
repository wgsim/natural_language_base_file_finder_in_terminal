"""Action commands for interactive mode."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.syntax import Syntax

from askfind.output.formatter import FileResult

console = Console()


def copy_path(result: FileResult) -> None:
    path_str = str(result.path)
    _copy_to_clipboard(path_str)
    console.print(f"[green]Copied: {path_str}[/green]")


def copy_content(result: FileResult) -> None:
    try:
        content = result.path.read_text()
        _copy_to_clipboard(content)
        console.print(f"[green]Copied content of: {result.path.name}[/green]")
    except OSError as e:
        console.print(f"[red]Error reading file: {e}[/red]")


def preview(result: FileResult) -> None:
    try:
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
    try:
        subprocess.run([editor, str(result.path)])
    except FileNotFoundError:
        console.print(f"[red]Editor '{editor}' not found.[/red]")


def _copy_to_clipboard(text: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
    elif sys.platform == "linux":
        try:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
        except FileNotFoundError:
            subprocess.run(["xsel", "--clipboard", "--input"], input=text.encode(), check=True)
    else:
        # Windows
        subprocess.run(["clip"], input=text.encode(), check=True)
