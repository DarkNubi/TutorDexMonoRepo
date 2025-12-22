param(
  # Comma-separated DuckDNS domains (without .duckdns.org), e.g. "tutordex-api,tutordex-studio"
  [string]$Domains = $env:DUCKDNS_DOMAINS,

  # DuckDNS token from https://www.duckdns.org/
  [string]$Token = $env:DUCKDNS_TOKEN,

  # Optional env file containing DUCKDNS_DOMAINS=... and DUCKDNS_TOKEN=...
  [string]$EnvFile = "",

  # If set, DuckDNS will use this IP instead of auto-detect.
  [string]$Ip = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Load-EnvFile([string]$path) {
  if (-not $path) { return }
  if (!(Test-Path $path)) { throw "Env file not found: $path" }
  Get-Content $path | ForEach-Object {
    $line = ($_ -as [string]).Trim()
    if (-not $line) { return }
    if ($line.StartsWith("#")) { return }
    $idx = $line.IndexOf("=")
    if ($idx -lt 1) { return }
    $k = $line.Substring(0, $idx).Trim()
    $v = $line.Substring($idx + 1).Trim()
    if ($k -and $v) { Set-Item -Path "Env:$k" -Value $v }
  }
}

Load-EnvFile $EnvFile
if (-not $Domains) { $Domains = $env:DUCKDNS_DOMAINS }
if (-not $Token) { $Token = $env:DUCKDNS_TOKEN }

if (-not $Domains) { throw "Missing -Domains (or DUCKDNS_DOMAINS)." }
if (-not $Token) { throw "Missing -Token (or DUCKDNS_TOKEN)." }

$domainsNorm = ($Domains -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }) -join ","
if (-not $domainsNorm) { throw "No valid domains in: $Domains" }

$ipParam = ""
if ($Ip) {
  $ipParam = "&ip=$([uri]::EscapeDataString($Ip))"
}

$url = "https://www.duckdns.org/update?domains=$([uri]::EscapeDataString($domainsNorm))&token=$([uri]::EscapeDataString($Token))$ipParam&verbose=true"
Write-Host "==> DuckDNS update: $domainsNorm"

try {
  $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 20
} catch {
  throw "DuckDNS update failed: $($_.Exception.Message)"
}

$body = ($resp.Content -as [string])?.Trim()
Write-Host $body
if ($resp.StatusCode -lt 200 -or $resp.StatusCode -ge 300) {
  throw "DuckDNS update failed status=$($resp.StatusCode)"
}

