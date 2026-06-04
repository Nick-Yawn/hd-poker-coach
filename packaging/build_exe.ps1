# Build a standalone Windows .exe for the Hold'em Study Coach GUI.
#
#   .\.venv\Scripts\python.exe -m pip install -e ".[build]"   # one time
#   powershell -ExecutionPolicy Bypass -File packaging\build_exe.ps1
#
# Output: dist\HoldemCoach\HoldemCoach.exe  (one-dir build; double-clickable)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "venv not found at $py - create it first (see README)." }

# Bundle the sample hands next to the app so the Sample dropdown works.
& $py -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name HoldemCoach `
    --collect-submodules treys `
    --add-data "sample_hands;sample_hands" `
    "packaging\holdem_coach_gui.py"

# Ship the .env template next to the exe so users know where to put their key.
# The packaged app reads a `.env` placed in this folder at runtime (see
# holdem_coach/config.py frozen branch). We deliberately DO NOT bundle a real
# key into the binary or the dist folder during the build.
$dest = "dist\HoldemCoach"
if (Test-Path ".env.example") {
    Copy-Item ".env.example" (Join-Path $dest ".env.example") -Force
}

Write-Host ""
Write-Host "Built: $dest\HoldemCoach.exe" -ForegroundColor Green
Write-Host "To enable AI coaching for the packaged app, put your key in $dest\.env" -ForegroundColor Yellow
