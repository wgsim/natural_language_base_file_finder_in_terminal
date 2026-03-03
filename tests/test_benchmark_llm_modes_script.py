"""Tests for scripts/bench/benchmark_llm_modes.py."""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from argparse import Namespace
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "bench" / "benchmark_llm_modes.py"
)


def _load_module():
    module_name = f"benchmark_llm_modes_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BENCH = _load_module()


def test_parse_llm_mode_stats_extracts_fields():
    llm_called, reason = BENCH._parse_llm_mode_stats(
        "cache: disabled\nllm_mode: mode=auto decision=fallback llm_called=no reason=auto_simple_fallback\n"
    )
    assert llm_called is False
    assert reason == "auto_simple_fallback"


def test_main_writes_json_and_csv_outputs(tmp_path):
    json_path = tmp_path / "bench" / "result.json"
    csv_path = tmp_path / "bench" / "result.csv"
    args = Namespace(
        root=str(tmp_path),
        mode=["always"],
        query=["python files in src"],
        repeats=2,
        max_results=50,
        json_output=False,
        output_json=str(json_path),
        output_csv=str(csv_path),
        fail_on_error=False,
    )
    BENCH._parse_args = lambda: args  # type: ignore[method-assign]
    calls = {"count": 0}

    def fake_run_once(**kwargs):
        calls["count"] += 1
        assert kwargs["mode"] == "always"
        if calls["count"] == 1:
            return BENCH.RunOutcome("always", "python files in src", 0.12, 0, True, "forced_always")
        return BENCH.RunOutcome("always", "python files in src", 0.18, 0, True, "forced_always")

    BENCH._run_once = fake_run_once  # type: ignore[method-assign]

    assert BENCH.main() == 0
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["benchmark_version"] == 1
    assert payload["summary"][0]["mode"] == "always"
    assert payload["summary"][0]["llm_called_runs"] == 2

    csv_text = csv_path.read_text(encoding="utf-8")
    assert "mode,query,runs,successes,failures,llm_called_runs,llm_unknown_runs,median_s,mean_s,reasons" in csv_text
    assert "always,python files in src,2,2,0,2,0,0.15,0.15" in csv_text


def test_main_fail_on_error_returns_1(tmp_path):
    args = Namespace(
        root=str(tmp_path),
        mode=["always"],
        query=["find files"],
        repeats=1,
        max_results=50,
        json_output=False,
        output_json=None,
        output_csv=None,
        fail_on_error=True,
    )
    BENCH._parse_args = lambda: args  # type: ignore[method-assign]
    BENCH._run_once = lambda **_kwargs: BENCH.RunOutcome(  # type: ignore[method-assign]
        "always",
        "find files",
        0.05,
        2,
        None,
        None,
    )

    assert BENCH.main() == 1
