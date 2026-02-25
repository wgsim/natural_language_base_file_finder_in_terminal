# Environment Definition (Conda)

This project uses a dedicated Conda environment defined in [`environment.yml`](./environment.yml).

## Canonical Environment

- Name: `askfind_env`
- Python: `3.12`
- Source of pinned runtime deps: [`requirements.txt`](./requirements.txt)
- Dev/test tools included: `pytest`, `pytest-cov`, `ruff`, `pip-audit`

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
ruff check src tests
PYTHONPATH=src pytest -q
```

## Hooks Integration

- Shared git hooks in `.githooks/` run lint+tests in `askfind_env` by default.
- If `askfind_env` is missing, hooks fall back to `pytest_env` when available.

## Reproducibility Notes

- Runtime package versions are pinned in `requirements.txt` and installed by `environment.yml`.
- The project itself is installed editable (`-e .`) so local source changes are reflected immediately.
