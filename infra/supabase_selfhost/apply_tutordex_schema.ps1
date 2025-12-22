param(
  [string]$DbContainer = "supabase-db",
  [string]$DbName = "postgres"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-PsqlFile {
  param(
    [Parameter(Mandatory = $true)][string]$Path
  )
  if (!(Test-Path $Path)) {
    throw "SQL file not found: $Path"
  }
  Write-Host "==> Applying $Path"
  $sql = Get-Content -Raw $Path
  $sqlBytes = [System.Text.Encoding]::UTF8.GetBytes($sql)
  $tmp = [System.IO.Path]::GetTempFileName()
  [System.IO.File]::WriteAllBytes($tmp, $sqlBytes)
  try {
    Get-Content -Raw $tmp | docker exec -i $DbContainer psql -U postgres -d $DbName -v ON_ERROR_STOP=1 | Out-Host
  } finally {
    Remove-Item -Force $tmp -ErrorAction SilentlyContinue
  }
}

Write-Host "==> Verifying DB container is running: $DbContainer"
$running = docker ps --format "{{.Names}}" | Select-String -SimpleMatch $DbContainer
if (-not $running) {
  throw "Container '$DbContainer' not running. Start Supabase first (docker compose up -d)."
}

Invoke-PsqlFile "TutorDexAggregator/supabase_schema_full.sql"

$migrationFiles = Get-ChildItem -File "TutorDexAggregator/migrations" -Filter "*.sql" | Sort-Object Name
foreach ($f in $migrationFiles) {
  Invoke-PsqlFile $f.FullName
}

Write-Host "==> Done."

