# Run ORA test suites (Windows)
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "==> Frontend lint" -ForegroundColor Cyan
Push-Location (Join-Path $Root "frontend")
if (Get-Command yarn -ErrorAction SilentlyContinue) { yarn lint } else { npm run lint }
Pop-Location

Write-Host "==> Backend pytest (offline-friendly selection)" -ForegroundColor Cyan
Push-Location (Join-Path $Root "backend")
$env:EXPO_PUBLIC_BACKEND_URL = if ($env:EXPO_PUBLIC_BACKEND_URL) { $env:EXPO_PUBLIC_BACKEND_URL } else { "http://127.0.0.1:8000" }
& $py -m pytest tests -q --ignore=tests/test_iter9_live_preview.py --ignore=tests/test_iter10_live_smoke.py --ignore=tests/test_iter11_live_smoke.py --ignore=tests/test_iter21_live_smoke.py --ignore=tests/test_iter22_live_smoke.py
$code = $LASTEXITCODE
Pop-Location
exit $code
