# Benchmark Scenarios (4-Sample Baseline)

This document defines a reproducible benchmark plan using 4 repository/sample types.

## Goals

- Track traversal latency regressions (`walk_and_filter` path).
- Track index-query parity regressions (`query_index` vs traversal).
- Compare behavior across small/medium/large/mixed datasets.

## Sample Set

| Sample | Recommended Root | Profile |
|---|---|---|
| S1 | `natural_language_base_file_finder_in_terminal` | Current target repo, cache-friendly baseline |
| S2 | `model-bridge-mcp` | Mid-size mixed codebase |
| S3 | `RNAseq_analysis_WebTool` | Large/real-world stress root |
| S4 | `/tmp/askfind_bench_synth` | Synthetic controlled dataset |

## Prepare S4 (Synthetic)

```bash
mkdir -p /tmp/askfind_bench_synth/src /tmp/askfind_bench_synth/docs /tmp/askfind_bench_synth/logs
for i in $(seq 1 1500); do
  printf "def f_%s(x):\n    if x > 0:\n        return x\n    return 0\n" "$i" > /tmp/askfind_bench_synth/src/file_$i.py
done
for i in $(seq 1 600); do
  printf "TODO item %s\n" "$i" > /tmp/askfind_bench_synth/docs/note_$i.md
done
for i in $(seq 1 120); do
  head -c 65536 /dev/urandom > /tmp/askfind_bench_synth/logs/blob_$i.bin
done
```

## Execution Plan

Assumption: run from project root with `PYTHONPATH=src`.

For each sample root (`$ROOT`):

1. Raw traversal benchmark:
```bash
PYTHONPATH=src python scripts/bench/benchmark_walk.py --root "$ROOT" --repeats 7 --workers 1 --json
PYTHONPATH=src python scripts/bench/benchmark_walk.py --root "$ROOT" --repeats 7 --workers 4 --json
```

2. Parallel regression gate:
```bash
PYTHONPATH=src python scripts/ci/benchmark_regression_gate.py --root "$ROOT" --repeats 7 --ratio-threshold 1.35
```

3. Index-query parity gate:
```bash
PYTHONPATH=src python scripts/ci/index_query_regression_gate.py --root "$ROOT" --repeats 7 --ratio-threshold 1.35
```

4. Similarity-threshold behavior check (new option):
```bash
askfind "files similar to auth.py" --root "$ROOT" --similarity-threshold 0.55 --no-rerank --no-cache
askfind "files similar to auth.py" --root "$ROOT" --similarity-threshold 0.85 --no-rerank --no-cache
```

## Suggested Reporting Fields

- `root`
- `scenario` (`all-files`, `python-files`, `todo-content`)
- `workers`
- `median_s`
- `result_count`
- `parallel_vs_baseline_ratio`
- `index_query_vs_walk_ratio`

## Pass/Fail Guidance

- `benchmark_regression_gate`: pass when all scenario ratios are `<= 1.35x`.
- `index_query_regression_gate`: pass when all scenario ratios are `<= 1.35x`.
- Similarity option sanity: stricter threshold should not increase result count.
