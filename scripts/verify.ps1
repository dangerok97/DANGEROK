# Full local verification gate (Windows)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$failed = $false

Write-Host "==> verify: test" -ForegroundColor Cyan
& "$PSScriptRoot\test.ps1"
if ($LASTEXITCODE -ne 0) { $failed = $true }

Write-Host "==> verify: build" -ForegroundColor Cyan
& "$PSScriptRoot\build.ps1"
if ($LASTEXITCODE -ne 0) { $failed = $true }

if ($failed) {
  Write-Host "VERIFY FAILED" -ForegroundColor Red
  exit 1
}
Write-Host "VERIFY OK" -ForegroundColor Green
