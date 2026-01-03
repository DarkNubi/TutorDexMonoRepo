# PowerShell script to remove the TutorDex Task Scheduler task
# Run this as Administrator

$ErrorActionPreference = "Stop"

$TaskNames = @("TutorDex-Collector", "TutorDex-Worker")

Write-Host "Uninstalling TutorDex Task Scheduler job..." -ForegroundColor Cyan

foreach ($TaskName in $TaskNames) {
    $ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($ExistingTask) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed task '$TaskName'." -ForegroundColor Green
    } else {
        Write-Host "Task '$TaskName' not found." -ForegroundColor Yellow
    }
}
