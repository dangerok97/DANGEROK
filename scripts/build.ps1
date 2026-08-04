# Build checks (Windows)
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$code = 0

Write-Host "==> TypeScript check (frontend)" -ForegroundColor Cyan
Push-Location (Join-Path $Root "frontend")
npx tsc --noEmit
if ($LASTEXITCODE -ne 0) { $code = $LASTEXITCODE }
Pop-Location

Write-Host "==> Python compileall (backend)" -ForegroundColor Cyan
$py = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py -m compileall -q (Join-Path $Root "backend")
if ($LASTEXITCODE -ne 0) { $code = $LASTEXITCODE }

exit $code
