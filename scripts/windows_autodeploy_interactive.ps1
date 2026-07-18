$ErrorActionPreference = 'Stop'

$source = 'D:\TutorDex'
$deploy = 'D:\TutorDex.autodeploy'
$statusPath = Join-Path $deploy 'autodeploy.status.json'
$logPath = Join-Path $deploy 'autodeploy.log'

Start-Transcript -Path $logPath -Force | Out-Null
try {
  Set-Location -LiteralPath $source
  git fetch origin main | Out-Host

  if (-not (Test-Path -LiteralPath $deploy)) {
    git worktree add --detach $deploy origin/main | Out-Host
  } else {
    git -C $deploy reset --hard origin/main | Out-Host
  }

  Copy-Item -LiteralPath (Join-Path $source '.env.prod') -Destination (Join-Path $deploy '.env.prod') -Force
  Copy-Item -LiteralPath (Join-Path $source 'TutorDexAggregator\.env.prod') -Destination (Join-Path $deploy 'TutorDexAggregator\.env.prod') -Force
  Copy-Item -LiteralPath (Join-Path $source 'TutorDexBackend\.env.prod') -Destination (Join-Path $deploy 'TutorDexBackend\.env.prod') -Force

  $secretDir = Join-Path $deploy 'TutorDexBackend\secrets'
  New-Item -ItemType Directory -Force -Path $secretDir | Out-Null
  $secretPath = Join-Path $secretDir 'firebase-admin-service-account.json'
  if (Test-Path -LiteralPath $secretPath -PathType Container) {
    Remove-Item -LiteralPath $secretPath -Recurse -Force
  }
  Copy-Item -LiteralPath (Join-Path $source 'TutorDexBackend\secrets\firebase-admin-service-account.json') -Destination $secretPath -Force

  docker context use desktop-linux | Out-Host
  $composeLogPath = Join-Path $deploy 'autodeploy-compose.log'
  docker compose -p tutordex-prod --env-file (Join-Path $deploy '.env.prod') up -d --build --pull=never --scale api-ingress=0 *> $composeLogPath
  $composeExitCode = $LASTEXITCODE
  Get-Content -LiteralPath $composeLogPath | Out-Host
  if ($composeExitCode -ne 0) {
    throw "docker compose failed with exit code $composeExitCode"
  }

  $status = [ordered]@{
    success = $true
    commit = (git -C $deploy rev-parse HEAD).Trim()
    completedAt = (Get-Date).ToUniversalTime().ToString('o')
  }
  $status | ConvertTo-Json -Compress | Set-Content -LiteralPath $statusPath -Encoding ascii
} catch {
  $status = [ordered]@{
    success = $false
    completedAt = (Get-Date).ToUniversalTime().ToString('o')
    error = $_.Exception.Message
  }
  $status | ConvertTo-Json -Compress | Set-Content -LiteralPath $statusPath -Encoding ascii
  throw
} finally {
  Stop-Transcript | Out-Null
}
