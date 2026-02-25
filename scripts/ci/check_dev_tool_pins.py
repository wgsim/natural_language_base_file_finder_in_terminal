#!/usr/bin/env python3
"""Ensure dev tool pins stay aligned across CI, env, and pyproject."""

from __future__ import annotations

import re
import shlex
import sys
import tomllib
from pathlib import Path

TOOLS = ("pytest", "pytest-cov", "mypy", "ruff", "pip-audit")
ROOT = Path(__file__).resolve().parents[2]
CI_FILE = ROOT / ".github" / "workflows" / "ci.yml"
ENV_FILE = ROOT / "environment.yml"
PYPROJECT_FILE = ROOT / "pyproject.toml"


def _parse_spec_token(token: str) -> tuple[str, str, str] | None:
    token = token.strip()
    if not token:
        return None
    if token.startswith("-"):
        return None
    if token in (".",):
        return None

    match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)\s*([<>=!~]{1,2})\s*([^\s;]+)$", token)
    if match is None:
        return None
    return match.group(1), match.group(2), match.group(3)


def _extract_ci_pins(text: str) -> dict[str, str]:
    pins: dict[str, str] = {}
    install_lines = [
        line.strip()
        for line in text.splitlines()
        if "python -m pip install " in line and "-e ." in line
    ]
    for line in install_lines:
        _, install_args = line.split("python -m pip install ", 1)
        for token in shlex.split(install_args):
            parsed = _parse_spec_token(token)
            if parsed is None:
                continue
            name, operator, version = parsed
            if name in TOOLS:
                pins[name] = f"{operator}{version}"
    return pins


def _extract_environment_pins(text: str) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in text.splitlines():
        parsed = _parse_spec_token(line.replace("- ", "", 1).strip())
        if parsed is None:
            continue
        name, operator, version = parsed
        if name in TOOLS:
            pins[name] = f"{operator}{version}"
    return pins


def _extract_pyproject_pins(data: dict[str, object]) -> dict[str, str]:
    project = data.get("project")
    if not isinstance(project, dict):
        return {}
    optional_deps = project.get("optional-dependencies")
    if not isinstance(optional_deps, dict):
        return {}
    dev_deps = optional_deps.get("dev")
    if not isinstance(dev_deps, list):
        return {}

    pins: dict[str, str] = {}
    for item in dev_deps:
        if not isinstance(item, str):
            continue
        parsed = _parse_spec_token(item)
        if parsed is None:
            continue
        name, operator, version = parsed
        if name in TOOLS:
            pins[name] = f"{operator}{version}"
    return pins


def _validate_source(name: str, pins: dict[str, str]) -> list[str]:
    errors: list[str] = []
    missing = [tool for tool in TOOLS if tool not in pins]
    if missing:
        errors.append(f"{name}: missing pins for {', '.join(missing)}")
    for tool, spec in pins.items():
        if not spec.startswith("=="):
            errors.append(f"{name}: {tool} must use exact pin (found {spec})")
    return errors


def _compare_sources(
    env_pins: dict[str, str],
    ci_pins: dict[str, str],
    pyproject_pins: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    for tool in TOOLS:
        env_spec = env_pins.get(tool)
        ci_spec = ci_pins.get(tool)
        pyproject_spec = pyproject_pins.get(tool)
        if env_spec != ci_spec:
            errors.append(
                f"version mismatch for {tool}: environment.yml={env_spec}, ci.yml={ci_spec}"
            )
        if env_spec != pyproject_spec:
            errors.append(
                f"version mismatch for {tool}: environment.yml={env_spec}, pyproject.toml={pyproject_spec}"
            )
    return errors


def main() -> int:
    ci_text = CI_FILE.read_text(encoding="utf-8")
    env_text = ENV_FILE.read_text(encoding="utf-8")
    pyproject_data = tomllib.loads(PYPROJECT_FILE.read_text(encoding="utf-8"))

    ci_pins = _extract_ci_pins(ci_text)
    env_pins = _extract_environment_pins(env_text)
    pyproject_pins = _extract_pyproject_pins(pyproject_data)

    errors = []
    errors.extend(_validate_source("ci.yml", ci_pins))
    errors.extend(_validate_source("environment.yml", env_pins))
    errors.extend(_validate_source("pyproject.toml", pyproject_pins))
    errors.extend(_compare_sources(env_pins, ci_pins, pyproject_pins))

    if errors:
        print("dev tool pin check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("dev tool pin check passed:")
    for tool in TOOLS:
        print(f"- {tool}{env_pins[tool]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
