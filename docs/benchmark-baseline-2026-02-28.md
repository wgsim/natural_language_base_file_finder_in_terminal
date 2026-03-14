# Benchmark Baseline (2026-02-28)

Assumption: this is a fast smoke baseline (`repeats=1`) captured on February 28, 2026.

- Metric: `median_s`
- Comparison: `workers=4 / workers=1`
- Threshold used for compare checks: `1.35x`
- Raw artifacts: `docs/benchmarks/2026-02-28/`

## Results

| Sample | Root | Scenario | Median (w=1, s) | Median (w=4, s) | Ratio (w4/w1) |
|---|---|---|---:|---:|---:|
| S1 | `natural_language_base_file_finder_in_terminal` | all-files | 0.070409 | 0.060649 | 0.861x |
| S1 | `natural_language_base_file_finder_in_terminal` | python-files | 0.056020 | 0.057077 | 1.019x |
| S1 | `natural_language_base_file_finder_in_terminal` | todo-content | 0.058574 | 0.062378 | 1.065x |
| S2 | `sample-medium-public-repo` | all-files | 0.032817 | 0.018384 | 0.560x |
| S2 | `sample-medium-public-repo` | python-files | 0.013472 | 0.016311 | 1.211x |
| S2 | `sample-medium-public-repo` | todo-content | 0.016435 | 0.020973 | 1.276x |
| S3 | `sample-large-public-repo` | all-files | 0.353088 | 0.329904 | 0.934x |
| S3 | `sample-large-public-repo` | python-files | 0.321681 | 0.325408 | 1.012x |
| S3 | `sample-large-public-repo` | todo-content | 0.340536 | 0.340175 | 0.999x |
| S4 | `synthetic-bench-root` | all-files | 0.082037 | 0.067752 | 0.826x |
| S4 | `synthetic-bench-root` | python-files | 0.041206 | 0.043140 | 1.047x |
| S4 | `synthetic-bench-root` | todo-content | 0.093594 | 0.106982 | 1.143x |

## Notes

- This baseline is useful for trend checks and CI sanity, not for rigorous statistical performance claims.
- For release-level performance assertions, rerun with `--repeats 5` or higher and compare artifacts with `scripts/bench/compare_benchmark_results.py`.
