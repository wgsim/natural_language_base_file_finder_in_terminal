# Remaining Issues (Current State)

Last validated: 2026-02-25

This file tracks issues that are still open after recent hardening work
(mypy in CI, coverage gate 95%, pip-audit severity gate, parser sanitization).

## Open Issues

- No active medium/high/low items in the current hardening scope.
- Remaining work is roadmap-level enhancement (see `docs/FUTURE_DEVELOPMENT.md`).

## Recently Resolved

- LLM parser value sanitization and bounds validation (`src/askfind/llm/parser.py`).
- Symlink and size guards for content reads (`src/askfind/search/filters.py`, `src/askfind/interactive/commands.py`).
- Explicit TLS verification in LLM client (`src/askfind/llm/client.py`).
- `get_api_key` env var semantics clarified (`src/askfind/config.py`).
- Security audit gate in CI (`scripts/ci/pip_audit_gate.py`, `.github/workflows/ci.yml`).
- Mypy check integrated into CI (`.github/workflows/ci.yml`, `pyproject.toml`).
- Coverage gate raised to 95% and passing in CI.
- Editor command failures now surface non-zero exit codes (`src/askfind/interactive/commands.py`).
- Lock file policy enforced in CI/hooks (`scripts/ci/check_dev_tool_pins.py`, `.gitignore`, `ENVIRONMENT.md`).
- Interactive result date now includes year (`src/askfind/interactive/session.py`).
- Broad exception handlers narrowed to explicit classes (`src/askfind/cli.py`, `src/askfind/interactive/session.py`).

## Priority Order

1. Continue with roadmap features in `docs/FUTURE_DEVELOPMENT.md` (performance/search UX/architecture).
