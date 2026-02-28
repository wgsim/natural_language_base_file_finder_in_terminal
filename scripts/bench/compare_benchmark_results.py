#!/usr/bin/env python3
"""Compare two benchmark outputs and flag regressions."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="Baseline benchmark file (.json or .csv)")
    parser.add_argument("--candidate", required=True, help="Candidate benchmark file (.json or .csv)")
    parser.add_argument(
        "--metric",
        default="median_s",
        choices=("min_s", "median_s", "mean_s", "max_s"),
        help="Metric field to compare (default: median_s)",
    )
    parser.add_argument(
        "--ratio-threshold",
        type=float,
        default=1.35,
        help="Fail when candidate metric > baseline metric * threshold (default: 1.35)",
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit JSON summary")
    args = parser.parse_args()
    if args.ratio_threshold < 1.0:
        parser.error("--ratio-threshold must be >= 1.0")
    return args


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("benchmark JSON payload must be an object")
    rows = payload.get("results")
    if not isinstance(rows, list):
        raise ValueError("benchmark JSON payload missing 'results' list")
    return rows


def _rows_by_scenario(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        scenario = row.get("scenario")
        if isinstance(scenario, str) and scenario:
            mapped[scenario] = row
    return mapped


def _to_float(value: Any, *, field: str, scenario: str, source: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"invalid numeric value for field '{field}' in scenario '{scenario}' ({source})"
        ) from exc


def main() -> int:
    args = _parse_args()
    baseline_path = Path(args.baseline).resolve()
    candidate_path = Path(args.candidate).resolve()
    baseline_rows = _rows_by_scenario(_load_rows(baseline_path))
    candidate_rows = _rows_by_scenario(_load_rows(candidate_path))

    shared = sorted(set(baseline_rows) & set(candidate_rows))
    if not shared:
        print("no shared scenarios between baseline and candidate", file=sys.stderr)
        return 2

    comparisons: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    for scenario in shared:
        baseline_value = _to_float(
            baseline_rows[scenario].get(args.metric),
            field=args.metric,
            scenario=scenario,
            source="baseline",
        )
        candidate_value = _to_float(
            candidate_rows[scenario].get(args.metric),
            field=args.metric,
            scenario=scenario,
            source="candidate",
        )
        ratio = float("inf") if baseline_value <= 0 else candidate_value / baseline_value
        row = {
            "scenario": scenario,
            "baseline": round(baseline_value, 6),
            "candidate": round(candidate_value, 6),
            "ratio": round(ratio, 6),
        }
        comparisons.append(row)
        if ratio > args.ratio_threshold:
            regressions.append(row)

    summary = {
        "baseline": str(baseline_path),
        "candidate": str(candidate_path),
        "metric": args.metric,
        "ratio_threshold": args.ratio_threshold,
        "comparisons": comparisons,
        "regressions": regressions,
    }

    if args.json_output:
        print(json.dumps(summary, indent=2))
    else:
        print(f"benchmark compare metric={args.metric} threshold={args.ratio_threshold:.3f}x")
        for row in comparisons:
            print(
                f"- {row['scenario']}: baseline={row['baseline']:.6f}s "
                f"candidate={row['candidate']:.6f}s ratio={row['ratio']:.3f}x"
            )

    if regressions:
        print("benchmark comparison failed: regressions detected", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
