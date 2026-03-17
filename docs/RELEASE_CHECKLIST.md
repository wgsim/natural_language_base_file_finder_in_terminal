# Release Checklist

Use this checklist before tagging and publishing a release.

## Quality Gates

- [ ] `./.githooks/pre-commit`
- [ ] `./.githooks/pre-push`
- [ ] CI workflow green on `main`

## PyPI Readiness

- [ ] Confirm package name, version, `requires-python`, and console entry point in `pyproject.toml`
- [ ] Confirm README installation guidance matches the intended public install path:
  - primary: `pipx install askfind`
  - alternative: `uv tool install askfind`
  - source install clearly marked as development-only
- [ ] Build fresh distribution artifacts locally:
  - clean old `dist/`, `build/`, and stale `src/*.egg-info` first
  - `python -m build`
  - `python -m twine check dist/*`
- [ ] Smoke-test installation from a built artifact or TestPyPI in an isolated environment before publishing
- [ ] Verify PyPI publishing credentials are ready:
  - trusted publisher configured in PyPI, or
  - PyPI API token available for manual upload
- [ ] Decide publish path before tagging:
  - manual publish (`twine upload dist/*` or `uv publish`)
  - or extend `release.yml` with an authenticated publish step
- [ ] Confirm package discovery on PyPI/TestPyPI after publish and verify `pipx install askfind` works end-to-end

## Versioning

- [ ] `pyproject.toml` version updated
- [ ] `src/askfind/__init__.py` version updated
- [ ] `CHANGELOG.md` updated with release notes

## Benchmark Baseline Refresh

- [ ] Regenerate S4 synthetic dataset:
  - `scripts/bench/generate_synth_dataset.sh /tmp/askfind_bench_synth`
- [ ] Re-run S1-S4 benchmark artifact generation (workers 1 and 4) using `docs/BENCHMARK_SCENARIOS.md`
- [ ] Re-run compare reports using `scripts/bench/compare_benchmark_results.py`
- [ ] Run CI-style regression gates with release threshold (`1.35x`):
  - `PYTHONPATH=src python scripts/ci/benchmark_regression_gate.py --root . --ratio-threshold 1.35`
  - `PYTHONPATH=src python scripts/ci/index_query_regression_gate.py --root . --ratio-threshold 1.35`
- [ ] (Optional) Capture LLM mode routing/cost baseline:
  - `PYTHONPATH=src python scripts/bench/benchmark_llm_modes.py --root . --repeats 3 --output-json /tmp/askfind-llm-modes.json --output-csv /tmp/askfind-llm-modes.csv`
- [ ] Confirm gate expectations in output:
  - pass condition is `ratio <= threshold` (gate fails only when `ratio > threshold`)
  - default scenarios are `all-files` and `python-files` when both are available (unless `--scenario` overrides)
- [ ] Update baseline report:
  - `docs/benchmark-baseline-YYYY-MM-DD.md`
- [ ] Commit the new `docs/benchmarks/YYYY-MM-DD/` artifacts + baseline report

## Benchmark Baseline Cadence Policy

- [ ] Weekly refresh: run baseline capture once per week (recommended Monday, UTC)
- [ ] Mandatory refresh before each release tag (`v*`)
- [ ] Additional refresh after major performance-impacting changes:
  - walker traversal algorithm changes
  - index query path changes
  - cache key/cache policy changes

## Release Workflow

- [ ] Create annotated tag: `git tag -a vX.Y.Z -m "vX.Y.Z"`
- [ ] Push tag: `git push origin vX.Y.Z`
- [ ] Verify `release.yml` artifacts (`dist/*`) were built and uploaded
