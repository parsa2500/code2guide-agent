<#
.SYNOPSIS
  Stop Code2Guide stack started by scripts/dev-up.ps1 (API + UI + optional Qdrant).
#>
[CmdletBinding()]
param(
  [switch]$KeepQdrant,
  [int]$ApiPort = 8000,
  [int]$UiPort = 5173
)

$ErrorActionPreference = "Continue"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$SessionFile = Join-Path $Root ".code2guide\dev-session.json"

function Stop-PortListeners([int]$Port) {
  $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  foreach ($c in @($conns)) {
    if ($c.OwningProcess -and $c.OwningProcess -gt 0) {
      Write-Host "  stop pid $($c.OwningProcess) on :$Port"
      & taskkill /PID $c.OwningProcess /T /F 2>$null | Out-Null
    }
  }
}

function Stop-Tree([int]$ProcessId) {
  if ($ProcessId -le 0) { return }
  & taskkill /PID $ProcessId /T /F 2>$null | Out-Null
}

Write-Host "==> Code2Guide DOWN" -ForegroundColor Cyan

$apiPid = $null
$uiPid = $null
$hadQdrant = $true

if (Test-Path $SessionFile) {
  try {
    $s = Get-Content $SessionFile -Raw -Encoding utf8 | ConvertFrom-Json
    $apiPid = [int]$s.apiPid
    $uiPid = [int]$s.uiPid
    if ($null -ne $s.apiPort) { $ApiPort = [int]$s.apiPort }
    if ($null -ne $s.uiPort) { $UiPort = [int]$s.uiPort }
    if ($null -ne $s.qdrant) { $hadQdrant = [bool]$s.qdrant }
  } catch {
    Write-Warning "Could not parse session file; falling back to ports."
  }
}

Write-Host "-> Stop API / UI processes" -ForegroundColor Yellow
if ($apiPid) { Stop-Tree $apiPid }
if ($uiPid) { Stop-Tree $uiPid }

# Uvicorn --reload and npm spawn children that may keep the port
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    ($_.Name -match 'python|uvicorn') -and ($_.CommandLine -match 'uvicorn|src\.api\.main')
  } |
  ForEach-Object {
    Write-Host "  stop python/uvicorn pid $($_.ProcessId)"
    Stop-Tree ([int]$_.ProcessId)
  }

Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'vite|code2giude-agent\\frontend|code2guide-frontend' } |
  ForEach-Object {
    Write-Host "  stop orphan node pid $($_.ProcessId)"
    Stop-Tree ([int]$_.ProcessId)
  }

Stop-PortListeners $ApiPort
Stop-PortListeners $UiPort
Start-Sleep -Milliseconds 500
Stop-PortListeners $ApiPort
Stop-PortListeners $UiPort

if (-not $KeepQdrant -and $hadQdrant) {
  Write-Host "-> Qdrant (docker compose down)" -ForegroundColor Yellow
  docker compose down
}

if (Test-Path $SessionFile) {
  Remove-Item $SessionFile -Force -ErrorAction SilentlyContinue
}

Write-Host "Stopped." -ForegroundColor Green
