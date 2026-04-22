param(
  [string]$ApiBase = "http://127.0.0.1:8010",
  [string]$FrontendBase = "http://127.0.0.1:5173",
  [string]$AccessToken = "",
  [string]$MonitorId = ""
)

$ErrorActionPreference = "Stop"

function Test-Step {
  param(
    [string]$Name,
    [scriptblock]$Body
  )
  try {
    & $Body
    Write-Host "[PASS] $Name" -ForegroundColor Green
    return $true
  } catch {
    Write-Host "[FAIL] $Name :: $($_.Exception.Message)" -ForegroundColor Red
    return $false
  }
}

function Invoke-JsonGet {
  param(
    [string]$Url,
    [string]$Token = ""
  )
  $headers = @{}
  if ($Token) {
    $headers["Authorization"] = "Bearer $Token"
  }
  return Invoke-RestMethod -Uri $Url -Method Get -Headers $headers -TimeoutSec 10
}

$results = @()

$results += Test-Step "Backend health endpoint" {
  $health = Invoke-JsonGet -Url "$ApiBase/api/v1/health"
  if (-not $health.status) {
    throw "Missing health status field"
  }
}

$results += Test-Step "Frontend root reachable" {
  $uri = [System.Uri]$FrontendBase
  $port = if ($uri.IsDefaultPort) { 80 } else { $uri.Port }
  $tcp = Test-NetConnection -ComputerName $uri.Host -Port $port -InformationLevel Quiet
  if (-not $tcp) {
    throw "Cannot connect to frontend $FrontendBase"
  }
}

if ($AccessToken) {
  $results += Test-Step "Auth /me endpoint" {
    $me = Invoke-JsonGet -Url "$ApiBase/api/v1/me" -Token $AccessToken
    if (-not $me.email) {
      throw "Missing user email"
    }
  }

  $results += Test-Step "Dashboard summary endpoint" {
    $summary = Invoke-JsonGet -Url "$ApiBase/api/v1/dashboard/summary" -Token $AccessToken
    if ($null -eq $summary.total_monitors) {
      throw "Missing total_monitors"
    }
  }

  $results += Test-Step "Monitors list endpoint" {
    $monitors = Invoke-JsonGet -Url "$ApiBase/api/v1/monitors?page=1&page_size=5" -Token $AccessToken
    if ($null -eq $monitors.total) {
      throw "Missing total field"
    }
  }

  if ($MonitorId) {
    $results += Test-Step "Monitor detail endpoint" {
      $detail = Invoke-JsonGet -Url "$ApiBase/api/v1/monitors/$MonitorId" -Token $AccessToken
      if (-not $detail.id) {
        throw "Missing monitor id"
      }
    }
    $results += Test-Step "Monitor checks endpoint" {
      [void](Invoke-JsonGet -Url "$ApiBase/api/v1/monitors/$MonitorId/checks?limit=10" -Token $AccessToken)
    }
    $results += Test-Step "Monitor uptime endpoint" {
      [void](Invoke-JsonGet -Url "$ApiBase/api/v1/monitors/$MonitorId/uptime" -Token $AccessToken)
    }
  } else {
    Write-Host "[INFO] Skip monitor-specific checks (set -MonitorId)." -ForegroundColor Yellow
  }
} else {
  Write-Host "[INFO] Skip authenticated checks (set -AccessToken)." -ForegroundColor Yellow
}

$passCount = ($results | Where-Object { $_ }).Count
$totalCount = $results.Count
Write-Host ""
Write-Host "Smoke summary: $passCount/$totalCount steps passed."
if ($passCount -ne $totalCount) {
  exit 1
}
