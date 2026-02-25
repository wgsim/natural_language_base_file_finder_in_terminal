# Environment Definition (Conda)

This project uses a dedicated Conda environment defined in [`environment.yml`](./environment.yml).

## Canonical Environment

- Name: `askfind_env`
- Python: `3.12`
- Source of pinned runtime deps: [`requirements.txt`](./requirements.txt)
- Dev/test tools included: `pytest`, `pytest-cov`, `mypy`, `ruff`, `pip-audit`

## Create Environment

```bash
conda env create -f environment.yml
conda activate askfind_env
```

## Update Environment

```bash
conda env update -n askfind_env -f environment.yml --prune
conda activate askfind_env
```

## Validate Environment

```bash
python --version
python -m askfind --help
python scripts/ci/check_dev_tool_pins.py
python -m mypy src
ruff check src tests
PYTHONPATH=src pytest -q --cov=src/askfind --cov-fail-under=95
```

## Hooks Integration

- Shared git hooks in `.githooks/` run lint+tests in `askfind_env` by default.
- If `askfind_env` is missing, hooks fall back to `pytest_env` when available.

## Reproducibility Notes

- Runtime package versions are pinned in `requirements.txt`.
- Dev tooling versions are pinned in [`environment.yml`](./environment.yml). Keep these pins aligned with [`.github/workflows/ci.yml`](./.github/workflows/ci.yml).
- The project itself is installed editable (`-e .`) so local source changes are reflected immediately.
- After changing dependency pins, refresh the environment:

```bash
conda env update -n askfind_env -f environment.yml --prune
conda activate askfind_env
```

- For reproducible snapshots, generate lock artifacts from a known-good environment:

```bash
conda env export -n askfind_env --no-builds > environment.lock.yml
conda list -n askfind_env --explicit > environment.lock.txt
```

- Lock usage:
  - `environment.lock.txt`: exact same-platform recreation (`conda create -n askfind_env --file environment.lock.txt`).
  - `environment.lock.yml`: portable recreation with solver variability (`conda env create -f environment.lock.yml`).
