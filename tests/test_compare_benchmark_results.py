"""Tests for scripts/bench/compare_benchmark_results.py."""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from argparse import Namespace
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "bench" / "compare_benchmark_results.py"
)


def _load_module():
    module_name = f"compare_benchmark_results_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


COMPARE = _load_module()


def test_main_success_for_json_inputs(tmp_path, capsys):
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(
        json.dumps({"results": [{"scenario": "all-files", "median_s": 1.0}]}),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps({"results": [{"scenario": "all-files", "median_s": 1.2}]}),
        encoding="utf-8",
    )
    COMPARE._parse_args = lambda: Namespace(  # type: ignore[method-assign]
        baseline=str(baseline),
        candidate=str(candidate),
        metric="median_s",
        ratio_threshold=1.3,
        json_output=False,
    )

    assert COMPARE.main() == 0
    captured = capsys.readouterr()
    assert "benchmark compare metric=median_s threshold=1.300x" in captured.out
    assert "ratio=1.200x" in captured.out


def test_main_failure_when_regression_detected(tmp_path, capsys):
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(
        json.dumps({"results": [{"scenario": "all-files", "median_s": 1.0}]}),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps({"results": [{"scenario": "all-files", "median_s": 1.5}]}),
        encoding="utf-8",
    )
    COMPARE._parse_args = lambda: Namespace(  # type: ignore[method-assign]
        baseline=str(baseline),
        candidate=str(candidate),
        metric="median_s",
        ratio_threshold=1.3,
        json_output=True,
    )

    assert COMPARE.main() == 1
    captured = capsys.readouterr()
    assert "benchmark comparison failed: regressions detected" in captured.err
    payload = json.loads(captured.out)
    assert len(payload["regressions"]) == 1


def test_main_supports_csv_inputs(tmp_path):
    baseline = tmp_path / "baseline.csv"
    candidate = tmp_path / "candidate.csv"
    baseline.write_text(
        "scenario,runs,min_s,median_s,mean_s,max_s,result_count\nall-files,1,1.0,1.0,1.0,1.0,10\n",
        encoding="utf-8",
    )
    candidate.write_text(
        "scenario,runs,min_s,median_s,mean_s,max_s,result_count\nall-files,1,1.1,1.1,1.1,1.1,10\n",
        encoding="utf-8",
    )
    COMPARE._parse_args = lambda: Namespace(  # type: ignore[method-assign]
        baseline=str(baseline),
        candidate=str(candidate),
        metric="median_s",
        ratio_threshold=1.2,
        json_output=False,
    )

    assert COMPARE.main() == 0


def test_main_returns_2_when_no_shared_scenarios(tmp_path):
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(
        json.dumps({"results": [{"scenario": "all-files", "median_s": 1.0}]}),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps({"results": [{"scenario": "python-files", "median_s": 1.0}]}),
        encoding="utf-8",
    )
    COMPARE._parse_args = lambda: Namespace(  # type: ignore[method-assign]
        baseline=str(baseline),
        candidate=str(candidate),
        metric="median_s",
        ratio_threshold=1.2,
        json_output=False,
    )

    assert COMPARE.main() == 2
