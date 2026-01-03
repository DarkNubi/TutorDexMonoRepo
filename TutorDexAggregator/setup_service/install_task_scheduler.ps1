# PowerShell script to create Windows Task Scheduler tasks for the queue pipeline.
# Run this as Administrator to install the scheduled tasks.

$ErrorActionPreference = "Stop"

# Configuration
$CollectorTaskName = "TutorDex-Collector"
$WorkerTaskName = "TutorDex-Worker"
$CollectorDescription = "TutorDex raw Telegram collector (tail) - Auto-restart on boot"
$WorkerDescription = "TutorDex extraction queue worker - Auto-restart on boot"
$CollectorScriptPath = "$PSScriptRoot\start_collector_loop.bat"
$WorkerScriptPath = "$PSScriptRoot\start_extract_worker_loop.bat"
$WorkingDirectory = Split-Path -Parent $PSScriptRoot

Write-Host "Installing TutorDex Task Scheduler job..." -ForegroundColor Cyan
Write-Host "Collector script: $CollectorScriptPath" -ForegroundColor Gray
Write-Host "Worker script:    $WorkerScriptPath" -ForegroundColor Gray
Write-Host "Working directory: $WorkingDirectory" -ForegroundColor Gray
Write-Host ""

function Remove-IfExists($Name) {
    $ExistingTask = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($ExistingTask) {
        Write-Host "Task '$Name' already exists. Removing it..." -ForegroundColor Yellow
        Stop-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
    }
}

Remove-IfExists $CollectorTaskName
Remove-IfExists $WorkerTaskName

function New-TaskAction($ScriptPath) {
    return New-ScheduledTaskAction `
        -Execute "cmd.exe" `
        -Argument "/c `"$ScriptPath`"" `
        -WorkingDirectory $WorkingDirectory
}

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

# Register the tasks
Register-ScheduledTask `
    -TaskName $CollectorTaskName `
    -Description $CollectorDescription `
    -Action (New-TaskAction $CollectorScriptPath) `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Force

Register-ScheduledTask `
    -TaskName $WorkerTaskName `
    -Description $WorkerDescription `
    -Action (New-TaskAction $WorkerScriptPath) `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Force

Write-Host ""
Write-Host "Success! Tasks installed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "The task will:" -ForegroundColor Cyan
Write-Host "  - Start automatically when Windows boots" -ForegroundColor White
Write-Host "  - Run as user: $env:USERNAME" -ForegroundColor White
Write-Host "  - Auto-restart if it crashes (up to 3 times)" -ForegroundColor White
Write-Host "  - Keep running indefinitely (loop restarts)" -ForegroundColor White
Write-Host ""
Write-Host "Management commands:" -ForegroundColor Cyan
Write-Host "  Start now:   Start-ScheduledTask -TaskName '$CollectorTaskName'; Start-ScheduledTask -TaskName '$WorkerTaskName'" -ForegroundColor White
Write-Host "  Stop:        Stop-ScheduledTask -TaskName '$CollectorTaskName'; Stop-ScheduledTask -TaskName '$WorkerTaskName'" -ForegroundColor White
Write-Host "  Status:      Get-ScheduledTask -TaskName '$CollectorTaskName' | Format-List" -ForegroundColor White
Write-Host "  Status:      Get-ScheduledTask -TaskName '$WorkerTaskName' | Format-List" -ForegroundColor White
Write-Host "  Uninstall:   Unregister-ScheduledTask -TaskName '$CollectorTaskName' -Confirm:`$false; Unregister-ScheduledTask -TaskName '$WorkerTaskName' -Confirm:`$false" -ForegroundColor White
Write-Host ""
Write-Host "To start the task now, run:" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName '$CollectorTaskName'" -ForegroundColor White
Write-Host "  Start-ScheduledTask -TaskName '$WorkerTaskName'" -ForegroundColor White
Write-Host ""
