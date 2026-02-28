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
- [ ] Update baseline report:
  - `docs/benchmark-baseline-YYYY-MM-DD.md`
- [ ] Commit the new `docs/benchmarks/YYYY-MM-DD/` artifacts + baseline report

## Release Workflow

- [ ] Create annotated tag: `git tag -a vX.Y.Z -m "vX.Y.Z"`
- [ ] Push tag: `git push origin vX.Y.Z`
- [ ] Verify `release.yml` artifacts (`dist/*`) were built and uploaded
