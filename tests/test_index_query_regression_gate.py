"""Unit tests for scripts/ci/index_query_regression_gate.py."""

from __future__ import annotations

import importlib.util
import sys
import types
import uuid
from argparse import Namespace
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "index_query_regression_gate.py"


def _load_gate_module():
    module_name = f"index_query_regression_gate_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


GATE = _load_gate_module()


def test_main_returns_success_when_index_query_within_threshold(monkeypatch, capsys):
    args = Namespace(
        root=".",
        scenario=["all-files"],
        repeats=3,
        max_results=0,
        index_dir=None,
        ratio_threshold=1.5,
        no_ignore=False,
        follow_symlinks=False,
        include_binary=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda **_kwargs: args)
    monkeypatch.setattr(
        GATE,
        "_load_benchmark_module",
        lambda: types.SimpleNamespace(
            SCENARIOS={"all-files": types.SimpleNamespace(filters=object())},
        ),
    )
    monkeypatch.setattr(GATE, "build_index", lambda **_kwargs: types.SimpleNamespace(file_count=10))
    monkeypatch.setattr(GATE, "_run_walk_median", lambda **_kwargs: (1.0, 25))
    monkeypatch.setattr(GATE, "_run_index_query_median", lambda **_kwargs: (1.1, 25))

    assert GATE.main() == 0
    captured = capsys.readouterr()
    assert "index query regression gate summary:" in captured.out
    assert "index query regression gate passed" in captured.out
    assert captured.err == ""


def test_main_returns_failure_when_index_query_exceeds_threshold(monkeypatch, capsys):
    args = Namespace(
        root=".",
        scenario=["all-files"],
        repeats=3,
        max_results=0,
        index_dir=None,
        ratio_threshold=1.2,
        no_ignore=False,
        follow_symlinks=False,
        include_binary=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda **_kwargs: args)
    monkeypatch.setattr(
        GATE,
        "_load_benchmark_module",
        lambda: types.SimpleNamespace(
            SCENARIOS={"all-files": types.SimpleNamespace(filters=object())},
        ),
    )
    monkeypatch.setattr(GATE, "build_index", lambda **_kwargs: types.SimpleNamespace(file_count=10))
    monkeypatch.setattr(GATE, "_run_walk_median", lambda **_kwargs: (1.0, 25))
    monkeypatch.setattr(GATE, "_run_index_query_median", lambda **_kwargs: (1.4, 25))

    assert GATE.main() == 1
    captured = capsys.readouterr()
    assert "index query regression gate failed" in captured.err


def test_main_returns_failure_when_result_counts_mismatch(monkeypatch, capsys):
    args = Namespace(
        root=".",
        scenario=["all-files"],
        repeats=3,
        max_results=0,
        index_dir=None,
        ratio_threshold=2.0,
        no_ignore=False,
        follow_symlinks=False,
        include_binary=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda **_kwargs: args)
    monkeypatch.setattr(
        GATE,
        "_load_benchmark_module",
        lambda: types.SimpleNamespace(
            SCENARIOS={"all-files": types.SimpleNamespace(filters=object())},
        ),
    )
    monkeypatch.setattr(GATE, "build_index", lambda **_kwargs: types.SimpleNamespace(file_count=10))
    monkeypatch.setattr(GATE, "_run_walk_median", lambda **_kwargs: (1.0, 25))
    monkeypatch.setattr(GATE, "_run_index_query_median", lambda **_kwargs: (1.0, 24))

    assert GATE.main() == 1
    captured = capsys.readouterr()
    assert "result mismatch" in captured.err


def test_main_returns_failure_when_index_build_fails(monkeypatch, capsys):
    args = Namespace(
        root="missing",
        scenario=["all-files"],
        repeats=3,
        max_results=0,
        index_dir=None,
        ratio_threshold=2.0,
        no_ignore=False,
        follow_symlinks=False,
        include_binary=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda **_kwargs: args)
    monkeypatch.setattr(
        GATE,
        "_load_benchmark_module",
        lambda: types.SimpleNamespace(
            SCENARIOS={"all-files": types.SimpleNamespace(filters=object())},
        ),
    )
    monkeypatch.setattr(GATE, "build_index", lambda **_kwargs: (_ for _ in ()).throw(FileNotFoundError("missing")))

    assert GATE.main() == 1
    captured = capsys.readouterr()
    assert "unable to build index" in captured.err


def test_main_applies_index_dir_override(monkeypatch, tmp_path):
    args = Namespace(
        root=".",
        scenario=["all-files"],
        repeats=1,
        max_results=0,
        index_dir=str(tmp_path / "custom-index"),
        ratio_threshold=2.0,
        no_ignore=False,
        follow_symlinks=False,
        include_binary=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda **_kwargs: args)
    monkeypatch.setattr(
        GATE,
        "_load_benchmark_module",
        lambda: types.SimpleNamespace(
            SCENARIOS={"all-files": types.SimpleNamespace(filters=object())},
        ),
    )

    seen: dict[str, Path] = {}

    def fake_build_index(**_kwargs):
        seen["index_dir"] = GATE.index_module.INDEX_DIR
        return types.SimpleNamespace(file_count=10)

    monkeypatch.setattr(GATE, "build_index", fake_build_index)
    monkeypatch.setattr(GATE, "_run_walk_median", lambda **_kwargs: (1.0, 10))
    monkeypatch.setattr(GATE, "_run_index_query_median", lambda **_kwargs: (1.0, 10))

    assert GATE.main() == 0
    assert seen["index_dir"] == (tmp_path / "custom-index").resolve()


def test_main_rejects_index_dir_within_root(monkeypatch, tmp_path, capsys):
    root = tmp_path / "repo"
    root.mkdir()
    args = Namespace(
        root=str(root),
        scenario=["all-files"],
        repeats=1,
        max_results=0,
        index_dir=str(root / ".tmp" / "indexes"),
        ratio_threshold=2.0,
        no_ignore=False,
        follow_symlinks=False,
        include_binary=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda **_kwargs: args)
    monkeypatch.setattr(
        GATE,
        "_load_benchmark_module",
        lambda: types.SimpleNamespace(
            SCENARIOS={"all-files": types.SimpleNamespace(filters=object())},
        ),
    )

    assert GATE.main() == 2
    captured = capsys.readouterr()
    assert "--index-dir must be outside --root" in captured.err


@pytest.mark.parametrize(
    ("argv", "expected_message"),
    [
        (["--repeats", "0"], "--repeats must be >= 1"),
        (["--max-results", "-1"], "--max-results must be >= 0"),
        (["--ratio-threshold", "0.99"], "--ratio-threshold must be >= 1.0"),
    ],
)
def test_parse_args_validation_rejects_invalid_values(argv, expected_message, capsys):
    with pytest.raises(SystemExit) as excinfo:
        GATE._parse_args(scenario_choices=["all-files"], argv=argv)

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert expected_message in captured.err


def test_select_scenarios_prefers_default_pairs_when_available():
    selected = GATE._select_scenarios(
        requested=None,
        available=["todo-content", "python-files", "all-files"],
    )
    assert selected == ["all-files", "python-files"]
