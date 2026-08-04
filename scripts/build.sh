#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/backend/.venv/bin/python"
[[ -x "$PY" ]] || PY=python3
code=0

echo "==> TypeScript check (frontend)"
cd "$ROOT/frontend"
npx tsc --noEmit || code=$?

echo "==> Python compileall (backend)"
"$PY" -m compileall -q "$ROOT/backend" || code=$?
exit "$code"
