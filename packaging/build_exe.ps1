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

Write-Host ""
Write-Host "Built: dist\HoldemCoach\HoldemCoach.exe" -ForegroundColor Green
