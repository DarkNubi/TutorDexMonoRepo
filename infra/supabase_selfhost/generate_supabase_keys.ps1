param(
  [Parameter(Mandatory = $true)][string]$JwtSecret,
  [int]$YearsValid = 10,
  [string]$Issuer = "supabase-selfhost"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function To-Base64Url([byte[]]$bytes) {
  $b64 = [Convert]::ToBase64String($bytes)
  return $b64.TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function New-JwtHs256 {
  param(
    [Parameter(Mandatory = $true)][hashtable]$Header,
    [Parameter(Mandatory = $true)][hashtable]$Payload,
    [Parameter(Mandatory = $true)][string]$Secret
  )

  $headerJson = ($Header | ConvertTo-Json -Compress)
  $payloadJson = ($Payload | ConvertTo-Json -Compress)

  $headerB64 = To-Base64Url ([System.Text.Encoding]::UTF8.GetBytes($headerJson))
  $payloadB64 = To-Base64Url ([System.Text.Encoding]::UTF8.GetBytes($payloadJson))
  $toSign = "$headerB64.$payloadB64"

  $hmac = New-Object System.Security.Cryptography.HMACSHA256
  $hmac.Key = [System.Text.Encoding]::UTF8.GetBytes($Secret)
  $sigBytes = $hmac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($toSign))
  $sigB64 = To-Base64Url $sigBytes
  return "$toSign.$sigB64"
}

$now = [DateTimeOffset]::UtcNow
$iat = [int]$now.ToUnixTimeSeconds()
$exp = [int]$now.AddYears([Math]::Max(1, $YearsValid)).ToUnixTimeSeconds()

$header = @{ alg = "HS256"; typ = "JWT" }

$anonPayload = @{ role = "anon"; iss = $Issuer; iat = $iat; exp = $exp }
$servicePayload = @{ role = "service_role"; iss = $Issuer; iat = $iat; exp = $exp }

$anonKey = New-JwtHs256 -Header $header -Payload $anonPayload -Secret $JwtSecret
$serviceKey = New-JwtHs256 -Header $header -Payload $servicePayload -Secret $JwtSecret

Write-Output ("ANON_KEY=" + $anonKey)
Write-Output ("SERVICE_ROLE_KEY=" + $serviceKey)
