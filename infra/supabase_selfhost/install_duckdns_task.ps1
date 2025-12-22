param(
  [Parameter(Mandatory = $true)][string]$EnvFile,
  [string]$TaskName = "TutorDex-DuckDNS-Update",
  [int]$Minutes = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path ".").Path
$scriptPath = Join-Path $repoRoot "infra/supabase_selfhost/duckdns_update.ps1"

if (!(Test-Path $scriptPath)) {
  throw "duckdns_update.ps1 not found at: $scriptPath"
}
if (!(Test-Path $EnvFile)) {
  throw "Env file not found: $EnvFile"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -EnvFile `"$EnvFile`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $Minutes) -RepetitionDuration ([TimeSpan]::MaxValue)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew

try {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
} catch {}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Updates DuckDNS domains for TutorDex Supabase self-host."
Write-Host "==> Installed scheduled task: $TaskName (every $Minutes minutes)"
Write-Host "Start it now: Start-ScheduledTask -TaskName `"$TaskName`""

