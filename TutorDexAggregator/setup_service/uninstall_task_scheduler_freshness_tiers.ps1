# PowerShell script to remove Windows Task Scheduler job for freshness tiers.
# Run this as Administrator.
#
# Uses `schtasks.exe` for maximum compatibility with Windows 10 Task Scheduler.

$ErrorActionPreference = "Stop"

$TaskName = "TutorDex-Freshness-Tiers"

Write-Host "Uninstalling task '$TaskName'..." -ForegroundColor Cyan
schtasks.exe /Query /TN $TaskName 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Task '$TaskName' not found. Nothing to uninstall." -ForegroundColor Yellow
  exit 0
}

schtasks.exe /Delete /TN $TaskName /F 1>$null 2>$null
Write-Host "Done." -ForegroundColor Green