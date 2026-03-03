#!/usr/bin/env python3
"""Benchmark askfind LLM routing modes across a query set."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import statistics
import time
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from askfind.cli import main as askfind_main


DEFAULT_MODES = ("always", "auto", "off")
DEFAULT_QUERIES = (
    "python files in src",
    "files related to authentication",
)
_LLM_MODE_STATS_PATTERN = re.compile(
    r"llm_mode:\s+mode=(?P<mode>\w+)\s+decision=(?P<decision>\w+)\s+llm_called=(?P<llm_called>yes|no)\s+reason=(?P<reason>[A-Za-z0-9_]+)"
)


@dataclass(frozen=True)
class RunOutcome:
    mode: str
    query: str
    elapsed_s: float
    exit_code: int
    llm_called: bool | None
    llm_reason: str | None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Search root path (default: current directory)")
    parser.add_argument(
        "--mode",
        action="append",
        choices=sorted(DEFAULT_MODES),
        help="LLM mode(s) to benchmark; repeat flag for multiple. Defaults to always+auto+off.",
    )
    parser.add_argument(
        "--query",
        action="append",
        help="Query to benchmark; repeat flag for multiple. Defaults to built-in simple+ambiguous queries.",
    )
    parser.add_argument("--repeats", type=int, default=3, help="Runs per mode/query pair (default: 3)")
    parser.add_argument("--max-results", type=int, default=50, help="Max results passed to askfind")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit JSON payload to stdout")
    parser.add_argument("--output-json", default=None, help="Write JSON payload to file")
    parser.add_argument("--output-csv", default=None, help="Write summary CSV to file")
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Return non-zero when any benchmarked run exits non-zero",
    )
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be >= 1")
    if args.max_results < 1:
        parser.error("--max-results must be >= 1")
    return args


def _parse_llm_mode_stats(stderr_output: str) -> tuple[bool | None, str | None]:
    last_match: re.Match[str] | None = None
    for line in stderr_output.splitlines():
        candidate = _LLM_MODE_STATS_PATTERN.search(line)
        if candidate is not None:
            last_match = candidate
    if last_match is None:
        return None, None
    llm_called = last_match.group("llm_called") == "yes"
    reason = last_match.group("reason")
    return llm_called, reason


def _run_once(
    *,
    root: Path,
    query: str,
    mode: str,
    max_results: int,
) -> RunOutcome:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    argv = [
        query,
        "--root",
        str(root),
        "--llm-mode",
        mode,
        "--max",
        str(max_results),
        "--no-cache",
        "--no-rerank",
        "--cache-stats",
    ]
    start = time.perf_counter()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = askfind_main(argv)
    elapsed_s = time.perf_counter() - start
    llm_called, llm_reason = _parse_llm_mode_stats(stderr_buffer.getvalue())
    return RunOutcome(
        mode=mode,
        query=query,
        elapsed_s=elapsed_s,
        exit_code=exit_code,
        llm_called=llm_called,
        llm_reason=llm_reason,
    )


def _build_summary_rows(outcomes: list[RunOutcome]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[RunOutcome]] = {}
    for outcome in outcomes:
        key = (outcome.mode, outcome.query)
        grouped.setdefault(key, []).append(outcome)

    rows: list[dict[str, object]] = []
    for mode, query in sorted(grouped):
        group = grouped[(mode, query)]
        durations = [run.elapsed_s for run in group]
        success_runs = [run for run in group if run.exit_code == 0]
        reason_counts: dict[str, int] = {}
        for run in group:
            if run.llm_reason:
                reason_counts[run.llm_reason] = reason_counts.get(run.llm_reason, 0) + 1
        row = {
            "mode": mode,
            "query": query,
            "runs": len(group),
            "successes": len(success_runs),
            "failures": len(group) - len(success_runs),
            "llm_called_runs": sum(1 for run in group if run.llm_called is True),
            "llm_unknown_runs": sum(1 for run in group if run.llm_called is None),
            "median_s": round(statistics.median(durations), 6),
            "mean_s": round(statistics.mean(durations), 6),
            "reasons": reason_counts,
        }
        rows.append(row)
    return rows


def _build_payload(
    *,
    root: Path,
    args: argparse.Namespace,
    outcomes: list[RunOutcome],
    summary_rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "benchmark_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": str(root),
        "parameters": {
            "modes": args.mode or list(DEFAULT_MODES),
            "queries": args.query or list(DEFAULT_QUERIES),
            "repeats": args.repeats,
            "max_results": args.max_results,
            "fail_on_error": args.fail_on_error,
        },
        "summary": summary_rows,
        "runs": [
            {
                "mode": run.mode,
                "query": run.query,
                "elapsed_s": round(run.elapsed_s, 6),
                "exit_code": run.exit_code,
                "llm_called": run.llm_called,
                "reason": run.llm_reason,
            }
            for run in outcomes
        ],
    }


def _write_json_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_csv_summary(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "mode",
                "query",
                "runs",
                "successes",
                "failures",
                "llm_called_runs",
                "llm_unknown_runs",
                "median_s",
                "mean_s",
                "reasons",
            ],
        )
        writer.writeheader()
        for row in rows:
            serialized = dict(row)
            serialized["reasons"] = json.dumps(row.get("reasons", {}), sort_keys=True)
            writer.writerow(serialized)


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    modes = args.mode or list(DEFAULT_MODES)
    queries = args.query or list(DEFAULT_QUERIES)

    outcomes: list[RunOutcome] = []
    for mode in modes:
        for query in queries:
            for _ in range(args.repeats):
                outcomes.append(
                    _run_once(
                        root=root,
                        query=query,
                        mode=mode,
                        max_results=args.max_results,
                    )
                )

    summary_rows = _build_summary_rows(outcomes)
    payload = _build_payload(root=root, args=args, outcomes=outcomes, summary_rows=summary_rows)

    if args.output_json:
        _write_json_payload(Path(args.output_json), payload)
    if args.output_csv:
        _write_csv_summary(Path(args.output_csv), summary_rows)

    if args.json_output:
        print(json.dumps(payload, indent=2))
    else:
        print(f"LLM mode benchmark root: {root}")
        for row in summary_rows:
            print(
                f"[{row['mode']}] query={row['query']!r} runs={row['runs']} "
                f"ok={row['successes']} fail={row['failures']} "
                f"llm_called={row['llm_called_runs']} "
                f"median={row['median_s']:.6f}s mean={row['mean_s']:.6f}s"
            )

    if args.fail_on_error and any(outcome.exit_code != 0 for outcome in outcomes):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
