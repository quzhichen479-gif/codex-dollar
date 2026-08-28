#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUTF8=1

if [ -n "${CODEX_METER_PYTHON:-}" ]; then
  PYTHON_BIN="$CODEX_METER_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
else
  echo "Python 3.10+ not found. Set CODEX_METER_PYTHON." >&2
  exit 1
fi

exec "$PYTHON_BIN" -m codex_meter "$@"
