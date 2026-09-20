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

function Test-ProcessAlive([int]$ProcessId) {
  if ($ProcessId -le 0) { return $false }
  return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Invoke-TaskKill([int]$ProcessId) {
  if (-not (Test-ProcessAlive $ProcessId)) { return $false }
  cmd.exe /c "taskkill /PID $ProcessId /T /F >nul 2>&1" | Out-Null
  return -not (Test-ProcessAlive $ProcessId)
}

function Get-ListenPids([int]$Port) {
  $pids = @()
  try {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in @($conns)) {
      if ($c.OwningProcess -and $c.OwningProcess -gt 0) {
        $pids += [int]$c.OwningProcess
      }
    }
  } catch {}
  return @($pids | Select-Object -Unique)
}

function Stop-PortListeners([int]$Port) {
  foreach ($procId in @(Get-ListenPids $Port)) {
    if (Test-ProcessAlive $procId) {
      Write-Host "  stop live pid $procId on :$Port"
      [void](Invoke-TaskKill $procId)
    } else {
      Write-Host "  skip ghost pid $procId on :$Port (process already gone)" -ForegroundColor DarkYellow
    }
  }
}

function Stop-Tree([int]$ProcessId) {
  if ($ProcessId -le 0) { return }
  if (-not (Test-ProcessAlive $ProcessId)) { return }
  Write-Host "  stop tree pid $ProcessId"
  [void](Invoke-TaskKill $ProcessId)
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

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    ($_.Name -match 'python|uvicorn') -and ($_.CommandLine -match 'uvicorn|src\.api\.main')
  } |
  ForEach-Object {
    Stop-Tree ([int]$_.ProcessId)
  }

Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'vite|code2giude-agent\\frontend|code2guide-frontend' } |
  ForEach-Object {
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
