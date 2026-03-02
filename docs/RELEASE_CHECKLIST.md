# Release Checklist

Use this checklist before tagging and publishing a release.

## Quality Gates

- [ ] `./.githooks/pre-commit`
- [ ] `./.githooks/pre-push`
- [ ] CI workflow green on `main`

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
