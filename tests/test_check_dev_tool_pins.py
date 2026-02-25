"""Tests for scripts/ci/check_dev_tool_pins.py."""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "ci" / "check_dev_tool_pins.py"
)


def _load_module():
    module_name = f"check_dev_tool_pins_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


CHECK = _load_module()


def test_parse_spec_token_parses_pinned_spec():
    assert CHECK._parse_spec_token("ruff==0.6.9") == ("ruff", "==", "0.6.9")


def test_parse_spec_token_ignores_non_requirements():
    assert CHECK._parse_spec_token("-e") is None
    assert CHECK._parse_spec_token(".") is None
    assert CHECK._parse_spec_token("requirements.txt") is None


def test_extract_ci_pins_reads_install_line():
    ci_text = """
steps:
  - name: Install dependencies
    run: |
      python -m pip install -r requirements.txt
      python -m pip install -e . pytest==9.0.2 pytest-cov==7.0.0 ruff==0.6.9 pip-audit==2.10.0 mypy==1.11.2
"""
    pins = CHECK._extract_ci_pins(ci_text)
    assert pins["pytest"] == "==9.0.2"
    assert pins["pytest-cov"] == "==7.0.0"
    assert pins["mypy"] == "==1.11.2"
    assert pins["ruff"] == "==0.6.9"
    assert pins["pip-audit"] == "==2.10.0"


def test_validate_source_requires_exact_pins():
    errors = CHECK._validate_source(
        "ci.yml",
        {
            "pytest": "==9.0.2",
            "pytest-cov": "==7.0.0",
            "mypy": "==1.11.2",
            "ruff": ">=0.6",
            "pip-audit": "==2.10.0",
        },
    )
    assert any("must use exact pin" in err for err in errors)


def test_compare_sources_detects_mismatch():
    errors = CHECK._compare_sources(
        {
            "pytest": "==9.0.2",
            "pytest-cov": "==7.0.0",
            "mypy": "==1.11.2",
            "ruff": "==0.6.9",
            "pip-audit": "==2.10.0",
        },
        {
            "pytest": "==9.0.2",
            "pytest-cov": "==7.0.0",
            "mypy": "==1.11.2",
            "ruff": "==0.7.0",
            "pip-audit": "==2.10.0",
        },
        {
            "pytest": "==9.0.2",
            "pytest-cov": "==7.0.0",
            "mypy": "==1.11.2",
            "ruff": "==0.6.9",
            "pip-audit": "==2.10.0",
        },
    )
    assert any("version mismatch for ruff" in err for err in errors)
