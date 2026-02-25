# Remaining Issues (Current State)

Last validated: 2026-02-25

This file tracks issues that are still open after recent hardening work
(mypy in CI, coverage gate 95%, pip-audit severity gate, parser sanitization).

## Open Issues

### Medium

1. Reproducibility lock artifacts are documented but not tracked
- Files: `ENVIRONMENT.md`, `environment.yml`
- Current behavior: lock generation instructions exist, but `environment.lock.yml` / `environment.lock.txt` are not committed.
- Impact: environment recreation is pinned but not fully frozen.
- Next fix: generate and commit lock artifacts (or define explicit policy to ignore them).

### Low

1. Interactive result table date format omits year
- File: `src/askfind/interactive/session.py`
- Current behavior: `%b %d` in table output.
- Impact: ambiguous dates across years.
- Next fix: align with formatter output (`%b %d %Y` or ISO date).

2. Broad exception handling remains in a few paths
- Files: `src/askfind/cli.py`, `src/askfind/interactive/session.py`
- Current behavior: broad `except Exception` still used as safety net.
- Impact: debugging granularity is reduced.
- Next fix: narrow exception types where practical while keeping UX-safe fallback.

## Recently Resolved

- LLM parser value sanitization and bounds validation (`src/askfind/llm/parser.py`).
- Symlink and size guards for content reads (`src/askfind/search/filters.py`, `src/askfind/interactive/commands.py`).
- Explicit TLS verification in LLM client (`src/askfind/llm/client.py`).
- `get_api_key` env var semantics clarified (`src/askfind/config.py`).
- Security audit gate in CI (`scripts/ci/pip_audit_gate.py`, `.github/workflows/ci.yml`).
- Mypy check integrated into CI (`.github/workflows/ci.yml`, `pyproject.toml`).
- Coverage gate raised to 95% and passing in CI.
- Editor command failures now surface non-zero exit codes (`src/askfind/interactive/commands.py`).

## Priority Order

1. Add lock-file policy enforcement (generate+commit or explicit ignore policy + CI check).
2. Clean up low-priority ergonomics (date format, narrower exceptions).
