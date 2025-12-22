param(
  [string]$DbContainer = "supabase-db",
  [string]$TargetDbName = "postgres",
  [string]$DumpFile = "infra/supabase_selfhost/backups/selfhost_public_$(Get-Date -Format yyyyMMdd_HHmmss).dump",
  [int]$Jobs = 4
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$dumpDir = Split-Path -Parent $DumpFile
if ($dumpDir) {
  New-Item -ItemType Directory -Force -Path $dumpDir | Out-Null
}

Write-Host "==> Verifying DB container is running: $DbContainer"
$running = docker ps --format "{{.Names}}" | Select-String -SimpleMatch $DbContainer
if (-not $running) {
  throw "Container '$DbContainer' not running."
}

$containerDump = "/tmp/selfhost_public.dump"
Write-Host "==> Dumping self-host DB (schema=public) to container path: $containerDump"
docker exec -i $DbContainer `
  pg_dump -U postgres -d $TargetDbName `
  --format=custom `
  --schema=public `
  --no-owner `
  --no-acl `
  --verbose `
  --file $containerDump | Out-Host

Write-Host "==> Copying dump to host: $DumpFile"
docker cp "${DbContainer}:$containerDump" $DumpFile

Write-Host "==> Done."
