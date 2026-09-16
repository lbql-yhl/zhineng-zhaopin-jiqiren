#!/bin/zsh
set -eu

if [ -n "${XIAOZHAO_PACKAGE_ROOT:-}" ]; then
  PACKAGE_ROOT="$XIAOZHAO_PACKAGE_ROOT"
else
  PACKAGE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

exec "$PYTHON_BIN" "$PACKAGE_ROOT/automations/run_cron_automation.py" "$@"
