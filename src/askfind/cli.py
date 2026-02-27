"""CLI entry point for askfind."""

from __future__ import annotations

import argparse
import ipaddress
import json as json_module
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dataclasses import dataclass, field, fields

from askfind.config import Config, get_api_key, get_config_path, set_api_key
from askfind.llm.client import LLMClient
from askfind.llm.parser import parse_llm_response
from askfind.logging_config import setup_logging, get_logger
from askfind.search.cache import SearchCache, build_search_cache_key, compute_root_fingerprint
from askfind.search.index import (
    IndexQueryDiagnostics,
    IndexOptions,
    build_index,
    clear_index,
    get_index_status,
    query_index,
    update_index,
)

logger = get_logger(__name__)
from askfind.output.formatter import FileResult, format_json, format_plain, format_verbose
from askfind.search.walker import walk_and_filter


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser. Returns parser for search mode or config mode depending on argv."""
    parser = argparse.ArgumentParser(
        prog="askfind",
        description="Find files using natural language queries.",
    )
    parser.add_argument("query", nargs="?", help="Natural language query or 'config' subcommand")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive mode")
    parser.add_argument("-r", "--root", default=".", help="Search root directory")
    parser.add_argument("-m", "--max", type=int, default=0, dest="max_results", help="Max results (0=use config)")
    parser.add_argument("--workers", type=int, default=0, help="Traversal workers (0=use config)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show file metadata")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    parser.add_argument("--model", help="Override LLM model")
    parser.add_argument("--api-key", help="One-off API key")
    parser.add_argument("--no-rerank", action="store_true", help="Skip semantic re-ranking")
    parser.add_argument("--no-cache", action="store_true", help="Disable search cache for this command")
    parser.add_argument(
        "--cache-stats",
        action="store_true",
        help="Print cache hit/miss/set counters to stderr",
    )
    parser.add_argument(
        "--no-ignore",
        action="store_true",
        help="Ignore .gitignore/.askfindignore rules during traversal",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="Follow symlinked files/directories within the search root",
    )
    parser.add_argument(
        "--include-binary",
        action="store_true",
        help="Include binary files in results (default excludes binary files)",
    )
    parser.add_argument(
        "--search-archives",
        action="store_true",
        help="Search inside supported archives (.zip, .tar.gz) by entry path/name",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--interactive-session", action="store_true", help=argparse.SUPPRESS)
    return parser


def _validate_base_url(url: str) -> tuple[bool, str]:
    """Validate base_url for SSRF protection.

    Returns (is_valid, error_message).
    """
    try:
        parsed = urlparse(url)

        # Require HTTPS unless localhost
        if parsed.scheme not in ("https", "http"):
            return False, "URL must use http:// or https:// scheme"

        if parsed.scheme == "http":
            # Only allow HTTP for localhost/127.0.0.1
            if parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
                return False, "HTTP is only allowed for localhost. Use HTTPS for remote servers."

        # Block RFC 1918 private addresses and link-local
        if parsed.hostname:
            try:
                ip = ipaddress.ip_address(parsed.hostname)
                if ip.is_private or ip.is_link_local or ip.is_loopback:
                    if parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
                        return False, f"Private/internal IP addresses are not allowed: {parsed.hostname}"
            except ValueError:
                # Not an IP address, it's a hostname - that's fine
                pass

        return True, ""
    except (AttributeError, TypeError, ValueError) as e:
        return False, f"Invalid URL format: {e}"


def _build_config_parser() -> argparse.ArgumentParser:
    """Build config subcommand parser."""
    parser = argparse.ArgumentParser(prog="askfind config")
    subparsers = parser.add_subparsers(dest="config_action", required=True)

    subparsers.add_parser("show", help="Show current configuration")

    set_parser = subparsers.add_parser("set", help="Set a config value")
    set_parser.add_argument("key", help="Config key")
    set_parser.add_argument("value", help="Config value")

    subparsers.add_parser("set-key", help="Store API key in system keychain")

    models_parser = subparsers.add_parser("models", help="List available models")
    models_parser.add_argument("--provider", help="Filter by provider")

    return parser


def _add_index_root_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-r", "--root", default=".", help="Search root directory")


def _add_index_traversal_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workers", type=int, default=0, help="Traversal workers (0=use config)")
    parser.add_argument(
        "--no-ignore",
        action="store_true",
        help="Ignore .gitignore/.askfindignore rules during traversal",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="Follow symlinked files/directories within the search root",
    )
    parser.add_argument(
        "--include-binary",
        action="store_true",
        help="Include binary files in index (default excludes binary files)",
    )


def _build_index_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="askfind index")
    subparsers = parser.add_subparsers(dest="index_action", required=True)

    build_parser = subparsers.add_parser("build", help="Build file index for a search root")
    _add_index_root_arg(build_parser)
    _add_index_traversal_args(build_parser)

    update_parser = subparsers.add_parser("update", help="Refresh file index for a search root")
    _add_index_root_arg(update_parser)
    _add_index_traversal_args(update_parser)

    status_parser = subparsers.add_parser("status", help="Show index status for a search root")
    _add_index_root_arg(status_parser)

    clear_parser = subparsers.add_parser("clear", help="Delete index for a search root")
    _add_index_root_arg(clear_parser)

    return parser


def _has_root_override(raw_argv: list[str]) -> bool:
    """Return True when root was explicitly provided on CLI."""
    for arg in raw_argv:
        if arg in ("-r", "--root") or arg.startswith("--root="):
            return True
    return False


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("must be a boolean value (true/false)")


def _read_bool_config(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _read_positive_int_config(value: object, *, default: int) -> int:
    if isinstance(value, int) and value >= 1:
        return value
    return default


def _emit_cache_stats(cache: SearchCache | None) -> None:
    if cache is None:
        print("cache: disabled", file=sys.stderr)
    else:
        stats = cache.stats()
        hits = stats.get("hits", 0)
        misses = stats.get("misses", 0)
        sets = stats.get("sets", 0)
        print(f"cache: hits={hits} misses={misses} sets={sets}", file=sys.stderr)


@dataclass
class _IndexQueryRuntimeStats:
    hits: int = 0
    fallbacks: int = 0
    fallback_reasons: dict[str, int] = field(default_factory=dict)

    def record_hit(self) -> None:
        self.hits += 1

    def record_fallback(self, reason: str | None) -> None:
        self.fallbacks += 1
        normalized_reason = reason or "unknown"
        self.fallback_reasons[normalized_reason] = self.fallback_reasons.get(normalized_reason, 0) + 1


def _emit_index_stats(index_stats: _IndexQueryRuntimeStats) -> None:
    if not index_stats.fallback_reasons:
        reasons_text = "none"
    else:
        reasons_text = ",".join(
            f"{reason}:{count}"
            for reason, count in sorted(index_stats.fallback_reasons.items())
        )
    print(
        f"index: hits={index_stats.hits} "
        f"fallbacks={index_stats.fallbacks} "
        f"reasons={reasons_text}",
        file=sys.stderr,
    )


def _handle_index(args: argparse.Namespace, *, raw_argv: list[str]) -> int:
    config = Config.from_file(get_config_path())
    root_value = args.root if _has_root_override(raw_argv) else config.default_root
    root_path = Path(root_value).resolve()

    try:
        if args.index_action in {"build", "update"}:
            if args.workers < 0:
                print("Error: --workers must be >= 0.", file=sys.stderr)
                return 2
            configured_workers = _read_positive_int_config(
                getattr(config, "parallel_workers", 1),
                default=1,
            )
            options = IndexOptions(
                respect_ignore_files=_read_bool_config(
                    getattr(config, "respect_ignore_files", True),
                    default=True,
                ) and not args.no_ignore,
                follow_symlinks=_read_bool_config(
                    getattr(config, "follow_symlinks", False),
                    default=False,
                ) or args.follow_symlinks,
                exclude_binary_files=(
                    _read_bool_config(
                        getattr(config, "exclude_binary_files", True),
                        default=True,
                    )
                    and not args.include_binary
                ),
                search_archives=False,
                traversal_workers=args.workers or configured_workers,
            )

            if args.index_action == "build":
                result = build_index(root=root_path, options=options)
                print(f"Index built for {result.root} (files={result.file_count})")
            else:
                result = update_index(root=root_path, options=options)
                print(f"Index updated for {result.root} (files={result.file_count})")
            return 0

        if args.index_action == "status":
            status = get_index_status(root=root_path)
            exists_text = "yes" if status.exists else "no"
            stale_text = "yes" if status.stale else "no"
            print(
                f"Index status for {status.root}: "
                f"exists={exists_text} files={status.file_count} stale={stale_text}"
            )
            return 0

        if args.index_action == "clear":
            cleared = clear_index(root=root_path)
            if cleared.cleared:
                print(f"Index cleared for {cleared.root}")
            else:
                print(f"No index found for {cleared.root}")
            return 0
    except FileNotFoundError:
        print(f"Error: Search root not found: {root_value}", file=sys.stderr)
        return 3
    except NotADirectoryError:
        print(f"Error: Search root is not a directory: {root_value}", file=sys.stderr)
        return 3
    except PermissionError:
        print(
            "Error: Permission denied while accessing search root or index cache",
            file=sys.stderr,
        )
        return 3
    except OSError:
        logger.exception("Unhandled error while executing askfind index command")
        print(
            "Error: Unexpected internal error. Run with --debug for details.",
            file=sys.stderr,
        )
        return 3

    return 2


def _handle_config(args: argparse.Namespace) -> int:
    config = Config.from_file(get_config_path())
    if args.config_action == "show":
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(title="askfind configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("base_url", config.base_url)
        table.add_row("model", config.model)
        table.add_row("default_root", config.default_root)
        table.add_row("max_results", str(config.max_results))
        table.add_row("parallel_workers", str(config.parallel_workers))
        table.add_row("cache_enabled", str(config.cache_enabled))
        table.add_row("cache_ttl_seconds", str(config.cache_ttl_seconds))
        table.add_row("respect_ignore_files", str(config.respect_ignore_files))
        table.add_row("follow_symlinks", str(config.follow_symlinks))
        table.add_row("exclude_binary_files", str(config.exclude_binary_files))
        table.add_row("search_archives", str(config.search_archives))
        table.add_row("editor", config.editor)
        api_key = get_api_key()
        table.add_row("api_key", "****" + api_key[-4:] if api_key else "[not set]")
        console.print(table)
        return 0
    if args.config_action == "set":
        # Validate config key against known fields
        valid_keys = {f.name for f in fields(Config)}
        if args.key not in valid_keys:
            print(
                f"Error: Unknown config key '{args.key}'. "
                f"Valid keys: {', '.join(sorted(valid_keys))}",
                file=sys.stderr
            )
            return 2

        # Type validation and coercion
        value = args.value

        # Validate base_url for SSRF protection
        if args.key == "base_url":
            is_valid, error = _validate_base_url(value)
            if not is_valid:
                print(f"Error: {error}", file=sys.stderr)
                return 2

        # Coerce integer config values
        if args.key in {"max_results", "parallel_workers", "cache_ttl_seconds"}:
            try:
                value = int(value)
            except ValueError:
                print(f"Error: '{args.key}' must be an integer.", file=sys.stderr)
                return 2
            if args.key in {"parallel_workers", "cache_ttl_seconds"} and value < 1:
                print(f"Error: '{args.key}' must be >= 1.", file=sys.stderr)
                return 2

        if args.key in {
            "cache_enabled",
            "respect_ignore_files",
            "follow_symlinks",
            "exclude_binary_files",
            "search_archives",
        }:
            try:
                value = _parse_bool(value)
            except ValueError:
                print(f"Error: '{args.key}' must be true/false.", file=sys.stderr)
                return 2

        setattr(config, args.key, value)
        config.save(get_config_path())
        print(f"Set {args.key} = {value}")
        return 0
    if args.config_action == "set-key":
        from getpass import getpass
        key = getpass("Enter API key: ")
        set_api_key(key)
        print("API key stored in system keychain.")
        return 0
    if args.config_action == "models":
        api_key = get_api_key()
        if not api_key:
            print("Error: No API key configured.", file=sys.stderr)
            return 2
        try:
            resp = httpx.get(
                f"{config.base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            models = resp.json().get("data", [])
            for m in models:
                print(m.get("id", "unknown"))
        except httpx.HTTPStatusError as e:
            print(f"Error: API returned HTTP {e.response.status_code}", file=sys.stderr)
            return 3
        except httpx.RequestError:
            print(f"Error: Cannot connect to API server at {config.base_url}", file=sys.stderr)
            return 3
        except (ValueError, TypeError, KeyError, RuntimeError) as e:
            print(f"Error: {type(e).__name__}", file=sys.stderr)
            return 3
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    # Get actual argv - if None, use sys.argv[1:]
    raw_argv = argv if argv is not None else sys.argv[1:]

    # Early setup of logging if --debug is present
    if "--debug" in raw_argv:
        setup_logging(debug=True)
    else:
        setup_logging()

    logger.debug(f"Starting askfind with args: {raw_argv}")

    # Check if first arg is "config" subcommand
    if raw_argv and len(raw_argv) > 0 and raw_argv[0] == "config":
        config_parser = _build_config_parser()
        args = config_parser.parse_args(raw_argv[1:])  # Skip "config" word
        return _handle_config(args)

    # Check if first arg is "index" subcommand
    if raw_argv and len(raw_argv) > 0 and raw_argv[0] == "index":
        index_parser = _build_index_parser()
        args = index_parser.parse_args(raw_argv[1:])  # Skip "index" word
        return _handle_index(args, raw_argv=raw_argv[1:])

    # Otherwise parse as search/interactive command
    parser = build_parser()
    args = parser.parse_args(raw_argv)

    if not args.query and not args.interactive and not args.interactive_session:
        parser.print_help()
        return 2

    config = Config.from_file(get_config_path())
    respect_ignore_files = _read_bool_config(
        getattr(config, "respect_ignore_files", True),
        default=True,
    ) and not args.no_ignore
    follow_symlinks = _read_bool_config(
        getattr(config, "follow_symlinks", False),
        default=False,
    ) or args.follow_symlinks
    exclude_binary_files = _read_bool_config(
        getattr(config, "exclude_binary_files", True),
        default=True,
    )
    search_archives = _read_bool_config(
        getattr(config, "search_archives", False),
        default=False,
    ) or args.search_archives
    cache_enabled = _read_bool_config(
        getattr(config, "cache_enabled", True),
        default=True,
    ) and not args.no_cache
    cache_ttl_seconds = _read_positive_int_config(
        getattr(config, "cache_ttl_seconds", 300),
        default=300,
    )
    if args.workers < 0:
        print("Error: --workers must be >= 0.", file=sys.stderr)
        return 2
    configured_workers = _read_positive_int_config(
        getattr(config, "parallel_workers", 1),
        default=1,
    )
    parallel_workers = args.workers or configured_workers
    if args.include_binary:
        exclude_binary_files = False
    root_value = args.root if _has_root_override(raw_argv) else config.default_root
    root_path = Path(root_value).resolve()

    # Handle --interactive-session (spawned pane)
    if args.interactive_session:
        from askfind.interactive.session import InteractiveSession
        config.respect_ignore_files = respect_ignore_files
        config.follow_symlinks = follow_symlinks
        config.exclude_binary_files = exclude_binary_files
        config.search_archives = search_archives
        config.parallel_workers = parallel_workers
        config.cache_enabled = cache_enabled
        config.cache_ttl_seconds = cache_ttl_seconds
        session = InteractiveSession(config, root_path)
        session.run()
        return 0

    # Handle -i/--interactive (spawn pane or run inline)
    if args.interactive:
        from askfind.interactive.pane import spawn_interactive_pane
        if spawn_interactive_pane():
            return 0  # Pane was spawned, exit this process
        # Fallback: run inline
        from askfind.interactive.session import InteractiveSession
        config.respect_ignore_files = respect_ignore_files
        config.follow_symlinks = follow_symlinks
        config.exclude_binary_files = exclude_binary_files
        config.search_archives = search_archives
        config.parallel_workers = parallel_workers
        config.cache_enabled = cache_enabled
        config.cache_ttl_seconds = cache_ttl_seconds
        session = InteractiveSession(config, root_path)
        session.run()
        return 0

    # Single command mode
    # Warn if API key is passed via CLI (visible in process list)
    if args.api_key:
        print(
            "Warning: --api-key exposes your key in process list and shell history. "
            "Use ASKFIND_API_KEY env var or `askfind config set-key` instead.",
            file=sys.stderr
        )

    api_key = get_api_key(cli_key=args.api_key)
    if not api_key:
        print("Error: No API key configured. Run `askfind config set-key`.", file=sys.stderr)
        return 2

    model = args.model or config.model
    max_results = args.max_results or config.max_results

    # Validate query length
    MAX_QUERY_LENGTH = 1000
    if len(args.query) > MAX_QUERY_LENGTH:
        print(f"Error: Query exceeds maximum length of {MAX_QUERY_LENGTH} characters.", file=sys.stderr)
        return 2

    cache = SearchCache(ttl_seconds=cache_ttl_seconds) if cache_enabled else None
    index_stats = _IndexQueryRuntimeStats()
    cache_key: str | None = None
    root_fingerprint: str | None = None
    if cache is not None:
        cache_key = build_search_cache_key(
            query=args.query,
            root=root_path,
            model=model,
            base_url=config.base_url,
            max_results=max_results,
            no_rerank=args.no_rerank,
            respect_ignore_files=respect_ignore_files,
            follow_symlinks=follow_symlinks,
            exclude_binary_files=exclude_binary_files,
            search_archives=search_archives,
            traversal_workers=parallel_workers,
        )
        root_fingerprint = compute_root_fingerprint(root_path)

    try:
        cached_paths: list[Path] | None = None
        if cache is not None and cache_key is not None and root_fingerprint is not None:
            try:
                cached_paths = cache.get(key=cache_key, root_fingerprint=root_fingerprint)
            except OSError:
                logger.debug("Cache read failed; continuing without cache", exc_info=True)
                cached_paths = None

        results: list[FileResult]
        if cached_paths is not None:
            logger.debug("Cache hit for query execution")
            results = []
            for path in cached_paths:
                try:
                    results.append(FileResult.from_path(path))
                except OSError:
                    logger.debug("Cache entry had inaccessible path; falling back to live search")
                    cached_paths = None
                    break
        else:
            logger.debug("Cache miss for query execution")

        if cached_paths is None:
            logger.debug(f"Initializing LLM client with model={model}, base_url={config.base_url}")
            with LLMClient(base_url=config.base_url, api_key=api_key, model=model) as client:
                logger.debug(f"Sending query to LLM: {args.query}")
                raw_response = client.extract_filters(args.query)
                logger.debug(
                    f"Received LLM response: {raw_response[:200]}..."
                    if len(raw_response) > 200
                    else f"Received LLM response: {raw_response}"
                )
                filters = parse_llm_response(raw_response)
                index_options = IndexOptions(
                    respect_ignore_files=respect_ignore_files,
                    follow_symlinks=follow_symlinks,
                    exclude_binary_files=exclude_binary_files,
                    search_archives=search_archives,
                    traversal_workers=parallel_workers,
                )
                index_diagnostics = IndexQueryDiagnostics()
                indexed_paths = query_index(
                    root=root_path,
                    filters=filters,
                    max_results=max_results,
                    options=index_options,
                    diagnostics=index_diagnostics,
                )
                if indexed_paths is None:
                    index_stats.record_fallback(index_diagnostics.fallback_reason)
                    logger.debug("Index query miss/unusable; falling back to filesystem walk")
                    paths = list(
                        walk_and_filter(
                            root_path,
                            filters,
                            max_results=max_results,
                            respect_ignore_files=respect_ignore_files,
                            follow_symlinks=follow_symlinks,
                            exclude_binary_files=exclude_binary_files,
                            search_archives=search_archives,
                            traversal_workers=parallel_workers,
                        )
                    )
                else:
                    index_stats.record_hit()
                    logger.debug("Index query hit; using indexed paths")
                    paths = indexed_paths
                results = [FileResult.from_path(p) for p in paths]

                # Optional LLM re-ranking for semantic relevance
                if not args.no_rerank and len(results) > 1:
                    from askfind.search.reranker import rerank_results
                    results = rerank_results(client, args.query, results)

            if cache is not None and cache_key is not None and root_fingerprint is not None:
                try:
                    cache.set(
                        key=cache_key,
                        root_fingerprint=root_fingerprint,
                        paths=[r.path for r in results],
                    )
                except OSError:
                    logger.debug("Cache write failed; continuing without cache", exc_info=True)

        if not results:
            if args.cache_stats:
                _emit_cache_stats(cache)
                _emit_index_stats(index_stats)
            return 1

        if args.json_output:
            print(format_json(results))
        elif args.verbose:
            print(format_verbose(results))
        else:
            print(format_plain(results))
        if args.cache_stats:
            _emit_cache_stats(cache)
            _emit_index_stats(index_stats)
        return 0
    except KeyboardInterrupt:
        print("\nSearch cancelled.", file=sys.stderr)
        return 130
    except FileNotFoundError:
        print(f"Error: Search root not found: {root_value}", file=sys.stderr)
        return 3
    except PermissionError:
        print("Error: Permission denied accessing search root", file=sys.stderr)
        return 3
    except httpx.HTTPStatusError as e:
        print(f"Error: API request failed (HTTP {e.response.status_code})", file=sys.stderr)
        return 3
    except httpx.RequestError:
        print("Error: Cannot connect to API server. Check your network and base_url config.", file=sys.stderr)
        return 3
    except json_module.JSONDecodeError:
        print("Error: Invalid response from LLM API", file=sys.stderr)
        return 3
    except (RuntimeError, ValueError, TypeError, OSError):
        logger.exception("Unhandled error while executing askfind query")
        print(
            "Error: Unexpected internal error. Run with --debug for details.",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    sys.exit(main())
