#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "==> ORA setup"

copy_env() {
  local src="$1" dst="$2"
  if [[ ! -f "$dst" ]]; then
    cp "$src" "$dst"
    echo "Created $dst — fill in secrets before running."
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
pip install --upgrade pip
if ! pip install -r "$ROOT/backend/requirements.txt"; then
  echo "WARNING: full requirements install failed (often Emergent litellm URL). See docs/DEVELOPMENT_STATE.md" >&2
fi

cd "$ROOT/frontend"
if command -v yarn >/dev/null 2>&1; then yarn install; else npm install; fi

cat <<EOF

Setup finished (with possible warnings).
Next:
  1. Start MongoDB or set MONGO_URL in backend/.env
  2. Fill JWT_SECRET and EMERGENT_LLM_KEY
  3. Run: ./scripts/dev.sh
EOF
