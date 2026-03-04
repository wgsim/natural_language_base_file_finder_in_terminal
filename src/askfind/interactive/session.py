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
from askfind.config_reader import ConfigReader
from askfind.interactive.commands import copy_content, copy_path, open_in_editor, preview
from askfind.llm.client import LLMClient
from askfind.llm.mode import DEFAULT_LLM_MODE, normalize_llm_mode
from askfind.logging_config import get_logger
from askfind.output.formatter import FileResult, human_size
from askfind.query_processor import QueryProcessor, QueryProcessorStats
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

        # Use ConfigReader for type-safe config access
        reader = ConfigReader(config)
        self.offline_mode = reader.get_bool("offline_mode", default=False)
        configured_llm_mode = reader.get_llm_mode(default=DEFAULT_LLM_MODE)
        self.llm_mode = "off" if self.offline_mode else configured_llm_mode
        self.client: LLMClient | None = None

        if self.llm_mode == "always":
            api_key = get_api_key()
            if not api_key:
                console.print("[red]No API key configured. Run `askfind config set-key`.[/red]")
                raise SystemExit(2)

            self.client = LLMClient(
                base_url=reader.get_str("base_url", default=""),
                api_key=api_key,
                model=reader.get_str("model", default=""),
            )

        cache_enabled = reader.get_bool("cache_enabled", default=True)
        cache_ttl_seconds = reader.get_positive_int("cache_ttl_seconds", default=300)
        self.cache = SearchCache(ttl_seconds=cache_ttl_seconds) if cache_enabled else None

        # Cache config reader for use in search
        self._reader = reader

        # Query processor with stats tracking
        self._query_processor = QueryProcessor(
            llm_mode=self.llm_mode,
            offline_mode=self.offline_mode,
        )
        self._query_stats = QueryProcessorStats()

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
            if self.client is not None:
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
            # Use cached ConfigReader for type-safe config access
            reader = self._reader
            respect_ignore_files = reader.get_bool("respect_ignore_files", default=True)
            follow_symlinks = reader.get_bool("follow_symlinks", default=False)
            exclude_binary_files = reader.get_bool("exclude_binary_files", default=True)
            search_archives = reader.get_bool("search_archives", default=False)
            traversal_workers = reader.get_positive_int("parallel_workers", default=1)
            similarity_threshold = reader.get_similarity_threshold(default=DEFAULT_SIMILARITY_THRESHOLD)
            max_results = reader.get_non_negative_int("max_results", default=50)
            model = reader.get_str("model", default="")
            base_url = reader.get_str("base_url", default="")

            # Process query using QueryProcessor
            query_result = self._query_processor.process(
                query,
                client=self._get_or_create_client(base_url, model),
                stats=self._query_stats,
            )

            if query_result.is_rejected:
                console.print(f"[red]{query_result.error_message}[/red]")
                self.results = []
                return

            filters = query_result.filters
            filters.similarity_threshold = similarity_threshold

            # Build cache key based on query decision
            use_llm = self._query_processor.llm_mode != "off" and not query_result.used_fallback
            cache_mode = f"{self.llm_mode}:{'llm' if use_llm else 'fallback'}"
            if use_llm:
                cache_model = f"{model}::llm_mode={cache_mode}"
                cache_base_url = base_url
            else:
                cache_model = f"__fallback__::llm_mode={cache_mode}"
                cache_base_url = "offline://fallback"

            cached_paths: list[Path] | None = None
            cache_key: str | None = None
            root_fingerprint: str | None = None
            if self.cache is not None:
                cache_key = build_search_cache_key(
                    query=query,
                    root=self.root,
                    model=cache_model,
                    base_url=cache_base_url,
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

                if query_result.used_fallback:
                    logger.debug(
                        "Interactive fallback parser used (reason=%s)",
                        query_result.fallback_reason or "unknown",
                    )
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

    def _get_or_create_client(self, base_url: str, model: str) -> LLMClient | None:
        """Get existing LLM client or create a new one if needed."""
        if self.client is not None:
            return self.client

        if self.llm_mode == "off":
            return None

        api_key = get_api_key()
        if not api_key:
            return None

        self.client = LLMClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
        return self.client
