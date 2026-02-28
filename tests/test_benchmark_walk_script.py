"""Tests for scripts/bench/benchmark_walk.py."""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from argparse import Namespace
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bench" / "benchmark_walk.py"


def _load_module():
    module_name = f"benchmark_walk_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


BENCH = _load_module()


def test_main_writes_json_and_csv_outputs(tmp_path):
    json_path = tmp_path / "bench" / "result.json"
    csv_path = tmp_path / "bench" / "result.csv"
    args = Namespace(
        root=str(tmp_path),
        scenario=["all-files"],
        repeats=2,
        max_results=0,
        workers=1,
        follow_symlinks=False,
        include_binary=False,
        json_output=False,
        output_json=str(json_path),
        output_csv=str(csv_path),
    )
    BENCH._parse_args = lambda: args  # type: ignore[method-assign]
    BENCH.SCENARIOS = {"all-files": BENCH.Scenario("all-files", object())}
    calls = {"count": 0}

    def fake_run_once(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return (0.2, 5)
        return (0.1, 5)

    BENCH._run_once = fake_run_once  # type: ignore[method-assign]

    assert BENCH.main() == 0
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["benchmark_version"] == 1
    assert payload["root"] == str(tmp_path.resolve())
    assert payload["parameters"]["workers"] == 1
    assert payload["results"][0]["scenario"] == "all-files"
    assert csv_path.is_file()
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "scenario,runs,min_s,median_s,mean_s,max_s,result_count" in csv_text
    assert "all-files,2,0.1,0.15,0.15,0.2,5" in csv_text


def test_main_json_stdout_uses_new_payload_format(tmp_path, capsys):
    args = Namespace(
        root=str(tmp_path),
        scenario=["all-files"],
        repeats=1,
        max_results=0,
        workers=1,
        follow_symlinks=False,
        include_binary=False,
        json_output=True,
        output_json=None,
        output_csv=None,
    )
    BENCH._parse_args = lambda: args  # type: ignore[method-assign]
    BENCH.SCENARIOS = {"all-files": BENCH.Scenario("all-files", object())}
    BENCH._run_once = lambda **_kwargs: (0.123, 2)  # type: ignore[method-assign]

    assert BENCH.main() == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["benchmark_version"] == 1
    assert payload["results"][0]["scenario"] == "all-files"
