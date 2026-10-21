#!/usr/bin/env bash
# Unified backend management. Run ./backend.sh --help for all commands.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${LUMENX_PYTHON:-}" ]]; then
  PYTHON_BIN="$LUMENX_PYTHON"
elif [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
elif [[ -x "$HOME/miniconda3/envs/lumenx/bin/python" ]]; then
  PYTHON_BIN="$HOME/miniconda3/envs/lumenx/bin/python"
else
  PYTHON_BIN="$(command -v python3)"
fi
exec "$PYTHON_BIN" "$PROJECT_ROOT/scripts/backendctl.py" "$@"
