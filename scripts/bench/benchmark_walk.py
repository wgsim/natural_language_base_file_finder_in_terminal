#!/usr/bin/env python3
"""Simple traversal benchmark for askfind walker."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from askfind.search.filters import SearchFilters
from askfind.search.walker import walk_and_filter


@dataclass(frozen=True)
class Scenario:
    name: str
    filters: SearchFilters


SCENARIOS: dict[str, Scenario] = {
    "all-files": Scenario("all-files", SearchFilters(type="file")),
    "python-files": Scenario("python-files", SearchFilters(type="file", ext=[".py"])),
    "todo-content": Scenario("todo-content", SearchFilters(type="file", has=["TODO"])),
}


def _run_once(
    *,
    root: Path,
    scenario: Scenario,
    max_results: int,
    follow_symlinks: bool,
    exclude_binary_files: bool,
    traversal_workers: int,
) -> tuple[float, int]:
    start = time.perf_counter()
    results = list(
        walk_and_filter(
            root=root,
            filters=scenario.filters,
            max_results=max_results,
            follow_symlinks=follow_symlinks,
            exclude_binary_files=exclude_binary_files,
            traversal_workers=traversal_workers,
        )
    )
    elapsed = time.perf_counter() - start
    return elapsed, len(results)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark askfind filesystem traversal.")
    parser.add_argument("--root", default=".", help="Search root path (default: current directory)")
    parser.add_argument(
        "--scenario",
        action="append",
        choices=sorted(SCENARIOS.keys()),
        help="Scenario(s) to run; repeat flag for multiple. Defaults to all scenarios.",
    )
    parser.add_argument("--repeats", type=int, default=5, help="Runs per scenario (default: 5)")
    parser.add_argument("--max-results", type=int, default=0, help="Max results per run (0 = no limit)")
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Traversal workers (default: 4, set 1 for sequential baseline)",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="Follow symlinks within root during traversal",
    )
    parser.add_argument(
        "--include-binary",
        action="store_true",
        help="Include binary files (default excludes binary files)",
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit JSON output")
    parser.add_argument(
        "--output-json",
        default=None,
        help="Write benchmark result payload JSON to file",
    )
    parser.add_argument(
        "--output-csv",
        default=None,
        help="Write benchmark result rows CSV to file",
    )
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be >= 1")
    if args.workers < 1:
        parser.error("--workers must be >= 1")
    return args


def _build_payload(*, root: Path, args: argparse.Namespace, rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "benchmark_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": str(root),
        "parameters": {
            "repeats": args.repeats,
            "max_results": args.max_results,
            "workers": args.workers,
            "follow_symlinks": args.follow_symlinks,
            "include_binary": args.include_binary,
        },
        "results": rows,
    }


def _write_json_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_csv_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scenario",
                "runs",
                "min_s",
                "median_s",
                "mean_s",
                "max_s",
                "result_count",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    selected = args.scenario or list(SCENARIOS.keys())
    rows: list[dict[str, object]] = []

    for name in selected:
        scenario = SCENARIOS[name]
        durations: list[float] = []
        result_counts: list[int] = []
        for _ in range(args.repeats):
            elapsed, count = _run_once(
                root=root,
                scenario=scenario,
                max_results=args.max_results,
                follow_symlinks=args.follow_symlinks,
                exclude_binary_files=not args.include_binary,
                traversal_workers=args.workers,
            )
            durations.append(elapsed)
            result_counts.append(count)

        row = {
            "scenario": name,
            "runs": args.repeats,
            "min_s": round(min(durations), 6),
            "median_s": round(statistics.median(durations), 6),
            "mean_s": round(statistics.mean(durations), 6),
            "max_s": round(max(durations), 6),
            "result_count": result_counts[-1],
        }
        rows.append(row)

    payload = _build_payload(root=root, args=args, rows=rows)
    if args.output_json:
        _write_json_payload(Path(args.output_json), payload)
    if args.output_csv:
        _write_csv_rows(Path(args.output_csv), rows)

    if args.json_output:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Benchmark root: {root}")
    for row in rows:
        print(
            f"[{row['scenario']}] runs={row['runs']} results={row['result_count']} "
            f"min={row['min_s']:.6f}s median={row['median_s']:.6f}s "
            f"mean={row['mean_s']:.6f}s max={row['max_s']:.6f}s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
