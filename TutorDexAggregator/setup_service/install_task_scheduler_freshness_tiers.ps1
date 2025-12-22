# PowerShell script to create Windows Task Scheduler job for freshness tiers.
# Run this as Administrator.
#
# Uses `schtasks.exe` for maximum compatibility with Windows 10 Task Scheduler.

$ErrorActionPreference = "Stop"

$TaskName = "TutorDex-Freshness-Tiers"
$ScriptPath = "$PSScriptRoot\run_freshness_tiers.bat"

Write-Host "Installing TutorDex freshness tier Task Scheduler job..." -ForegroundColor Cyan
Write-Host "Script path: $ScriptPath" -ForegroundColor Gray
Write-Host ""

# Remove if exists (suppress "not found" noise).
schtasks.exe /Query /TN $TaskName 1>$null 2>$null
if ($LASTEXITCODE -eq 0) {
  schtasks.exe /Delete /TN $TaskName /F 1>$null 2>$null
}

# Start time: next 5-minute boundary (Task Scheduler requires HH:mm).
$now = Get-Date
$start = $now.AddMinutes(5 - ($now.Minute % 5))
if ($start -le $now) { $start = $start.AddMinutes(5) }
$StartTime = $start.ToString("HH:mm")

$Cmd = "cmd.exe /c `"$ScriptPath`""

Write-Host "Creating task '$TaskName' (hourly, starting at $StartTime)..." -ForegroundColor Cyan

schtasks.exe /Create `
  /TN $TaskName `
  /TR $Cmd `
  /SC HOURLY `
  /MO 1 `
  /ST $StartTime `
  /RL HIGHEST `
  /F | Out-Null

Write-Host ""
Write-Host "Success! Task '$TaskName' installed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Management commands:" -ForegroundColor Cyan
Write-Host "  Run now:     schtasks /Run /TN `"$TaskName`"" -ForegroundColor White
Write-Host "  Stop:        schtasks /End /TN `"$TaskName`"" -ForegroundColor White
Write-Host "  Query:       schtasks /Query /TN `"$TaskName`" /V /FO LIST" -ForegroundColor White
Write-Host "  Uninstall:   schtasks /Delete /TN `"$TaskName`" /F" -ForegroundColor White
Write-Host ""
