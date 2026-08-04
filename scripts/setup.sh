#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "==> ORA setup"

copy_env() {
  local src="$1" dst="$2"
  if [[ ! -f "$dst" ]]; then
    cp "$src" "$dst"
    echo "Created $dst - fill secrets before running."
  else
    echo "Exists $dst"
  fi
}

copy_env "$ROOT/backend/.env.example" "$ROOT/backend/.env"
copy_env "$ROOT/frontend/.env.example" "$ROOT/frontend/.env"

if [[ ! -d "$ROOT/backend/.venv" ]]; then
  python3 -m venv "$ROOT/backend/.venv"
fi
# shellcheck disable=SC1091
source "$ROOT/backend/.venv/bin/activate"
python -m pip install --upgrade pip
pip install -r "$ROOT/backend/requirements-local.txt"

cd "$ROOT/frontend"
export ORA_SKIP_CMD_GUARD=1
if command -v yarn >/dev/null 2>&1; then yarn install; else npm install; fi

cat <<EOF
Setup finished.
Next:
  1. Ensure MongoDB on mongodb://127.0.0.1:27017
  2. Confirm backend/.env and frontend/.env
  3. Run backend uvicorn + expo (see README)
EOF
