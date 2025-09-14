#!/usr/bin/env bash
set -euo pipefail

# Dead code scan helper for this repo.
# Usage:
#   uv pip install vulture  # or: pip install vulture
#   extra-utils/run-vulture.sh

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="$ROOT_DIR/src"

# Prefer project venv's Python if available
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PY="$ROOT_DIR/.venv/bin/python"
else
  PY="${PYTHON:-$(command -v python3 || command -v python)}"
fi

# Choose how to invoke Vulture
if command -v vulture >/dev/null 2>&1; then
  RUN_VULTURE=("vulture")
else
  RUN_VULTURE=("$PY" -m vulture)
fi

EXCLUDES=(
  ".venv"
  ".uv-cache"
  "tests"
  "**/__pycache__/**"
)

EXCLUDE_ARG=$(IFS=","; echo "${EXCLUDES[*]}")

WHITELIST="$ROOT_DIR/vulture_whitelist.py"

if [[ -f "$WHITELIST" ]]; then
  echo "> Using whitelist: $WHITELIST" >&2
  "${RUN_VULTURE[@]}" "$SRC_DIR" "$WHITELIST" \
    --min-confidence 90 \
    --exclude "$EXCLUDE_ARG"
else
  "${RUN_VULTURE[@]}" "$SRC_DIR" \
    --min-confidence 90 \
    --exclude "$EXCLUDE_ARG"
fi

echo
echo "Tips:" >&2
echo "- Generate a whitelist skeleton: vulture src --min-confidence 90 --make-whitelist > vulture_whitelist.py" >&2
echo "- Re-run this script after reviewing/adjusting the whitelist." >&2
