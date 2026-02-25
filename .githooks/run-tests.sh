#!/bin/sh
set -eu

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if command -v conda >/dev/null 2>&1; then
  if conda env list 2>/dev/null | awk '{print $1}' | grep -Fxq "askfind_env"; then
    conda run -n askfind_env sh -lc 'PYTHONPATH=src pytest -q'
    exit $?
  fi
fi

if [ -x "./pytest_env/bin/pytest" ]; then
  PYTHONPATH=src ./pytest_env/bin/pytest -q
  exit $?
fi

echo "hook: no test environment found." >&2
echo "hook: create askfind_env (conda env create -f environment.yml)" >&2
echo "hook: or create pytest_env and install pytest." >&2
exit 1
