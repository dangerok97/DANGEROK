#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/backend/.venv/bin/python"
[[ -x "$PY" ]] || PY=python3

echo "==> Frontend lint"
cd "$ROOT/frontend"
if command -v yarn >/dev/null 2>&1; then yarn lint; else npm run lint; fi

echo "==> Backend pytest (skip Emergent live smokes)"
cd "$ROOT/backend"
export EXPO_PUBLIC_BACKEND_URL="${EXPO_PUBLIC_BACKEND_URL:-http://127.0.0.1:8000}"
"$PY" -m pytest tests -q \
  --ignore=tests/test_iter9_live_preview.py \
  --ignore=tests/test_iter10_live_smoke.py \
  --ignore=tests/test_iter11_live_smoke.py \
  --ignore=tests/test_iter21_live_smoke.py \
  --ignore=tests/test_iter22_live_smoke.py
