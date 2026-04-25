Param(
  [switch]$Strict,
  [int]$Retries = 1,
  [int]$RetryDelaySeconds = 2
)

$ErrorActionPreference = "Stop"

function Get-CeleryProcesses {
  Get-CimInstance Win32_Process |
    Where-Object {
      ($_.Name -in @("python.exe", "py.exe")) -and
      $_.CommandLine -match "celery -A app\.workers\.celery_app"
    }
}

for ($attempt = 1; $attempt -le [Math]::Max(1, $Retries); $attempt++) {
  $all = Get-CeleryProcesses
  $workers = $all | Where-Object { $_.CommandLine -match " worker " }
  $beats = $all | Where-Object { $_.CommandLine -match " beat " }

  Write-Host ("[runtime-check] attempt={0} total={1} worker={2} beat={3}" -f $attempt, $all.Count, $workers.Count, $beats.Count)
  foreach ($p in $all) {
    Write-Host ("  pid={0} name={1}" -f $p.ProcessId, $p.Name)
  }

  $missing = ($workers.Count -eq 0 -or $beats.Count -eq 0)
  $duplicate = ($workers.Count -gt 2 -or $beats.Count -gt 2)

  if (-not $missing -and -not $duplicate) {
    exit 0
  }

  if ($missing) {
    Write-Warning "[runtime-check] missing worker or beat process."
  }
  if ($duplicate) {
    Write-Warning "[runtime-check] possible duplicates detected (py/python wrappers included)."
  }

  if ($attempt -lt $Retries) {
    Start-Sleep -Seconds ([Math]::Max(1, $RetryDelaySeconds))
  }
}

if ($Strict) {
  throw "[runtime-check] strict mode failed: topology is not healthy."
}
