#!/bin/sh
set -eu

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if [ ! -x "./pytest_env/bin/pytest" ]; then
  echo "hook: ./pytest_env/bin/pytest not found. Create pytest_env first." >&2
  exit 1
fi

PYTHONPATH=src ./pytest_env/bin/pytest -q
