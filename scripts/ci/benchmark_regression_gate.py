#!/usr/bin/env python3
"""Fail CI when parallel traversal median regresses beyond an allowed ratio."""

from __future__ import annotations

import argparse
import importlib.util
import statistics
import sys
from pathlib import Path
from types import ModuleType
from typing import Sequence

DEFAULT_SCENARIOS = ("all-files", "python-files")
BASELINE_WORKERS = 1
PARALLEL_WORKERS = 4


def _load_benchmark_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / "bench" / "benchmark_walk.py"
    module_name = "askfind_benchmark_walk_gate"
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
        default=5,
        help="Runs per worker/scenario for median comparison (default: 5)",
    )
    parser.add_argument("--max-results", type=int, default=0, help="Max results per run (0 = no limit)")
    parser.add_argument(
        "--ratio-threshold",
        type=float,
        default=1.35,
        help="Fail when parallel median exceeds (baseline median * threshold). Default: 1.35",
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


def _run_worker_median(
    *,
    benchmark_module: ModuleType,
    root: Path,
    scenario_name: str,
    repeats: int,
    max_results: int,
    follow_symlinks: bool,
    include_binary: bool,
    traversal_workers: int,
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
            traversal_workers=traversal_workers,
        )
        durations.append(elapsed)
    return statistics.median(durations), result_count


def main() -> int:
    benchmark_module = _load_benchmark_module()
    scenario_choices = list(benchmark_module.SCENARIOS.keys())
    args = _parse_args(scenario_choices=scenario_choices)

    root = Path(args.root).resolve()
    selected_scenarios = _select_scenarios(requested=args.scenario, available=scenario_choices)
    regressions: list[str] = []

    print("performance regression gate summary:")
    print(f"root={root}")
    print(
        f"threshold={args.ratio_threshold:.3f}x "
        f"(workers={PARALLEL_WORKERS} vs workers={BASELINE_WORKERS})"
    )

    for scenario_name in selected_scenarios:
        baseline_median, baseline_count = _run_worker_median(
            benchmark_module=benchmark_module,
            root=root,
            scenario_name=scenario_name,
            repeats=args.repeats,
            max_results=args.max_results,
            follow_symlinks=args.follow_symlinks,
            include_binary=args.include_binary,
            traversal_workers=BASELINE_WORKERS,
        )
        parallel_median, parallel_count = _run_worker_median(
            benchmark_module=benchmark_module,
            root=root,
            scenario_name=scenario_name,
            repeats=args.repeats,
            max_results=args.max_results,
            follow_symlinks=args.follow_symlinks,
            include_binary=args.include_binary,
            traversal_workers=PARALLEL_WORKERS,
        )

        if baseline_median <= 0:
            ratio = float("inf")
        else:
            ratio = parallel_median / baseline_median

        print(
            f"- {scenario_name}: baseline_median={baseline_median:.6f}s "
            f"parallel_median={parallel_median:.6f}s ratio={ratio:.3f}x "
            f"results={baseline_count}/{parallel_count}"
        )
        if ratio > args.ratio_threshold:
            regressions.append(
                f"{scenario_name} ratio={ratio:.3f}x "
                f"(parallel={parallel_median:.6f}s baseline={baseline_median:.6f}s)"
            )

    if regressions:
        print("performance regression gate failed:", file=sys.stderr)
        for regression in regressions:
            print(f"- {regression}", file=sys.stderr)
        return 1

    print("performance regression gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
