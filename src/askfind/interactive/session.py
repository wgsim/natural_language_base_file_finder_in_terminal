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
from askfind.llm.fallback import has_meaningful_filters, parse_query_fallback
from askfind.llm.parser import parse_llm_response
from askfind.logging_config import get_logger
from askfind.output.formatter import FileResult, human_size
from askfind.search.cache import SearchCache, build_search_cache_key, compute_root_fingerprint
from askfind.search.filters import DEFAULT_SIMILARITY_THRESHOLD, SearchFilters
from askfind.search.walker import walk_and_filter

console = Console()
logger = get_logger(__name__)

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

        cache_enabled = getattr(config, "cache_enabled", True)
        cache_ttl_seconds = getattr(config, "cache_ttl_seconds", 300)
        if not isinstance(cache_enabled, bool):
            cache_enabled = True
        if not isinstance(cache_ttl_seconds, int) or cache_ttl_seconds < 1:
            cache_ttl_seconds = 300
        self.cache = SearchCache(ttl_seconds=cache_ttl_seconds) if cache_enabled else None

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
            respect_ignore_files = getattr(self.config, "respect_ignore_files", True)
            follow_symlinks = getattr(self.config, "follow_symlinks", False)
            exclude_binary_files = getattr(self.config, "exclude_binary_files", True)
            search_archives = getattr(self.config, "search_archives", False)
            traversal_workers = getattr(self.config, "parallel_workers", 1)
            similarity_threshold = getattr(
                self.config,
                "similarity_threshold",
                DEFAULT_SIMILARITY_THRESHOLD,
            )
            if not isinstance(respect_ignore_files, bool):
                respect_ignore_files = True
            if not isinstance(follow_symlinks, bool):
                follow_symlinks = False
            if not isinstance(exclude_binary_files, bool):
                exclude_binary_files = True
            if not isinstance(search_archives, bool):
                search_archives = False
            if not isinstance(traversal_workers, int) or traversal_workers < 1:
                traversal_workers = 1
            if (
                not isinstance(similarity_threshold, (int, float))
                or isinstance(similarity_threshold, bool)
                or float(similarity_threshold) < 0.0
                or float(similarity_threshold) > 1.0
            ):
                similarity_threshold = DEFAULT_SIMILARITY_THRESHOLD
            similarity_threshold = float(similarity_threshold)

            max_results = getattr(self.config, "max_results", 50)
            if not isinstance(max_results, int):
                max_results = 50

            model = getattr(self.config, "model", "")
            if not isinstance(model, str):
                model = ""
            base_url = getattr(self.config, "base_url", "")
            if not isinstance(base_url, str):
                base_url = ""

            cached_paths: list[Path] | None = None
            cache_key: str | None = None
            root_fingerprint: str | None = None
            if self.cache is not None:
                cache_key = build_search_cache_key(
                    query=query,
                    root=self.root,
                    model=model,
                    base_url=base_url,
                    max_results=max_results,
                    no_rerank=True,
                    respect_ignore_files=respect_ignore_files,
                    follow_symlinks=follow_symlinks,
                    exclude_binary_files=exclude_binary_files,
                    search_archives=search_archives,
                    traversal_workers=traversal_workers,
                    similarity_threshold=similarity_threshold,
                )
                root_fingerprint = compute_root_fingerprint(self.root)
                try:
                    cached_paths = self.cache.get(key=cache_key, root_fingerprint=root_fingerprint)
                except OSError:
                    logger.debug("Interactive cache read failed; continuing without cache", exc_info=True)
                    cached_paths = None

            if cached_paths is not None:
                loaded: list[FileResult] = []
                for path in cached_paths:
                    try:
                        loaded.append(FileResult.from_path(path))
                    except OSError:
                        cached_paths = None
                        break
                if cached_paths is not None:
                    self.results = loaded
                else:
                    self.results = []
            else:
                self.results = []

            if cached_paths is None:
                fallback_used = False
                try:
                    raw = self.client.extract_filters(query)
                    filters = parse_llm_response(raw)
                    if isinstance(filters, SearchFilters) and not has_meaningful_filters(filters):
                        fallback_filters = parse_query_fallback(query)
                        if has_meaningful_filters(fallback_filters):
                            filters = fallback_filters
                            fallback_used = True
                except httpx.HTTPError:
                    fallback_filters = parse_query_fallback(query)
                    if has_meaningful_filters(fallback_filters):
                        filters = fallback_filters
                        fallback_used = True
                    else:
                        raise

                if hasattr(filters, "similarity_threshold"):
                    filters.similarity_threshold = similarity_threshold
                paths = list(
                    walk_and_filter(
                        self.root,
                        filters,
                        max_results=max_results,
                        respect_ignore_files=respect_ignore_files,
                        follow_symlinks=follow_symlinks,
                        exclude_binary_files=exclude_binary_files,
                        search_archives=search_archives,
                        traversal_workers=traversal_workers,
                    )
                )
                self.results = [FileResult.from_path(p) for p in paths]
                if fallback_used:
                    console.print("[yellow]Warning: LLM unavailable; using heuristic fallback filters.[/yellow]")

                if self.cache is not None and cache_key is not None and root_fingerprint is not None:
                    try:
                        self.cache.set(
                            key=cache_key,
                            root_fingerprint=root_fingerprint,
                            paths=[r.path for r in self.results],
                        )
                    except OSError:
                        logger.debug("Interactive cache write failed; continuing without cache", exc_info=True)

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
