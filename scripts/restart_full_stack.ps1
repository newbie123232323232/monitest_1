Param(
  [switch]$NoFrontend,
  [switch]$NoBackend,
  [switch]$NoCelery,
  [switch]$ForceKillPortOwners,
  [int]$BackendPort = 8011,
  [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"

function Get-CommandLineProcesses([string]$pattern) {
  Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -in @("python.exe", "py.exe", "node.exe")) -and
    $_.CommandLine -match $pattern
  }
}

function Stop-ByPattern([string]$name, [string]$pattern) {
  $procs = Get-CommandLineProcesses -pattern $pattern
  if (-not $procs) {
    Write-Host ("[restart] no {0} process found." -f $name)
    return
  }
  foreach ($p in $procs) {
    try {
      Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
      Write-Host ("[restart] stopped {0} pid={1}" -f $name, $p.ProcessId)
    } catch {
      Write-Warning ("[restart] failed stopping {0} pid={1}: {2}" -f $name, $p.ProcessId, $_.Exception.Message)
    }
  }
}

function Ensure-PortFree([int]$port, [string]$ownerName) {
  $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  if (-not $listeners) {
    Write-Host ("[guard] port {0} free ({1})" -f $port, $ownerName)
    return
  }

  $pids = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
  $blocked = @()
  foreach ($ownerPid in $pids) {
    try {
      $proc = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $ownerPid) -ErrorAction Stop
      if ($proc) { $blocked += $proc }
    } catch {
      # ignore dead pid race
    }
  }

  if (-not $ForceKillPortOwners) {
    $who = ($blocked | ForEach-Object { "{0}({1})" -f $_.Name, $_.ProcessId }) -join ", "
    if (-not $who) { $who = ("pid(s): {0}" -f (($pids | ForEach-Object { "$_" }) -join ", ")) }
    if (-not $who) { $who = "unknown process" }
    throw ("[guard] port {0} is already in use by {1}. Use -ForceKillPortOwners to terminate it explicitly." -f $port, $who)
  }

  foreach ($proc in $blocked) {
    try {
      Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
      Write-Host ("[guard] killed port owner {0}({1}) on {2}" -f $proc.Name, $proc.ProcessId, $port)
    } catch {
      throw ("[guard] failed to kill process {0}({1}) on port {2}: {3}" -f $proc.Name, $proc.ProcessId, $port, $_.Exception.Message)
    }
  }
}

function Wait-PortListen([int]$port, [string]$serviceName, [int]$timeoutSeconds = 20) {
  $deadline = (Get-Date).AddSeconds($timeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
      Write-Host ("[restart] {0} is listening on port {1}" -f $serviceName, $port)
      return
    }
    Start-Sleep -Milliseconds 500
  }
  throw ("[restart] {0} did not bind to port {1} within {2}s." -f $serviceName, $port, $timeoutSeconds)
}

Write-Host "[restart] stopping existing processes..."
if (-not $NoBackend) {
  Stop-ByPattern -name "backend-api" -pattern "uvicorn app\.main:app"
}
if (-not $NoFrontend) {
  Stop-ByPattern -name "frontend-vite" -pattern "vite"
}
if (-not $NoCelery) {
  Stop-ByPattern -name "celery-worker/beat" -pattern "celery -A app\.workers\.celery_app"
}

Start-Sleep -Seconds 1

if (-not $NoBackend) {
  Ensure-PortFree -port $backendPort -ownerName "backend api"
}
if (-not $NoFrontend) {
  Ensure-PortFree -port $frontendPort -ownerName "frontend vite"
}

Write-Host "[restart] starting services..."
if (-not $NoBackend) {
  Start-Process -FilePath "py" -ArgumentList @("-3", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$backendPort") -WorkingDirectory $backendDir
  Write-Host ("[restart] backend started on 127.0.0.1:{0}" -f $backendPort)
}
if (-not $NoCelery) {
  Start-Process -FilePath "py" -ArgumentList @("-3", "-m", "celery", "-A", "app.workers.celery_app", "worker", "-P", "solo", "-l", "info", "--without-gossip", "--without-mingle") -WorkingDirectory $backendDir
  Start-Process -FilePath "py" -ArgumentList @("-3", "-m", "celery", "-A", "app.workers.celery_app", "beat", "-l", "info") -WorkingDirectory $backendDir
  Write-Host "[restart] celery worker + beat started"
}
if (-not $NoFrontend) {
  Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", "set MONI_DEV_API_PORT=$backendPort&& npx vite --host 127.0.0.1 --port $frontendPort --strictPort") -WorkingDirectory $frontendDir
  Write-Host ("[restart] frontend started on 127.0.0.1:{0}" -f $frontendPort)
}

Start-Sleep -Seconds 2

Write-Host "[restart] verifying port guards..."
if (-not $NoBackend) {
  Wait-PortListen -port $backendPort -serviceName "backend api" -timeoutSeconds 20
}
if (-not $NoFrontend) {
  Wait-PortListen -port $frontendPort -serviceName "frontend vite" -timeoutSeconds 25
}

if (-not $NoCelery) {
  powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "check_celery_runtime.ps1") -Strict -Retries 4 -RetryDelaySeconds 2
}

Write-Host "[restart] full-stack restart completed."
