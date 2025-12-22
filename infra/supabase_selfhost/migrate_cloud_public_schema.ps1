param(
  # Supabase Cloud DB URL (get from Supabase Project Settings -> Database).
  # Example:
  #   postgresql://postgres:<PASSWORD>@db.<project-ref>.supabase.co:5432/postgres?sslmode=require
  [string]$CloudDatabaseUrl = $env:TDX_CLOUD_DATABASE_URL,

  # Dump file written on the machine running this script.
  [string]$DumpFile = "infra/supabase_selfhost/backups/tutordex_public_data.dump",
  # Only run pg_dump and exit (does not restore).
  [switch]$DumpOnly,
  # Only restore from an existing dump file (does not re-dump).
  [switch]$RestoreOnly,

  # Restore target inside self-hosted Supabase.
  [string]$DbContainer = "supabase-db",
  [string]$TargetDbName = "postgres",
  # Path to the self-hosted Supabase docker `.env` file (used to read POSTGRES_PASSWORD for pg_restore).
  [string]$SupabaseDockerEnvPath = "",
  # If true, truncates all tables in `public` before restore (destructive).
  [switch]$TruncatePublicFirst,

  # Performance (custom format only).
  # Note: `pg_restore --jobs > 1` can violate FK ordering on data-only restores; prefer 1 for reliability.
  [int]$Jobs = 1,

  # Optional DNS server for the pg_dump container (useful if Docker DNS can't resolve Supabase Cloud host).
  # Examples: "1.1.1.1" or "8.8.8.8"
  [string]$DnsServer = "",

  # Force IPv4 by resolving the hostname to an A record and using the IP in the connection string.
  # Useful when Docker/WSL lacks IPv6 connectivity and Postgres resolves to AAAA first.
  [switch]$ForceIPv4,

  # Use Supabase Cloud connection pooler (IPv4) instead of the direct db.<ref>.supabase.co host.
  # Useful when Docker/WSL cannot reach IPv6-only DB endpoints.
  [switch]$UsePooler,
  # Supabase project region for the pooler endpoint (check Supabase dashboard if unsure).
  # Common values: ap-southeast-1, us-east-1, eu-west-1. Use "auto" to try common regions.
  [string]$PoolerRegion = "auto",
  # Supabase pooler transaction port (default 6543).
  [int]$PoolerPort = 6543,
  # Supabase pooler shard/index. Some projects resolve via aws-1-<region>.pooler.supabase.com.
  # Use "auto" to try 0 and 1.
  [string]$PoolerAwsIndex = "auto"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SCRIPT_VERSION = "2025-12-19b"
Write-Host "==> migrate_cloud_public_schema.ps1 version: $SCRIPT_VERSION"

$supabaseEnvCandidates = @()
if ($SupabaseDockerEnvPath) { $supabaseEnvCandidates += $SupabaseDockerEnvPath }
$supabaseEnvCandidates += @(
  (Join-Path (Get-Location) ".env"),
  "C:\\supabase-selfhost\\supabase\\docker\\.env",
  "D:\\supabase-selfhost\\supabase\\docker\\.env"
)
$supabaseEnvCandidates = $supabaseEnvCandidates | Where-Object { $_ } | Select-Object -Unique

$resolvedSupabaseEnvPath = $supabaseEnvCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($resolvedSupabaseEnvPath) {
  $SupabaseDockerEnvPath = $resolvedSupabaseEnvPath
}

if ($DumpOnly -and $RestoreOnly) {
  throw "Choose only one: -DumpOnly or -RestoreOnly."
}

$needsCloud = -not $RestoreOnly
if ($needsCloud -and -not $CloudDatabaseUrl) {
  throw "Missing CloudDatabaseUrl. Pass -CloudDatabaseUrl or set `$env:TDX_CLOUD_DATABASE_URL."
}

$effectiveDbUrl = $CloudDatabaseUrl

function _try_extract_project_ref([string]$dbHost) {
  $m = [regex]::Match($dbHost, '^(?:db\.)?(?<ref>[a-z0-9]{10,})\.supabase\.co$', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
  if ($m.Success) { return $m.Groups["ref"].Value }
  return ""
}

function _test_pooler_connection {
  param(
    [Parameter(Mandatory = $true)][string]$PoolerHost,
    [Parameter(Mandatory = $true)][int]$PoolerPort,
    [Parameter(Mandatory = $true)][string]$User,
    [Parameter(Mandatory = $true)][string]$Password,
    [Parameter(Mandatory = $true)][string]$DbName,
    [Parameter(Mandatory = $true)][string]$QueryString,
    [string]$DnsServer = ""
  )

  $connNoPass = "postgresql://$User@$PoolerHost`:$PoolerPort/$DbName$QueryString"
  $dockerArgs = @("run", "--rm")
  if ($DnsServer) {
    $dockerArgs += @("--dns", $DnsServer)
  }
  $dockerArgs += @("-e", "PGPASSWORD=$Password", "postgres:17", "bash", "-lc", "PGCONNECT_TIMEOUT=6 psql `"$connNoPass`" -v ON_ERROR_STOP=1 -c 'select 1' >/dev/null")

  & docker @dockerArgs 2>$null
  return ($LASTEXITCODE -eq 0)
}

function _read_env_kv {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Key
  )
  if (!(Test-Path $Path)) { return "" }
  $lines = Get-Content $Path -ErrorAction Stop
  foreach ($line in $lines) {
    $s = ($line -as [string]).Trim()
    if (-not $s) { continue }
    if ($s.StartsWith("#")) { continue }
    $idx = $s.IndexOf("=")
    if ($idx -lt 1) { continue }
    $k = $s.Substring(0, $idx).Trim()
    if ($k -ne $Key) { continue }
    $v = $s.Substring($idx + 1).Trim()
    # strip optional surrounding quotes
    if ($v.StartsWith('"') -and $v.EndsWith('"') -and $v.Length -ge 2) { $v = $v.Substring(1, $v.Length - 2) }
    if ($v.StartsWith("'") -and $v.EndsWith("'") -and $v.Length -ge 2) { $v = $v.Substring(1, $v.Length - 2) }
    return $v
  }
  return ""
}

function _get_container_network_name {
  param([Parameter(Mandatory = $true)][string]$ContainerName)
  $json = docker inspect $ContainerName | ConvertFrom-Json
  if (-not $json) { throw "docker inspect returned no data for $ContainerName" }
  $nets = $json[0].NetworkSettings.Networks
  if (-not $nets) { throw "No networks found for container: $ContainerName" }
  $names = @($nets.PSObject.Properties | ForEach-Object { $_.Name })
  if (-not $names -or $names.Count -lt 1) { throw "No network names found for container: $ContainerName" }
  return $names[0]
}

function _exec_psql {
  param(
    [Parameter(Mandatory = $true)][string]$Sql
  )
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($Sql)
  $tmp = [System.IO.Path]::GetTempFileName()
  [System.IO.File]::WriteAllBytes($tmp, $bytes)
  try {
    Get-Content -Raw $tmp | docker exec -i $DbContainer psql -U postgres -d $TargetDbName -v ON_ERROR_STOP=1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
      throw "psql failed (exit=$LASTEXITCODE)"
    }
  } finally {
    Remove-Item -Force $tmp -ErrorAction SilentlyContinue
  }
}

function _validate_target_schema {
  # Validate the self-host DB has the columns/tables expected by the cloud dump and by this repo.
  $sql = @'
do $$
begin
  if not exists (
    select 1 from information_schema.columns
    where table_schema='public' and table_name='assignments' and column_name='parse_quality_score'
  ) then
    raise exception 'missing column public.assignments.parse_quality_score (apply TutorDex migrations first)';
  end if;

  if not exists (
    select 1 from information_schema.tables
    where table_schema='public' and table_name='telegram_extractions'
  ) then
    raise exception 'missing table public.telegram_extractions (apply TutorDex migrations first)';
  end if;

  if not exists (
    select 1 from information_schema.tables
    where table_schema='public' and table_name='telegram_messages_raw'
  ) then
    raise exception 'missing table public.telegram_messages_raw (apply TutorDex migrations first)';
  end if;
end;
$$;
'@
  _exec_psql -Sql $sql
}

if ($needsCloud -and $UsePooler) {
  try {
    $u = [Uri]$effectiveDbUrl
    $dbHost = $u.Host
    if (-not $dbHost) { throw "No host in URL" }

    $ref = _try_extract_project_ref $dbHost
    if (-not $ref) { throw "Could not extract Supabase project ref from host: $dbHost" }

    $user = $u.UserInfo.Split(":")[0]
    $pass = ""
    $parts = $u.UserInfo.Split(":", 2)
    if ($parts.Length -eq 2) { $pass = $parts[1] }

    # Pooler commonly requires username like: postgres.<project_ref>
    if ($user -eq "postgres") {
      $user = "postgres.$ref"
    }

    $dbName = $u.AbsolutePath.TrimStart("/")
    if (-not $dbName) { $dbName = "postgres" }

    $qs = $u.Query
    if (-not $qs) { $qs = "?sslmode=require" }
    elseif (-not $qs.ToLowerInvariant().Contains("sslmode=")) { $qs = $qs + "&sslmode=require" }

    $userEnc = [uri]::EscapeDataString($user)
    $passEnc = [uri]::EscapeDataString($pass)

    $regions = @()
    if ($PoolerRegion -and $PoolerRegion.Trim().ToLowerInvariant() -ne "auto") {
      $regions = @($PoolerRegion.Trim())
    } else {
      # Common Supabase regions. Add more if needed.
      $regions = @(
        "ap-southeast-1",
        "ap-southeast-2",
        "ap-south-1",
        "ap-northeast-1",
        "ap-northeast-2",
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
        "eu-west-1",
        "eu-central-1",
        "sa-east-1",
        "ca-central-1"
      )
    }

    $awsIndexes = @()
    if ($PoolerAwsIndex -and $PoolerAwsIndex.Trim().ToLowerInvariant() -ne "auto") {
      $awsIndexes = @($PoolerAwsIndex.Trim())
    } else {
      $awsIndexes = @("0", "1")
    }

    $lastErr = ""
    foreach ($r in $regions) {
      foreach ($idx in $awsIndexes) {
        $poolerHost = "aws-$idx-$r.pooler.supabase.com"
        $candidate = "postgresql://$userEnc`:$passEnc@$poolerHost`:$PoolerPort/$dbName$qs"

        $ok = _test_pooler_connection -PoolerHost $poolerHost -PoolerPort $PoolerPort -User $user -Password $pass -DbName $dbName -QueryString $qs -DnsServer $DnsServer
        if ($ok) {
          $effectiveDbUrl = $candidate
          Write-Host "==> UsePooler enabled: $dbHost -> $($poolerHost):$PoolerPort (region=$r, user=$user)"
          $lastErr = ""
          break
        } else {
          $lastErr = "Pooler test failed for region=$r host=$poolerHost"
        }
      }
      if (-not $lastErr) { break }
    }

    if ($lastErr) {
      throw $lastErr
    }
  } catch {
    throw "UsePooler failed: $($_.Exception.Message)"
  }
}

if ($needsCloud -and $ForceIPv4) {
  try {
    $u = [Uri]$effectiveDbUrl
    $dbHost = $u.Host
    if (-not $dbHost) { throw "No host in URL" }

    $records = Resolve-DnsName -Name $dbHost -Type A -ErrorAction Stop
    # Resolve-DnsName can return a CNAME record first; pick the first entry that actually has an IP.
    $ipRec = $records | Where-Object { $_.PSObject.Properties.Name -contains "IPAddress" -and $_.IPAddress } | Select-Object -First 1
    $ipv4 = $null
    if ($ipRec -and ($ipRec.PSObject.Properties.Name -contains "IPAddress")) {
      $ipv4 = $ipRec.IPAddress
    }
    if (-not $ipv4) { throw "No A record found for $dbHost" }

    # Replace only the host portion; keep user/pass, port, db name, and query string.
    $effectiveDbUrl = $effectiveDbUrl.Replace($dbHost, $ipv4)
    Write-Host "==> ForceIPv4 enabled: $dbHost -> $ipv4"
  } catch {
    throw "ForceIPv4 failed: $($_.Exception.Message)"
  }
}

$dumpDir = Split-Path -Parent $DumpFile
if ($dumpDir) {
  New-Item -ItemType Directory -Force -Path $dumpDir | Out-Null
}

Write-Host "==> Verifying DB container is running: $DbContainer"
$running = docker ps --format "{{.Names}}" | Select-String -SimpleMatch $DbContainer
if (-not $running) {
  throw "Container '$DbContainer' not running. Start Supabase first (docker compose up -d)."
}

$netName = _get_container_network_name $DbContainer
$pgPass = _read_env_kv -Path $SupabaseDockerEnvPath -Key "POSTGRES_PASSWORD"
if (-not $pgPass) {
  $cands = ($supabaseEnvCandidates -join ", ")
  throw "Could not read POSTGRES_PASSWORD from '$SupabaseDockerEnvPath'. Set -SupabaseDockerEnvPath to your Supabase docker .env path. Tried: $cands"
}

if (-not $RestoreOnly) {
  Write-Host "==> Dumping Supabase Cloud (schema=public, data-only) to: $DumpFile"
  $dockerDnsArgs = @()
  if ($DnsServer) {
    $dockerDnsArgs += @("--dns", $DnsServer)
  }

  docker run --rm `
    @dockerDnsArgs `
    -v "${PWD}:/work" -w /work `
    postgres:17 `
    pg_dump "$effectiveDbUrl" `
    --format=custom `
    --schema=public `
    --data-only `
    --no-owner `
    --no-acl `
    --verbose `
    --file "/work/$DumpFile"

  if ($LASTEXITCODE -ne 0) {
    throw "pg_dump failed (exit=$LASTEXITCODE). Check DNS/network and the CloudDatabaseUrl."
  }
}

try {
  $fi = Get-Item -LiteralPath $DumpFile -ErrorAction Stop
  if ($fi.Length -lt 1024) {
    throw "Dump file looks too small ($($fi.Length) bytes): $DumpFile"
  }
  Write-Host "==> Dump file ready: $DumpFile ($([Math]::Round($fi.Length/1MB,2)) MB)"
} catch {
  throw "Dump file missing/invalid: $DumpFile. Error: $($_.Exception.Message)"
}

if ($DumpOnly) {
  Write-Host "==> DumpOnly set; skipping restore."
  Write-Host "To restore later: powershell -ExecutionPolicy Bypass -File .\\infra\\supabase_selfhost\\migrate_cloud_public_schema.ps1 -RestoreOnly -DumpFile `"$DumpFile`""
  Write-Host "==> Done."
  exit 0
}

Write-Host "==> Validating target schema (expected TutorDex migrations applied)"
_validate_target_schema

if ($TruncatePublicFirst) {
  Write-Host "==> Truncating all public tables (CASCADE)"
  $truncateSql = @'
do $$
declare r record;
begin
  for r in (select tablename from pg_tables where schemaname='public') loop
    execute format('truncate table public.%I restart identity cascade;', r.tablename);
  end loop;
end;
$$;
'@
  _exec_psql -Sql $truncateSql
}

Write-Host "==> Restoring into self-hosted DB via postgres:17 tools on docker network '$netName'"
docker run --rm `
  --network $netName `
  -e "PGPASSWORD=$pgPass" `
  -v "${PWD}:/work" -w /work `
  postgres:17 `
  bash -lc "set -euo pipefail; pg_restore --data-only --no-owner --no-acl --verbose -f - '/work/$DumpFile' | sed '/^SET transaction_timeout = 0;$/d' | psql -h '$DbContainer' -p 5432 -U postgres -d '$TargetDbName' -v ON_ERROR_STOP=1" | Out-Host

if ($LASTEXITCODE -ne 0) {
  throw "Restore failed (exit=$LASTEXITCODE)."
}

Write-Host "==> Done."
