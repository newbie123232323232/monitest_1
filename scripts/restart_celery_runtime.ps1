Param(
  [switch]$NoStart
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"

function Get-CeleryProcesses {
  Get-CimInstance Win32_Process |
    Where-Object {
      ($_.Name -in @("python.exe", "py.exe")) -and
      $_.CommandLine -match "celery -A app\.workers\.celery_app"
    }
}

Write-Host "[runtime] stopping existing celery worker/beat processes..."
$running = Get-CeleryProcesses
foreach ($p in $running) {
  try {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
    Write-Host ("  stopped pid={0}" -f $p.ProcessId)
  } catch {
    Write-Warning ("  failed to stop pid={0}: {1}" -f $p.ProcessId, $_.Exception.Message)
  }
}

Start-Sleep -Seconds 1
$remaining = Get-CeleryProcesses
if ($remaining.Count -gt 0) {
  throw "[runtime] duplicate celery processes still running; abort for safety."
}

if ($NoStart) {
  Write-Host "[runtime] stop-only mode completed."
  exit 0
}

Write-Host "[runtime] starting worker (solo, no gossip/mingle)..."
Start-Process `
  -FilePath "py" `
  -ArgumentList @(
    "-3", "-m", "celery", "-A", "app.workers.celery_app",
    "worker", "-P", "solo", "-l", "info", "--without-gossip", "--without-mingle"
  ) `
  -WorkingDirectory $backendDir

Start-Sleep -Seconds 1
Write-Host "[runtime] starting beat..."
Start-Process `
  -FilePath "py" `
  -ArgumentList @(
    "-3", "-m", "celery", "-A", "app.workers.celery_app",
    "beat", "-l", "info"
  ) `
  -WorkingDirectory $backendDir

Start-Sleep -Seconds 2
$after = Get-CeleryProcesses
Write-Host ("[runtime] celery processes after restart: {0}" -f $after.Count)
foreach ($p in $after) {
  Write-Host ("  pid={0} name={1}" -f $p.ProcessId, $p.Name)
}

Write-Host "[runtime] done."
