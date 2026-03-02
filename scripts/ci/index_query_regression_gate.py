#!/usr/bin/env python3
"""Fail CI when index-query median regresses beyond an allowed ratio."""

from __future__ import annotations

import argparse
import importlib.util
import statistics
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Sequence

from askfind.search import index as index_module
from askfind.search.index import IndexOptions, build_index, query_index

DEFAULT_SCENARIOS = ("all-files", "python-files")
INDEX_QUERY_WORKERS = 4


def _load_benchmark_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / "bench" / "benchmark_walk.py"
    module_name = "askfind_benchmark_walk_index_gate"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load benchmark module from: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _parse_args(*, scenario_choices: Sequence[str], argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Search root path (default: current directory)")
    parser.add_argument(
        "--scenario",
        action="append",
        choices=sorted(scenario_choices),
        help=(
            "Scenario(s) to run; repeat flag for multiple. "
            "Defaults to conservative CI set: all-files + python-files when available."
        ),
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Runs per scenario for median comparison (default: 3)",
    )
    parser.add_argument("--max-results", type=int, default=0, help="Max results per run (0 = no limit)")
    parser.add_argument(
        "--index-dir",
        help="Override index cache directory for this gate run (default uses askfind cache path)",
    )
    parser.add_argument(
        "--ratio-threshold",
        type=float,
        default=2.0,
        help="Fail when index-query median exceeds (walk median * threshold). Default: 2.0",
    )
    parser.add_argument(
        "--no-ignore",
        action="store_true",
        help="Ignore .gitignore/.askfindignore rules during traversal and index build",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="Follow symlinks within root during traversal and index query",
    )
    parser.add_argument(
        "--include-binary",
        action="store_true",
        help="Include binary files (default excludes binary files)",
    )
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats must be >= 1")
    if args.max_results < 0:
        parser.error("--max-results must be >= 0")
    if args.ratio_threshold < 1.0:
        parser.error("--ratio-threshold must be >= 1.0")
    return args


def _select_scenarios(*, requested: list[str] | None, available: Sequence[str]) -> list[str]:
    if requested:
        return requested

    conservative_default = [name for name in DEFAULT_SCENARIOS if name in available]
    if conservative_default:
        return conservative_default

    return sorted(available)


def _format_pct_change(*, baseline: int, candidate: int) -> str:
    if baseline <= 0:
        return "n/a"
    return f"{(abs(candidate - baseline) / baseline) * 100:.3f}%"


def _format_result_parity(*, walk_count: int, index_count: int) -> str:
    if walk_count == index_count:
        return "parity=match"

    delta = index_count - walk_count
    direction = "index>walk" if delta > 0 else "walk>index"
    pct_change = _format_pct_change(baseline=walk_count, candidate=index_count)
    return f"parity=mismatch delta={delta:+d} ({direction}, pct_change={pct_change})"


def _format_result_mismatch(*, scenario_name: str, walk_count: int, index_count: int) -> str:
    delta = index_count - walk_count
    direction = "index>walk" if delta > 0 else "walk>index"
    pct_change = _format_pct_change(baseline=walk_count, candidate=index_count)
    return (
        f"{scenario_name} result mismatch: walk={walk_count} index={index_count} "
        f"delta={delta:+d} ({direction}, pct_change={pct_change})"
    )


def _format_ratio_regression(
    *,
    scenario_name: str,
    ratio: float,
    ratio_threshold: float,
    index_median: float,
    walk_median: float,
) -> str:
    return (
        f"{scenario_name} ratio={ratio:.3f}x "
        f"(threshold={ratio_threshold:.3f}x over_by={ratio - ratio_threshold:.3f}x "
        f"index={index_median:.6f}s walk={walk_median:.6f}s)"
    )


def _run_walk_median(
    *,
    benchmark_module: ModuleType,
    root: Path,
    scenario_name: str,
    repeats: int,
    max_results: int,
    follow_symlinks: bool,
    include_binary: bool,
) -> tuple[float, int]:
    scenario = benchmark_module.SCENARIOS[scenario_name]
    durations: list[float] = []
    result_count = 0
    for _ in range(repeats):
        elapsed, result_count = benchmark_module._run_once(
            root=root,
            scenario=scenario,
            max_results=max_results,
            follow_symlinks=follow_symlinks,
            exclude_binary_files=not include_binary,
            traversal_workers=INDEX_QUERY_WORKERS,
        )
        durations.append(elapsed)
    return statistics.median(durations), result_count


def _run_index_query_median(
    *,
    benchmark_module: ModuleType,
    root: Path,
    scenario_name: str,
    repeats: int,
    max_results: int,
    options: IndexOptions,
) -> tuple[float, int]:
    scenario = benchmark_module.SCENARIOS[scenario_name]
    durations: list[float] = []
    result_count = 0
    for _ in range(repeats):
        start = time.perf_counter()
        matches = query_index(
            root=root,
            filters=scenario.filters,
            max_results=max_results,
            options=options,
        )
        elapsed = time.perf_counter() - start
        if matches is None:
            raise RuntimeError(f"index query unavailable for scenario: {scenario_name}")
        durations.append(elapsed)
        result_count = len(matches)
    return statistics.median(durations), result_count


def main() -> int:
    benchmark_module = _load_benchmark_module()
    scenario_choices = list(benchmark_module.SCENARIOS.keys())
    args = _parse_args(scenario_choices=scenario_choices)

    root = Path(args.root).resolve()
    selected_scenarios = _select_scenarios(requested=args.scenario, available=scenario_choices)
    if args.index_dir:
        index_dir = Path(args.index_dir).resolve()
        if index_dir == root or root in index_dir.parents:
            print("index query regression gate failed: --index-dir must be outside --root", file=sys.stderr)
            return 2
        index_module.INDEX_DIR = index_dir

    options = IndexOptions(
        respect_ignore_files=not args.no_ignore,
        follow_symlinks=args.follow_symlinks,
        exclude_binary_files=not args.include_binary,
        search_archives=False,
        traversal_workers=INDEX_QUERY_WORKERS,
    )

    try:
        build_result = build_index(root=root, options=options)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        print(f"index query regression gate failed: unable to build index ({exc})", file=sys.stderr)
        return 1

    regressions: list[str] = []
    print("index query regression gate summary:")
    print(f"root={root}")
    print(f"index_files={build_result.file_count}")
    print(f"threshold={args.ratio_threshold:.3f}x (index-query vs walk workers={INDEX_QUERY_WORKERS})")

    for scenario_name in selected_scenarios:
        walk_median, walk_count = _run_walk_median(
            benchmark_module=benchmark_module,
            root=root,
            scenario_name=scenario_name,
            repeats=args.repeats,
            max_results=args.max_results,
            follow_symlinks=args.follow_symlinks,
            include_binary=args.include_binary,
        )
        try:
            index_median, index_count = _run_index_query_median(
                benchmark_module=benchmark_module,
                root=root,
                scenario_name=scenario_name,
                repeats=args.repeats,
                max_results=args.max_results,
                options=options,
            )
        except RuntimeError as exc:
            regressions.append(str(exc))
            continue

        ratio = float("inf") if walk_median <= 0 else index_median / walk_median
        parity = _format_result_parity(walk_count=walk_count, index_count=index_count)

        print(
            f"- {scenario_name}: walk_median={walk_median:.6f}s "
            f"index_median={index_median:.6f}s ratio={ratio:.3f}x "
            f"results={walk_count}/{index_count} {parity}"
        )

        if walk_count != index_count:
            regressions.append(
                _format_result_mismatch(
                    scenario_name=scenario_name,
                    walk_count=walk_count,
                    index_count=index_count,
                )
            )
        if ratio > args.ratio_threshold:
            regressions.append(
                _format_ratio_regression(
                    scenario_name=scenario_name,
                    ratio=ratio,
                    ratio_threshold=args.ratio_threshold,
                    index_median=index_median,
                    walk_median=walk_median,
                )
            )

    if regressions:
        print("index query regression gate failed:", file=sys.stderr)
        for regression in regressions:
            print(f"- {regression}", file=sys.stderr)
        return 1

    print("index query regression gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
