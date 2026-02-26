"""Interactive REPL session for askfind."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.table import Table

from askfind.config import Config, get_api_key
from askfind.interactive.commands import copy_content, copy_path, open_in_editor, preview
from askfind.llm.client import LLMClient
from askfind.llm.parser import parse_llm_response
from askfind.output.formatter import FileResult, human_size
from askfind.search.walker import walk_and_filter

console = Console()

HELP_TEXT = """\
[bold]Available commands:[/bold]
  [cyan]<natural language query>[/cyan]  Search for files
  [cyan]copy path <n>[/cyan]             Copy file path to clipboard
  [cyan]copy content <n>[/cyan]          Copy file contents to clipboard
  [cyan]preview <n>[/cyan]               Preview file contents
  [cyan]open <n>[/cyan]                  Open file in editor
  [cyan]help[/cyan]                      Show this message
  [cyan]exit[/cyan] / [cyan]quit[/cyan]               Exit askfind
"""


class InteractiveSession:
    def __init__(self, config: Config, root: Path) -> None:
        self.config = config
        self.root = root.resolve()
        self.results: list[FileResult] = []

        api_key = get_api_key()
        if not api_key:
            console.print("[red]No API key configured. Run `askfind config set-key`.[/red]")
            raise SystemExit(2)

        self.client = LLMClient(
            base_url=config.base_url,
            api_key=api_key,
            model=config.model,
        )

    def run(self) -> None:
        session: PromptSession[str] = PromptSession()
        console.print("[bold blue]askfind[/bold blue] [dim]interactive mode[/dim]")
        console.print("[dim]Type 'help' for commands, 'exit' to quit.[/dim]\n")

        try:
            while True:
                try:
                    user_input = session.prompt(HTML("<ansiblue><b>askfind&gt;</b></ansiblue> ")).strip()
                except (EOFError, KeyboardInterrupt):
                    break

                if not user_input:
                    continue
                if user_input in ("exit", "quit"):
                    break
                if user_input == "help":
                    console.print(HELP_TEXT)
                    continue

                # Check for action commands
                if self._handle_action(user_input):
                    continue

                # Natural language query
                self._search(user_input)
        finally:
            self.client.close()

    def _handle_action(self, text: str) -> bool:
        """Handle action commands. Returns True if handled."""
        match = re.match(r"^(copy path|copy content|preview|open)\s+(\d+)$", text, re.IGNORECASE)
        if not match:
            return False

        action = match.group(1).lower()
        idx = int(match.group(2)) - 1  # 1-indexed to 0-indexed

        if idx < 0 or idx >= len(self.results):
            console.print(f"[red]Invalid index. Have {len(self.results)} results.[/red]")
            return True

        result = self.results[idx]
        if action == "copy path":
            copy_path(result)
        elif action == "copy content":
            copy_content(result)
        elif action == "preview":
            preview(result)
        elif action == "open":
            open_in_editor(result, self.config.editor)
        return True

    def _search(self, query: str) -> None:
        try:
            raw = self.client.extract_filters(query)
            filters = parse_llm_response(raw)
            paths = list(
                walk_and_filter(
                    self.root,
                    filters,
                    max_results=self.config.max_results,
                    respect_ignore_files=getattr(self.config, "respect_ignore_files", True),
                    follow_symlinks=getattr(self.config, "follow_symlinks", False),
                    exclude_binary_files=getattr(self.config, "exclude_binary_files", True),
                    traversal_workers=getattr(self.config, "parallel_workers", 4),
                )
            )
            self.results = [FileResult.from_path(p) for p in paths]

            if not self.results:
                console.print("[dim]No files found.[/dim]")
                return

            console.print(f"[dim]Found {len(self.results)} file(s):[/dim]")
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_column("idx", style="yellow bold", width=5)
            table.add_column("path", style="blue")
            table.add_column("size", style="dim", justify="right", width=10)
            table.add_column("date", style="dim", width=12)

            for i, r in enumerate(self.results, 1):
                size_str = human_size(r.size)
                date_str = r.modified.strftime("%b %d %Y")
                table.add_row(f"[{i}]", str(r.path), size_str, date_str)

            console.print(table)
            console.print()
        except (httpx.HTTPError, OSError, ValueError, RuntimeError) as e:
            console.print(f"[red]Error: {e}[/red]")
