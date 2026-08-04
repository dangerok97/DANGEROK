# ORA local setup (Windows) — Emergent-free dependency path
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> ORA setup" -ForegroundColor Cyan

function Ensure-Copy {
  param([string]$src, [string]$dst)
  if (-not (Test-Path $dst)) {
    Copy-Item $src $dst
    Write-Host "Created $dst - fill secrets before running."
  } else {
    Write-Host "Exists $dst"
  }
}

function Get-Python {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    $v = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
    if ($v) { return $v.Trim() }
    $v = & py -3 -c "import sys; print(sys.executable)" 2>$null
    if ($v) { return $v.Trim() }
  }
  if (Get-Command python -ErrorAction SilentlyContinue) {
    $v = & python -c "import sys; print(sys.executable)" 2>$null
    if ($v -and $v -notmatch "WindowsApps") { return $v.Trim() }
  }
  throw "Python 3.12+ not found. Install Python.Python.3.12 via winget."
}

Ensure-Copy "$Root\backend\.env.example" "$Root\backend\.env"
Ensure-Copy "$Root\frontend\.env.example" "$Root\frontend\.env"

$python = Get-Python
Write-Host "Using Python: $python"

$venv = Join-Path $Root "backend\.venv"
if (-not (Test-Path $venv)) {
  Write-Host "Creating backend\.venv"
  & $python -m venv $venv
}
$pip = Join-Path $venv "Scripts\pip.exe"

Write-Host "Installing local Python requirements (no Emergent CDN packages)..."
$pyVenv = Join-Path $venv "Scripts\python.exe"
& $pyVenv -m pip install --upgrade pip
$reqLocal = Join-Path $Root "backend\requirements-local.txt"
if (-not (Test-Path $reqLocal)) {
  throw "Missing backend\requirements-local.txt"
}
& $pyVenv -m pip install -r $reqLocal

Push-Location "$Root\frontend"
try {
  $env:ORA_SKIP_CMD_GUARD = "1"
  if (Get-Command yarn -ErrorAction SilentlyContinue) {
    Write-Host "yarn install"
    yarn install
  } else {
    Write-Host "npm install"
    npm install
  }
} finally {
  Pop-Location
}

Write-Host "Setup finished." -ForegroundColor Green
Write-Host "1. Ensure MongoDB on mongodb://127.0.0.1:27017"
Write-Host "2. Confirm backend\.env and frontend\.env"
Write-Host "3. Run: .\scripts\dev.ps1"
