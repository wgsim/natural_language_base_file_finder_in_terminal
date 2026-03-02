# Changelog

All notable changes to this project are documented in this file.

## [0.1.18] - 2026-03-02

### Added
- Added interactive offline-mode parity:
  - `askfind -i --offline` now skips API key/LLM client initialization in interactive session mode.
- Added dedicated CI `offline-smoke` job:
  - validates expected offline match behavior on a temporary sample tree.
  - asserts broad offline queries fail with an explicit `too broad` guard message.
- Added stronger regression tests for:
  - index-query gate parity/mismatch diagnostics
  - benchmark-regression gate threshold/invalid-median handling
  - fallback parser false-positive prevention cases

### Changed
- Improved offline fallback parser precision:
  - plain verb usage of `go` no longer implies Go-language extension matching.
  - generic scope words (`project`, `repo`, `repository`, `codebase`, `workspace`) are no longer inferred as concrete path filters.
- Improved index-query regression gate output:
  - scenario lines now include explicit parity state (`parity=match|mismatch`).
  - mismatch/ratio failure messages now include delta, direction, and over-threshold diagnostics.
- Hardened benchmark-regression gate validation:
  - rejects non-finite `--ratio-threshold` values.
  - fails safely on non-finite or negative median measurements with explicit diagnostics.
- Updated package version metadata to `0.1.18`.

## [0.1.17] - 2026-03-02

### Added
- Added explicit offline search mode via CLI flag:
  - `--offline` skips API key validation and LLM calls.
  - search runs with local heuristic filter parsing only.
- Added offline end-to-end CLI coverage:
  - offline successful search path without LLM mocks
  - offline broad-query rejection guard path
  - offline `--cache-stats` output path

### Changed
- Improved fallback parser precision for natural language queries:
  - reduced path false positives for size/time phrases
  - improved `path` / `not_path` normalization and determiner handling
  - preserved quoted `has` terms that include words like `in`
- Extended fallback parser support for:
  - `size` constraints (`larger than`, `under`, etc.)
  - relative `mod` windows (`last 7 days`, `past 3 hours`, etc.)
- Updated package version metadata to `0.1.17`.

## [0.1.16] - 2026-02-28

### Added
- Added release checklist document: `docs/RELEASE_CHECKLIST.md`
  - includes mandatory benchmark-baseline refresh items for release prep.
- Added reusable S4 synthetic dataset generator:
  - `scripts/bench/generate_synth_dataset.sh`
  - parameterized via `PY_FILES`, `TODO_FILES`, `BINARY_FILES`, `BINARY_BYTES`.
- Added optional CI benchmark compare job in `.github/workflows/ci.yml`:
  - manual `workflow_dispatch` inputs
  - baseline-vs-candidate comparison through `scripts/bench/compare_benchmark_results.py`.

### Changed
- Updated benchmark scenario docs to use the new synthetic dataset generator script.
- Updated package version metadata to `0.1.16`.

## [0.1.15] - 2026-02-28

### Added
- Added benchmark artifact outputs to `scripts/bench/benchmark_walk.py`:
  - `--output-json` for structured benchmark payload files
  - `--output-csv` for tabular benchmark rows
- Added benchmark comparison utility: `scripts/bench/compare_benchmark_results.py`
  - compares baseline/candidate JSON or CSV benchmark files
  - reports per-scenario ratios and returns non-zero on regression
- Added benchmark script tests:
  - `tests/test_benchmark_walk_script.py`
  - `tests/test_compare_benchmark_results.py`
- Added 4-sample measured baseline report:
  - `docs/benchmark-baseline-2026-02-28.md`
  - raw artifacts under `docs/benchmarks/2026-02-28/`

### Changed
- Updated LLM prompt guidance to state that similarity cutoff is runtime-controlled (`similarity_threshold` / `--similarity-threshold`) and should not be emitted by the model.
- Updated package version metadata to `0.1.15`.

## [0.1.14] - 2026-02-28

### Added
- Added configurable similarity cutoff support:
  - new CLI override `--similarity-threshold`
  - new config key `similarity_threshold` under `[search]`
  - threshold now participates in cache-key construction (single + interactive modes)
- Added index module branch-coverage tests for root resolve failures and `_matches_indexed_path` guard branches.
- Added a 4-sample benchmark scenario guide under `docs/BENCHMARK_SCENARIOS.md`.

### Changed
- Updated package version metadata to `0.1.14`.

## [0.1.13] - 2026-02-28

### Added
- Added similarity filtering support via `similar` query filter.
- Added code metrics filtering support via `loc` and `complexity` query filters.
- Added parser/prompt support and tests for similarity/code-metrics filters.

### Changed
- Search pipeline now applies similarity and code-metrics filters in both traversal and index-query paths.
- Updated package version metadata to `0.1.13`.

## [0.1.12] - 2026-02-28

### Added
- Added language filtering support via `lang` / `not_lang` query filters.
- Added license filtering support via `license` / `not_license` query filters.
- Added parser/prompt support and tests for language/license filters.

### Changed
- Search pipeline now applies language/license filters in both live traversal and index-query paths.
- Updated package version metadata to `0.1.12`.

## [0.1.11] - 2026-02-28

### Added
- Added macOS Finder tag filtering support via `tag` query filter:
  - parses and matches `com.apple.metadata:_kMDItemUserTags` extended attributes.
  - supports case-insensitive tag matching and strips Finder color suffixes.
- Added parser, filter, walker, and CLI tests for tag-filtered search scenarios.

### Changed
- Search pipeline now applies tag filtering in both live traversal and index-query paths.
- Updated package version metadata to `0.1.11`.

## [0.1.10] - 2026-02-28

### Added
- Added archive content matching support (stage 2) for `--search-archives`:
  - `.zip` and `.tar.gz` entries can now satisfy `has` content filters.
  - archive-member checks stream content with existing content-scan size limits.
- Added walker tests covering archive `has` matching and member-name/content combinations.

### Changed
- Refined archive traversal decisions in walker:
  - archive-member scans are now triggered for `has` queries and for non-direct path/name matches.
- Updated package version metadata to `0.1.10`.

## [0.1.9] - 2026-02-27

### Added
- Added index query runtime observability in CLI `--cache-stats` output:
  - index query hit/fallback counters
  - fallback reason counters (for index-unusable paths)
- Added index query regression gate:
  - new script `scripts/ci/index_query_regression_gate.py`
  - new CI step in `.github/workflows/ci.yml`

### Changed
- Implemented incremental early termination in walker:
  - traversal now propagates a shared match budget for `max_results`
  - sequential and parallel scan paths stop scanning/scheduling earlier once budget is exhausted
- Expanded lint gates to include `scripts/` in CI and local hooks.
- Updated package version metadata to `0.1.9`.

## [0.1.8] - 2026-02-27

### Added
- Added runtime index query integration:
  - search execution now attempts `query_index(...)` first when an index is present, fresh, and option-compatible.
  - automatic fallback to filesystem traversal when index is unavailable/unusable.
- Added persistent disk cache for `LLMClient.extract_filters`:
  - file: `~/.cache/askfind/extract_filters_cache.json`
  - TTL, max-entry pruning, and fail-open error handling.
- Added tests for runtime index query/fallback paths and disk-cache edge cases.

### Changed
- Updated package version metadata to `0.1.8`.

## [0.1.7] - 2026-02-27

### Added
- Added index management commands:
  - `askfind index build`
  - `askfind index update`
  - `askfind index status`
  - `askfind index clear`
- Added persistent per-root index storage under `~/.cache/askfind/indexes`.
- Added CI performance regression gate:
  - new script `scripts/ci/benchmark_regression_gate.py`
  - new CI step in `.github/workflows/ci.yml`
- Added process-local memoization for `LLMClient.extract_filters` with TTL and bounded cache size.
- Added tests for index module and benchmark regression gate.

### Changed
- Updated package version metadata to `0.1.7`.

## [0.1.6] - 2026-02-26

### Added
- Added cache observability support:
  - `--cache-stats` CLI switch to print per-command cache counters (`hits`, `misses`, `sets`) to stderr.
- Added interactive-mode cache integration:
  - interactive queries now use the same file-based cache policy (enabled/TTL) as single-command mode.

### Changed
- Fixed CI type-check failure by replacing PEP 695 `type` aliases with mypy-compatible `TypeAlias` declarations in the cache module.
- Interactive search now explicitly forwards `respect_ignore_files` to traversal.

## [0.1.5] - 2026-02-26

### Added
- Added search cache controls:
  - `cache_enabled` config option under `[search]` (default: `true`)
  - `cache_ttl_seconds` config option under `[search]` (default: `300`)
  - `--no-cache` CLI switch to bypass cache for a single command
- Added file-based search cache implementation with:
  - keying by query/root/search options/model/base_url
  - TTL-based expiry
  - root fingerprint checks for coarse invalidation
- Added cache unit tests (`tests/test_search_cache.py`).

### Changed
- Single-command search now checks cache before LLM extraction/walker traversal.
- Updated package version metadata to `0.1.5`.

## [0.1.4] - 2026-02-26

### Added
- Added parallel traversal controls:
  - `parallel_workers` config option under `[search]` (default: `1`)
  - `--workers` CLI option (`0` uses configured value)
- Added worker selection to traversal benchmark script (`scripts/bench/benchmark_walk.py`).

### Changed
- Implemented threaded directory traversal path in walker for performance improvements.
- Updated docs/roadmap to include parallel traversal status and configuration examples.
- Updated package version metadata to `0.1.4`.

## [0.1.3] - 2026-02-26

### Added
- Added safe symlink traversal option:
  - `--follow-symlinks` CLI switch.
  - `follow_symlinks` config option under `[search]`.
  - Root-bounded traversal and cycle protection for followed symlink directories.
- Added binary file exclusion controls:
  - Binary detection/exclusion enabled by default.
  - `--include-binary` CLI switch.
  - `exclude_binary_files` config option under `[search]`.
- Added release workflow `.github/workflows/release.yml` for `v*` tags:
  - build (`python -m build`)
  - artifact validation (`twine check`)
  - upload of `dist/*` artifacts
- Added traversal benchmark baseline script: `scripts/bench/benchmark_walk.py`.

### Changed
- Updated README/CONTRIBUTING/FUTURE docs to align with current repository links and quality gates.
- Updated package version metadata to `0.1.3`.

## [0.1.2] - 2026-02-25

### Added
- Added ignore-aware traversal controls:
  - Root and nested `.gitignore` support.
  - Root and nested `.askfindignore` support.
  - `--no-ignore` CLI switch to disable ignore rules per command.
  - `respect_ignore_files` config option under `[search]`.
- Added tests for nested ignore behavior and ignore negation handling.

### Changed
- Improved release/readme documentation for ignore behavior and quality gates.
- Updated package version metadata to `0.1.2`.

## [0.1.1] - 2026-02-25

### Added
- Added CI `mypy` type check stage.
- Added `pip-audit` severity gate script tests.
- Added dev tool pin consistency check in CI/hooks.

### Changed
- Raised coverage gate to `95%`.
- Hardened interactive editor error reporting.
- Enforced lock-file policy as ignored/untracked local artifacts.

## [0.1.0] - 2026-02-03

### Added
- Initial release of `askfind`.
