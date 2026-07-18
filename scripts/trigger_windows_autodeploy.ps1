$ErrorActionPreference = 'Stop'

$taskName = 'TutorDexAutodeploy'
$statusPath = 'D:\TutorDex.autodeploy\autodeploy.status.json'

Remove-Item -LiteralPath $statusPath -Force -ErrorAction SilentlyContinue
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(15)
Set-ScheduledTask -TaskName $taskName -Trigger $trigger | Out-Null

for ($i = 0; $i -lt 180; $i++) {
  Start-Sleep -Seconds 10
  if (Test-Path -LiteralPath $statusPath) {
    $status = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
    $status | ConvertTo-Json -Compress
    if ($status.success -eq $true) {
      exit 0
    }
    exit 1
  }
}

throw 'Timed out waiting for TutorDexAutodeploy task.'
