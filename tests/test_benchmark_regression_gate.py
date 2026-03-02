"""Unit tests for scripts/ci/benchmark_regression_gate.py."""

from __future__ import annotations

import importlib.util
import sys
import types
import uuid
from argparse import Namespace
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "benchmark_regression_gate.py"


def _load_gate_module():
    module_name = f"benchmark_regression_gate_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


GATE = _load_gate_module()


def test_main_returns_success_when_parallel_within_threshold(monkeypatch, capsys):
    args = Namespace(
        root=".",
        scenario=["all-files"],
        repeats=5,
        max_results=0,
        ratio_threshold=1.25,
        follow_symlinks=False,
        include_binary=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda **_kwargs: args)
    monkeypatch.setattr(
        GATE,
        "_load_benchmark_module",
        lambda: types.SimpleNamespace(SCENARIOS={"all-files": object()}),
    )

    def fake_run_worker_median(*, scenario_name, traversal_workers, **_kwargs):
        if scenario_name == "all-files" and traversal_workers == 1:
            return (1.0, 50)
        if scenario_name == "all-files" and traversal_workers == 4:
            return (1.1, 50)
        raise AssertionError("unexpected benchmark call")

    monkeypatch.setattr(GATE, "_run_worker_median", fake_run_worker_median)

    assert GATE.main() == 0
    captured = capsys.readouterr()
    assert "performance regression gate summary:" in captured.out
    assert "performance regression gate passed" in captured.out
    assert captured.err == ""


def test_main_returns_failure_when_parallel_exceeds_threshold(monkeypatch, capsys):
    args = Namespace(
        root=".",
        scenario=["all-files"],
        repeats=5,
        max_results=0,
        ratio_threshold=1.1,
        follow_symlinks=False,
        include_binary=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda **_kwargs: args)
    monkeypatch.setattr(
        GATE,
        "_load_benchmark_module",
        lambda: types.SimpleNamespace(SCENARIOS={"all-files": object()}),
    )

    def fake_run_worker_median(*, scenario_name, traversal_workers, **_kwargs):
        if scenario_name == "all-files" and traversal_workers == 1:
            return (1.0, 50)
        if scenario_name == "all-files" and traversal_workers == 4:
            return (1.3, 50)
        raise AssertionError("unexpected benchmark call")

    monkeypatch.setattr(GATE, "_run_worker_median", fake_run_worker_median)

    assert GATE.main() == 1
    captured = capsys.readouterr()
    assert "performance regression gate summary:" in captured.out
    assert "performance regression gate failed" in captured.err


def test_main_returns_success_when_ratio_equals_threshold(monkeypatch, capsys):
    args = Namespace(
        root=".",
        scenario=["all-files"],
        repeats=5,
        max_results=0,
        ratio_threshold=1.3,
        follow_symlinks=False,
        include_binary=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda **_kwargs: args)
    monkeypatch.setattr(
        GATE,
        "_load_benchmark_module",
        lambda: types.SimpleNamespace(SCENARIOS={"all-files": object()}),
    )

    def fake_run_worker_median(*, scenario_name, traversal_workers, **_kwargs):
        if scenario_name == "all-files" and traversal_workers == 1:
            return (1.0, 50)
        if scenario_name == "all-files" and traversal_workers == 4:
            return (1.3, 50)
        raise AssertionError("unexpected benchmark call")

    monkeypatch.setattr(GATE, "_run_worker_median", fake_run_worker_median)

    assert GATE.main() == 0
    captured = capsys.readouterr()
    assert "performance regression gate passed" in captured.out
    assert captured.err == ""


def test_main_returns_failure_when_benchmark_median_is_non_finite(monkeypatch, capsys):
    args = Namespace(
        root=".",
        scenario=["all-files"],
        repeats=5,
        max_results=0,
        ratio_threshold=1.3,
        follow_symlinks=False,
        include_binary=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda **_kwargs: args)
    monkeypatch.setattr(
        GATE,
        "_load_benchmark_module",
        lambda: types.SimpleNamespace(SCENARIOS={"all-files": object()}),
    )

    def fake_run_worker_median(*, scenario_name, traversal_workers, **_kwargs):
        if scenario_name == "all-files" and traversal_workers == 1:
            return (float("nan"), 50)
        if scenario_name == "all-files" and traversal_workers == 4:
            return (1.0, 50)
        raise AssertionError("unexpected benchmark call")

    monkeypatch.setattr(GATE, "_run_worker_median", fake_run_worker_median)

    assert GATE.main() == 1
    captured = capsys.readouterr()
    assert "performance regression gate failed" in captured.err
    assert "invalid median values" in captured.err


@pytest.mark.parametrize(
    ("argv", "expected_message"),
    [
        (["--repeats", "0"], "--repeats must be >= 1"),
        (["--max-results", "-1"], "--max-results must be >= 0"),
        (["--ratio-threshold", "0.99"], "--ratio-threshold must be >= 1.0"),
        (["--ratio-threshold", "inf"], "--ratio-threshold must be finite"),
        (["--ratio-threshold", "nan"], "--ratio-threshold must be finite"),
    ],
)
def test_parse_args_validation_rejects_invalid_values(argv, expected_message, capsys):
    with pytest.raises(SystemExit) as excinfo:
        GATE._parse_args(scenario_choices=["all-files"], argv=argv)

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert expected_message in captured.err
