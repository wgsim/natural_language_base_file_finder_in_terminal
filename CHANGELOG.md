# Changelog

All notable changes to this project are documented in this file.

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
