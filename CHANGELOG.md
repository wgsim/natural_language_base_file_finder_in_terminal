# Changelog

All notable changes to this project are documented in this file.

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
