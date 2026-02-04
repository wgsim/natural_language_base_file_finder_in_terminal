"""CLI entry point for askfind."""

from __future__ import annotations

import argparse
import ipaddress
import sys
from pathlib import Path
from urllib.parse import urlparse

from dataclasses import fields

from askfind.config import Config, get_api_key, get_config_path, set_api_key
from askfind.llm.client import LLMClient
from askfind.llm.parser import parse_llm_response
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
    parser.add_argument("-v", "--verbose", action="store_true", help="Show file metadata")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    parser.add_argument("--model", help="Override LLM model")
    parser.add_argument("--api-key", help="One-off API key")
    parser.add_argument("--no-rerank", action="store_true", help="Skip semantic re-ranking")
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
    except Exception as e:
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


def _handle_config(args) -> int:
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

        # Coerce max_results to int
        if args.key == "max_results":
            try:
                value = int(value)
            except ValueError:
                print(f"Error: '{args.key}' must be an integer.", file=sys.stderr)
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
            import httpx
            resp = httpx.get(
                f"{config.base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            models = resp.json().get("data", [])
            provider = args.provider
            printed = 0
            for m in models:
                model_id = m.get("id", "unknown")
                if provider:
                    prefix = model_id.split("/", 1)[0]
                    if prefix != provider:
                        continue
                print(model_id)
                printed += 1
            if provider and printed == 0:
                print(f"No models found for provider '{provider}'", file=sys.stderr)
        except httpx.HTTPStatusError as e:
            print(f"Error: API returned HTTP {e.response.status_code}", file=sys.stderr)
            return 3
        except (httpx.ConnectError, httpx.TimeoutException):
            print(f"Error: Cannot connect to API server at {config.base_url}", file=sys.stderr)
            return 3
        except Exception as e:
            print(f"Error: {type(e).__name__}", file=sys.stderr)
            return 3
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    # Get actual argv - if None, use sys.argv[1:]
    raw_argv = argv if argv is not None else sys.argv[1:]

    # Check if first arg is "config" subcommand
    if raw_argv and len(raw_argv) > 0 and raw_argv[0] == "config":
        config_parser = _build_config_parser()
        args = config_parser.parse_args(raw_argv[1:])  # Skip "config" word
        return _handle_config(args)

    # Otherwise parse as search/interactive command
    parser = build_parser()
    args = parser.parse_args(raw_argv)

    if not args.query and not args.interactive and not args.interactive_session:
        parser.print_help()
        return 2

    config = Config.from_file(get_config_path())

    # Handle --interactive-session (spawned pane)
    if args.interactive_session:
        from askfind.interactive.session import InteractiveSession
        session = InteractiveSession(config, Path(args.root))
        session.run()
        return 0

    # Handle -i/--interactive (spawn pane or run inline)
    if args.interactive:
        from askfind.interactive.pane import spawn_interactive_pane
        if spawn_interactive_pane():
            return 0  # Pane was spawned, exit this process
        # Fallback: run inline
        from askfind.interactive.session import InteractiveSession
        session = InteractiveSession(config, Path(args.root))
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

    try:
        with LLMClient(base_url=config.base_url, api_key=api_key, model=model) as client:
            raw_response = client.extract_filters(args.query)
            filters = parse_llm_response(raw_response)
            root = Path(args.root).resolve()
            paths = list(walk_and_filter(root, filters, max_results=max_results))
            results = [FileResult.from_path(p) for p in paths]

            if not results:
                return 1

            # Optional LLM re-ranking for semantic relevance
            if not args.no_rerank and len(results) > 1:
                from askfind.search.reranker import rerank_results
                results = rerank_results(client, args.query, results)

            if args.json_output:
                print(format_json(results))
            elif args.verbose:
                print(format_verbose(results))
            else:
                print(format_plain(results))
            return 0
    except KeyboardInterrupt:
        print("\nSearch cancelled.", file=sys.stderr)
        return 130
    except FileNotFoundError as e:
        print(f"Error: Search root not found: {args.root}", file=sys.stderr)
        return 3
    except PermissionError as e:
        print(f"Error: Permission denied accessing search root", file=sys.stderr)
        return 3
    except Exception as e:
        import httpx
        import json as json_module

        # Provide sanitized error messages for common error types
        if isinstance(e, httpx.HTTPStatusError):
            print(f"Error: API request failed (HTTP {e.response.status_code})", file=sys.stderr)
            return 3
        elif isinstance(e, (httpx.ConnectError, httpx.TimeoutException)):
            print(f"Error: Cannot connect to API server. Check your network and base_url config.", file=sys.stderr)
            return 3
        elif isinstance(e, json_module.JSONDecodeError):
            print(f"Error: Invalid response from LLM API", file=sys.stderr)
            return 3
        else:
            # For unexpected errors, show type but not full details
            print(f"Error: {type(e).__name__}: {str(e)[:100]}", file=sys.stderr)
            return 3


if __name__ == "__main__":
    sys.exit(main())
