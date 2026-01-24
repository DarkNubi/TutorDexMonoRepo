# Persistent Tailscale Serve for Homepage (Windows)
# Runs `tailscale serve` in a restart loop and logs output.

$ErrorActionPreference = 'Continue'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $ScriptDir '..\logs' | Resolve-Path -Relative
$LogDir = Join-Path $ScriptDir '..\logs'
if (-not (Test-Path -Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$LogFile = Join-Path $LogDir 'tailscale-serve-homepage.log'

function Log($msg) {
    $time = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    "$time`t$msg" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

Log 'Starting tailscale-serve-homepage script'

while ($true) {
    try {
        Log 'Checking tailscale status'
        $status = & tailscale status 2>&1
        if ($LASTEXITCODE -ne 0) {
            Log "tailscale not ready: $status"
            Start-Sleep -Seconds 10
            continue
        }

        Log 'Launching: tailscale serve --https=443 --service=svc:homepage http://localhost:7575'
        & tailscale serve --https=443 --service=svc:homepage http://localhost:7575 2>&1 | ForEach-Object { Log $_ }
        Log 'tailscale serve exited; will restart after delay'
    } catch {
        Log "Exception: $_"
    }
    Start-Sleep -Seconds 5
}
