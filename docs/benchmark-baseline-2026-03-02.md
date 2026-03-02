# Benchmark Baseline (2026-03-02)

Assumption: this baseline was captured with `repeats=3` on March 2, 2026.

- Metric: `median_s`
- Comparison: `workers=4 / workers=1`
- Threshold used for compare checks: `1.35x`
- Raw artifacts: `docs/benchmarks/2026-03-02/`

## Results

| Sample | Root | Scenario | Median (w=1, s) | Median (w=4, s) | Ratio (w4/w1) |
|---|---|---|---:|---:|---:|
| S1 | `natural_language_base_file_finder_in_terminal` | all-files | 0.079843 | 0.081991 | 1.027x |
| S1 | `natural_language_base_file_finder_in_terminal` | python-files | 0.076969 | 0.084062 | 1.092x |
| S1 | `natural_language_base_file_finder_in_terminal` | todo-content | 0.079267 | 0.083161 | 1.049x |
| S2 | `model-bridge-mcp` | all-files | 0.016110 | 0.017436 | 1.082x |
| S2 | `model-bridge-mcp` | python-files | 0.015385 | 0.016163 | 1.051x |
| S2 | `model-bridge-mcp` | todo-content | 0.018439 | 0.021623 | 1.173x |
| S3 | `RNAseq_analysis_WebTool` | all-files | 0.354267 | 0.348926 | 0.985x |
| S3 | `RNAseq_analysis_WebTool` | python-files | 0.340019 | 0.341560 | 1.005x |
| S3 | `RNAseq_analysis_WebTool` | todo-content | 0.372253 | 0.359803 | 0.967x |
| S4 | `/tmp/askfind_bench_synth` | all-files | 0.062445 | 0.060631 | 0.971x |
| S4 | `/tmp/askfind_bench_synth` | python-files | 0.040838 | 0.042917 | 1.051x |
| S4 | `/tmp/askfind_bench_synth` | todo-content | 0.094899 | 0.118373 | 1.247x |

## Notes

- All sample compare runs (`s1_compare.json` ... `s4_compare.json`) passed the `1.35x` threshold.
- This baseline is intended for trend/regression checks. For stronger statistical confidence, rerun with higher `--repeats`.
