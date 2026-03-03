"""Unit tests for scripts/ci/pip_audit_gate.py."""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from argparse import Namespace
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "pip_audit_gate.py"


def _load_gate_module():
    module_name = f"pip_audit_gate_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


GATE = _load_gate_module()


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        ("9.0", "critical"),
        ("7.0", "high"),
        ("4.0", "medium"),
        ("0.1", "low"),
        (" 7.5 ", "high"),
        ("0", "unknown"),
        ("-1", "unknown"),
        ("not-a-number", "unknown"),
    ],
)
def test_severity_from_score(score, expected):
    assert GATE._severity_from_score(score) == expected


def test_extract_record_severity_picks_highest_signal():
    record = {
        "database_specific": {"severity": " medium "},
        "ecosystem_specific": {"severity": "high"},
        "severity": [{"score": "9.8"}, {"score": "4.2"}],
    }

    assert GATE._extract_record_severity(record) == "critical"


def test_extract_record_severity_ignores_malformed_shapes():
    record = {
        "database_specific": {"severity": "not-real"},
        "ecosystem_specific": "critical",
        "severity": [None, {"score": 7.2}, {"score": "vector"}],
    }

    assert GATE._extract_record_severity(record) == "unknown"


def test_load_findings_uses_aliases_and_selects_best_severity(monkeypatch, tmp_path):
    report = {
        "dependencies": [
            {
                "name": "alpha",
                "version": "1.0.0",
                "vulns": [
                    {
                        "id": "PYSEC-1",
                        "aliases": ["CVE-2024-0001", "GHSA-zzzz-1111"],
                    }
                ],
            },
            {
                "name": "beta",
                "version": "2.0.0",
                "vulns": [{"id": "PYSEC-2"}],
            },
            {"name": "ignored", "version": "3.0.0", "vulns": "bad-shape"},
            "not-a-dict",
        ]
    }
    report_path = tmp_path / "pip-audit.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    records = {
        "PYSEC-1": {"database_specific": {"severity": "low"}},
        "CVE-2024-0001": {"database_specific": {"severity": "high"}},
        "GHSA-zzzz-1111": {"severity": [{"score": "9.8"}]},
    }
    calls = []

    def fake_fetch(vuln_id, timeout):
        calls.append((vuln_id, timeout))
        return records.get(vuln_id)

    monkeypatch.setattr(GATE, "_fetch_osv_record", fake_fetch)

    findings = GATE._load_findings(str(report_path), timeout=3.5)

    assert len(findings) == 2

    first = findings[0]
    assert first.package == "alpha"
    assert first.version == "1.0.0"
    assert first.vuln_id == "PYSEC-1"
    assert first.severity == "critical"
    assert first.source_id == "GHSA-zzzz-1111"
    assert first.severity_resolved is True

    second = findings[1]
    assert second.package == "beta"
    assert second.vuln_id == "PYSEC-2"
    assert second.severity == "unknown"
    assert second.source_id == "PYSEC-2"
    assert second.severity_resolved is False

    assert calls == [
        ("PYSEC-1", 3.5),
        ("CVE-2024-0001", 3.5),
        ("GHSA-zzzz-1111", 3.5),
        ("PYSEC-2", 3.5),
    ]


def test_load_findings_raises_for_invalid_report_shape(monkeypatch, tmp_path):
    report_path = tmp_path / "pip-audit.json"
    report_path.write_text(json.dumps({"dependencies": {}}), encoding="utf-8")

    def fail_fetch(*_args, **_kwargs):
        raise AssertionError("_fetch_osv_record should not be called")

    monkeypatch.setattr(GATE, "_fetch_osv_record", fail_fetch)

    with pytest.raises(GATE.GateInputError, match="'dependencies' must be a list"):
        GATE._load_findings(str(report_path), timeout=1.0)


def test_main_returns_failure_when_min_severity_is_met(monkeypatch, capsys):
    args = Namespace(
        input="ignored.json",
        min_severity="high",
        timeout=2.0,
        allow_unresolved_severity=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda: args)
    monkeypatch.setattr(
        GATE,
        "_load_findings",
        lambda *_args, **_kwargs: [
            GATE.Finding(
                package="alpha",
                version="1.0.0",
                vuln_id="CVE-2024-0001",
                severity="high",
                source_id="CVE-2024-0001",
            ),
            GATE.Finding(
                package="beta",
                version="2.0.0",
                vuln_id="CVE-2024-0002",
                severity="low",
                source_id="CVE-2024-0002",
            ),
        ],
    )

    assert GATE.main() == 1
    captured = capsys.readouterr()
    assert "pip-audit severity gate summary:" in captured.out
    assert "severity=high" in captured.out
    assert "pip-audit severity gate failed: found 1 high+ vulnerabilities" in captured.err


def test_main_returns_success_when_no_finding_reaches_threshold(monkeypatch, capsys):
    args = Namespace(
        input="ignored.json",
        min_severity="critical",
        timeout=2.0,
        allow_unresolved_severity=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda: args)
    monkeypatch.setattr(
        GATE,
        "_load_findings",
        lambda *_args, **_kwargs: [
            GATE.Finding(
                package="alpha",
                version="1.0.0",
                vuln_id="CVE-2024-0001",
                severity="high",
                source_id="CVE-2024-0001",
            )
        ],
    )

    assert GATE.main() == 0
    captured = capsys.readouterr()
    assert "pip-audit severity gate summary:" in captured.out
    assert "pip-audit severity gate passed: no critical+ vulnerabilities" in captured.out
    assert captured.err == ""


def test_main_returns_success_when_no_findings(monkeypatch, capsys):
    args = Namespace(
        input="ignored.json",
        min_severity="high",
        timeout=2.0,
        allow_unresolved_severity=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda: args)
    monkeypatch.setattr(GATE, "_load_findings", lambda *_args, **_kwargs: [])

    assert GATE.main() == 0
    captured = capsys.readouterr()
    assert "pip-audit severity gate: no vulnerabilities found" in captured.out
    assert captured.err == ""


def test_main_returns_failure_when_unresolved_and_fail_closed(monkeypatch, capsys):
    args = Namespace(
        input="ignored.json",
        min_severity="high",
        timeout=2.0,
        allow_unresolved_severity=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda: args)
    monkeypatch.setattr(
        GATE,
        "_load_findings",
        lambda *_args, **_kwargs: [
            GATE.Finding(
                package="alpha",
                version="1.0.0",
                vuln_id="PYSEC-1",
                severity="unknown",
                source_id="PYSEC-1",
                severity_resolved=False,
            )
        ],
    )

    assert GATE.main() == 1
    captured = capsys.readouterr()
    assert "pip-audit severity gate summary:" in captured.out
    assert "osv=unresolved" in captured.out
    assert "unresolved OSV severity for 1 vulnerabilities" in captured.err


def test_main_allows_unresolved_when_opt_out_flag_is_set(monkeypatch, capsys):
    args = Namespace(
        input="ignored.json",
        min_severity="high",
        timeout=2.0,
        allow_unresolved_severity=True,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda: args)
    monkeypatch.setattr(
        GATE,
        "_load_findings",
        lambda *_args, **_kwargs: [
            GATE.Finding(
                package="alpha",
                version="1.0.0",
                vuln_id="PYSEC-1",
                severity="unknown",
                source_id="PYSEC-1",
                severity_resolved=False,
            )
        ],
    )

    assert GATE.main() == 0
    captured = capsys.readouterr()
    assert "pip-audit severity gate summary:" in captured.out
    assert "pip-audit severity gate passed: no high+ vulnerabilities" in captured.out
    assert captured.err == ""


def test_main_returns_input_error_for_missing_report_file(monkeypatch, capsys, tmp_path):
    missing_path = tmp_path / "missing-pip-audit.json"
    args = Namespace(
        input=str(missing_path),
        min_severity="high",
        timeout=2.0,
        allow_unresolved_severity=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda: args)

    assert GATE.main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"input file not found: {missing_path}" in captured.err


def test_main_returns_input_error_for_invalid_json(monkeypatch, capsys, tmp_path):
    report_path = tmp_path / "pip-audit.json"
    report_path.write_text("{ not-json }", encoding="utf-8")
    args = Namespace(
        input=str(report_path),
        min_severity="high",
        timeout=2.0,
        allow_unresolved_severity=False,
    )
    monkeypatch.setattr(GATE, "_parse_args", lambda: args)

    assert GATE.main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "invalid JSON in input file" in captured.err
