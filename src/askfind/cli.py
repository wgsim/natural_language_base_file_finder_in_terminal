"""CLI entry point for askfind."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
    return parser


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
        setattr(config, args.key, args.value)
        config.save(get_config_path())
        print(f"Set {args.key} = {args.value}")
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
            for m in models:
                print(m.get("id", "unknown"))
        except Exception as e:
            print(f"Error fetching models: {e}", file=sys.stderr)
            return 3
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    # Check if first arg is "config" subcommand
    if argv and len(argv) > 0 and argv[0] == "config":
        config_parser = _build_config_parser()
        args = config_parser.parse_args(argv[1:])  # Skip "config" word
        return _handle_config(args)

    # Otherwise parse as search/interactive command
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.query and not args.interactive:
        parser.print_help()
        return 2

    config = Config.from_file(get_config_path())

    if args.interactive:
        # Will be implemented in Task 9
        print("Interactive mode not yet implemented.", file=sys.stderr)
        return 0

    # Single command mode
    api_key = get_api_key(cli_key=args.api_key)
    if not api_key:
        print("Error: No API key configured. Run `askfind config set-key`.", file=sys.stderr)
        return 2

    model = args.model or config.model
    max_results = args.max_results or config.max_results

    client = LLMClient(base_url=config.base_url, api_key=api_key, model=model)
    try:
        raw_response = client.extract_filters(args.query)
        filters = parse_llm_response(raw_response)
        root = Path(args.root).resolve()
        paths = list(walk_and_filter(root, filters, max_results=max_results))
        results = [FileResult.from_path(p) for p in paths]

        if not results:
            return 1

        if args.json_output:
            print(format_json(results))
        elif args.verbose:
            print(format_verbose(results))
        else:
            print(format_plain(results))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
