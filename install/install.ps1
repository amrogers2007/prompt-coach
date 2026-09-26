# Install Prompt Coach for Claude Code on Windows (PowerShell).
# Usage:  powershell -ExecutionPolicy Bypass -File install\install.ps1
$ErrorActionPreference = "Stop"
$Repo = "amrogers2007/prompt-coach"

$claude = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claude) {
  # The Claude desktop app bundles its own copy that is not on PATH.
  $bundled = Get-ChildItem "$env:APPDATA\Claude\claude-code\*\claude.exe" -ErrorAction SilentlyContinue |
             Sort-Object FullName -Descending | Select-Object -First 1
  if ($bundled) { $claude = $bundled.FullName } else {
    Write-Host "Claude Code was not found. Using the Claude desktop app? Open Customize > Plugins and upload dist\prompt-coach-plugin.zip"
    Write-Host "(build it with: python coach\scripts\build_zip.py)"
    exit 1
  }
} else { $claude = $claude.Source }

$py = $null
foreach ($c in "python3", "python", "py") {
  $cmd = Get-Command $c -ErrorAction SilentlyContinue
  if ($cmd) {
    & $cmd.Source -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = $cmd.Source; break }
  }
}
if (-not $py) {
  Write-Host "Prompt Coach needs Python 3.9 or newer: https://www.python.org/downloads/  (tick 'Add python.exe to PATH'). Then re-run this script."
  exit 1
}

Write-Host "Adding the Prompt Coach marketplace..."
& $claude plugin marketplace add $Repo
Write-Host "Installing the plugin..."
& $claude plugin install prompt-coach@prompt-coach
Write-Host ""
Write-Host "Health check:"
& $py (Join-Path $PSScriptRoot "..\coach\scripts\coach.py") doctor
Write-Host ""
Write-Host "Done. Start a new Claude Code session and just work as usual; the coach starts automatically."
Write-Host "Type /prompt-coach:score any time to see your level."
