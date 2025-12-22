# PowerShell script to create Windows Task Scheduler task for TutorDex
# Run this as Administrator to install the scheduled task

$ErrorActionPreference = "Stop"

# Configuration
$TaskName = "TutorDex-Aggregator"
$TaskDescription = "TutorDex Telegram Assignment Aggregator - Auto-restart on boot"
$ScriptPath = "$PSScriptRoot\start_tutordex_loop.bat"
$WorkingDirectory = Split-Path -Parent $PSScriptRoot

Write-Host "Installing TutorDex Task Scheduler job..." -ForegroundColor Cyan
Write-Host "Script path: $ScriptPath" -ForegroundColor Gray
Write-Host "Working directory: $WorkingDirectory" -ForegroundColor Gray
Write-Host ""

# Check if task already exists
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($ExistingTask) {
    Write-Host "Task '$TaskName' already exists. Removing it..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create the scheduled task action
$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$ScriptPath`"" `
    -WorkingDirectory $WorkingDirectory

# Create the trigger (at system startup)
$Trigger = New-ScheduledTaskTrigger -AtStartup

# Create settings for the task
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0)

# Get current user
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

# Register the task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Description $TaskDescription `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Force

Write-Host ""
Write-Host "Success! Task '$TaskName' installed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "The task will:" -ForegroundColor Cyan
Write-Host "  - Start automatically when Windows boots" -ForegroundColor White
Write-Host "  - Run as user: $env:USERNAME" -ForegroundColor White
Write-Host "  - Auto-restart if it crashes (up to 3 times)" -ForegroundColor White
Write-Host "  - Keep running indefinitely (loop restarts)" -ForegroundColor White
Write-Host ""
Write-Host "Management commands:" -ForegroundColor Cyan
Write-Host "  Start now:   Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
Write-Host "  Stop:        Stop-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
Write-Host "  Status:      Get-ScheduledTask -TaskName '$TaskName' | Format-List" -ForegroundColor White
Write-Host "  Uninstall:   Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false" -ForegroundColor White
Write-Host ""
Write-Host "To start the task now, run:" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
Write-Host ""
