#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
failed=0
"$ROOT/scripts/test.sh" || failed=1
"$ROOT/scripts/build.sh" || failed=1
if [[ "$failed" -ne 0 ]]; then
  echo "VERIFY FAILED"
  exit 1
fi
echo "VERIFY OK"
