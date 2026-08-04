# ORA local setup (Windows)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> ORA setup" -ForegroundColor Cyan

function Ensure-Copy($src, $dst) {
  if (-not (Test-Path $dst)) {
    Copy-Item $src $dst
    Write-Host "Created $dst — fill in secrets before running."
  } else {
    Write-Host "Exists $dst"
  }
}

Ensure-Copy "$Root\backend\.env.example" "$Root\backend\.env"
Ensure-Copy "$Root\frontend\.env.example" "$Root\frontend\.env"

# Python venv
$venv = Join-Path $Root "backend\.venv"
if (-not (Test-Path $venv)) {
  Write-Host "Creating backend\.venv"
  python -m venv $venv
}
$pip = Join-Path $venv "Scripts\pip.exe"
$py = Join-Path $venv "Scripts\python.exe"

Write-Host "Installing Python requirements (may fail on Emergent-hosted litellm wheel)..."
& $pip install --upgrade pip
try {
  & $pip install -r "$Root\backend\requirements.txt"
} catch {
  Write-Warning "Full requirements install failed. See docs/DEVELOPMENT_STATE.md"
  Write-Warning $_.Exception.Message
}

# Frontend deps
Push-Location "$Root\frontend"
try {
  if (Get-Command yarn -ErrorAction SilentlyContinue) {
    Write-Host "yarn install"
    yarn install
  } else {
    Write-Host "npm install (yarn not found)"
    npm install
  }
} finally {
  Pop-Location
}

Write-Host @"

Setup finished (with possible warnings).
Next:
  1. Start MongoDB locally or set MONGO_URL in backend\.env
  2. Fill JWT_SECRET and EMERGENT_LLM_KEY in backend\.env
  3. Run:  .\scripts\dev.ps1
"@ -ForegroundColor Green
