param(
  [string]$ApiBase = "http://127.0.0.1:8011",
  [string]$FrontendBase = "http://127.0.0.1:5173",
  [string]$AccessToken = "",
  [switch]$SkipRestart
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"

function Step([string]$name, [scriptblock]$body) {
  Write-Host "==> $name"
  . $body
}

if (-not $SkipRestart) {
  Step "Restart full stack (guarded)" {
    powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "restart_full_stack.ps1") -ForceKillPortOwners
  }
}

Step "Run packaged smoke-check.ps1" {
  $args = @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "smoke-check.ps1"),
    "-ApiBase", $ApiBase,
    "-FrontendBase", $FrontendBase
  )
  if ($AccessToken) {
    $args += @("-AccessToken", $AccessToken)
  }
  & powershell @args
}

if ($AccessToken) {
  Step "Extra runtime health assertion (authenticated)" {
    $headers = @{ Authorization = "Bearer $AccessToken" }
    $rh = Invoke-RestMethod -Uri "$ApiBase/api/v1/runtime/health" -Headers $headers -TimeoutSec 12
    if (-not $rh.status) {
      throw "Runtime health payload missing status"
    }
    $reasons = ""
    if ($rh.degraded_reasons) {
      $reasons = ($rh.degraded_reasons -join ",")
    }
    Write-Host ("runtime.status={0} reasons={1}" -f $rh.status, $reasons)
  }
} else {
  Write-Host "[INFO] Skipped authenticated runtime assertion (set -AccessToken)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Smoke gate PASS. Local is ready for push/deploy."
