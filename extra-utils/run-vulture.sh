#!/usr/bin/env bash
set -euo pipefail

# Dead code scan helper for this repo.
# Usage:
#   uv pip install vulture  # or: pip install vulture
#   extra-utils/run-vulture.sh

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="$ROOT_DIR/src"

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
  vulture "$SRC_DIR" "$WHITELIST" \
    --min-confidence 90 \
    --exclude "$EXCLUDE_ARG"
else
  vulture "$SRC_DIR" \
    --min-confidence 90 \
    --exclude "$EXCLUDE_ARG"
fi

echo
echo "Tips:" >&2
echo "- Generate a whitelist skeleton: vulture src --min-confidence 90 --make-whitelist > vulture_whitelist.py" >&2
echo "- Re-run this script after reviewing/adjusting the whitelist." >&2

