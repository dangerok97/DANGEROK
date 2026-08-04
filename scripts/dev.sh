#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/backend/.venv/bin/python"
[[ -x "$PY" ]] || PY=python3

echo "==> Starting ORA backend on :8000"
(cd "$ROOT/backend" && "$PY" -m uvicorn server:app --reload --host 0.0.0.0 --port 8000) &
BACK_PID=$!
trap 'kill $BACK_PID 2>/dev/null || true' EXIT
sleep 2

echo "==> Starting Expo"
cd "$ROOT/frontend"
if command -v yarn >/dev/null 2>&1; then yarn start; else npx expo start; fi
