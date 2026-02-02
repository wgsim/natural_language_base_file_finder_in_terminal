"""CLI entry point for askfind."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from askfind.config import Config, get_api_key, get_config_path
from askfind.llm.client import LLMClient
from askfind.llm.parser import parse_llm_response
from askfind.output.formatter import FileResult, format_json, format_plain, format_verbose
from askfind.search.walker import walk_and_filter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="askfind",
        description="Find files using natural language queries.",
    )
    parser.add_argument("query", nargs="?", help="Natural language query")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive mode")
    parser.add_argument("-r", "--root", default=".", help="Search root directory")
    parser.add_argument("-m", "--max", type=int, default=0, dest="max_results", help="Max results (0=use config)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show file metadata")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    parser.add_argument("--model", help="Override LLM model")
    parser.add_argument("--api-key", help="One-off API key")
    parser.add_argument("--no-rerank", action="store_true", help="Skip semantic re-ranking")
    return parser


def main(argv: list[str] | None = None) -> int:
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
