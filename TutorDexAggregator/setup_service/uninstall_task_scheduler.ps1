# PowerShell script to remove the TutorDex Task Scheduler task
# Run this as Administrator

$ErrorActionPreference = "Stop"

$TaskName = "TutorDex-Aggregator"

Write-Host "Uninstalling TutorDex Task Scheduler job..." -ForegroundColor Cyan

$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($ExistingTask) {
    # Stop the task if running
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    
    # Remove the task
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    
    Write-Host "Success! Task '$TaskName' removed successfully!" -ForegroundColor Green
} else {
    Write-Host "Task '$TaskName' not found." -ForegroundColor Yellow
}
