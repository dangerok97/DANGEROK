# Start ORA backend + frontend (Windows)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "==> Starting ORA backend on :8000" -ForegroundColor Cyan
$backend = Start-Process -PassThru -NoNewWindow -FilePath $py -ArgumentList @(
  "-m", "uvicorn", "server:app", "--reload", "--host", "0.0.0.0", "--port", "8000"
) -WorkingDirectory (Join-Path $Root "backend")

Start-Sleep -Seconds 2

Write-Host "==> Starting Expo" -ForegroundColor Cyan
Push-Location (Join-Path $Root "frontend")
try {
  if (Get-Command yarn -ErrorAction SilentlyContinue) {
    yarn start
  } else {
    npx expo start
  }
} finally {
  Pop-Location
  if ($backend -and -not $backend.HasExited) {
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
  }
}
