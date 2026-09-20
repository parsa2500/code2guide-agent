<#
.SYNOPSIS
  Start Code2Guide stack: Qdrant + FastAPI + Vite frontend.
.NOTES
  Writes session metadata to .code2guide/dev-session.json for scripts/dev-down.ps1
#>
[CmdletBinding()]
param(
  [int]$ApiPort = 8000,
  [int]$UiPort = 5173,
  [switch]$SkipQdrant,
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$SessionDir = Join-Path $Root ".code2guide"
$SessionFile = Join-Path $SessionDir "dev-session.json"
$LogDir = Join-Path $SessionDir "logs"
New-Item -ItemType Directory -Force -Path $SessionDir, $LogDir | Out-Null

function Test-ProcessAlive([int]$ProcessId) {
  if ($ProcessId -le 0) { return $false }
  return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Invoke-TaskKill([int]$ProcessId) {
  if (-not (Test-ProcessAlive $ProcessId)) { return $false }
  # Route through cmd so stderr never becomes a terminating NativeCommandError under Stop
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

function Test-PortOpen([int]$Port) {
  return @(Get-ListenPids $Port).Count -gt 0
}

function Stop-PortListeners([int]$Port) {
  $pids = Get-ListenPids $Port
  foreach ($procId in $pids) {
    if (Test-ProcessAlive $procId) {
      Write-Host "  stop live pid $procId on :$Port"
      [void](Invoke-TaskKill $procId)
    } else {
      Write-Host "  skip ghost pid $procId on :$Port (process already gone)" -ForegroundColor DarkYellow
    }
  }
  Start-Sleep -Milliseconds 300
}

function Clear-PortOrWarn([int]$Port) {
  if (-not (Test-PortOpen $Port)) { return }
  Write-Host "-> Port $Port busy - clearing listeners" -ForegroundColor DarkYellow
  Stop-PortListeners $Port

  $left = Get-ListenPids $Port
  $live = @($left | Where-Object { Test-ProcessAlive $_ })
  if ($live.Count -gt 0) {
    Write-Warning ("Port {0} still held by live PID(s): {1}. API/UI may fail to bind." -f $Port, ($live -join ", "))
  } elseif ($left.Count -gt 0) {
    Write-Host "  stale TCP rows remain on :$Port; continuing (bind usually still works)" -ForegroundColor DarkYellow
  }
}

Write-Host "==> Code2Guide UP" -ForegroundColor Cyan

if (-not $SkipQdrant) {
  Write-Host "-> Qdrant (docker compose)" -ForegroundColor Yellow
  docker compose up -d qdrant
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "docker compose failed - continuing without Qdrant."
  }
}

$Frontend = Join-Path $Root "frontend"
if (-not $SkipInstall) {
  if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Write-Host "-> npm install (frontend)" -ForegroundColor Yellow
    Push-Location $Frontend
    npm install
    Pop-Location
  }
}

Clear-PortOrWarn $ApiPort
Clear-PortOrWarn $UiPort

$ApiLog = Join-Path $LogDir "api.out.log"
$ApiErr = Join-Path $LogDir "api.err.log"
$UiLog = Join-Path $LogDir "ui.out.log"
$UiErr = Join-Path $LogDir "ui.err.log"

$Python = "python"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) { $Python = $VenvPython }

Write-Host "-> API  http://127.0.0.1:$ApiPort  (uvicorn)" -ForegroundColor Yellow
$api = Start-Process -FilePath $Python `
  -ArgumentList @("-m", "uvicorn", "src.api.main:app", "--reload", "--host", "127.0.0.1", "--port", "$ApiPort") `
  -WorkingDirectory $Root `
  -RedirectStandardOutput $ApiLog `
  -RedirectStandardError $ApiErr `
  -WindowStyle Hidden `
  -PassThru

Write-Host "-> UI   http://127.0.0.1:$UiPort  (vite)" -ForegroundColor Yellow
$npmCmd = if (Get-Command npm.cmd -ErrorAction SilentlyContinue) { "npm.cmd" } else { "npm" }
$ui = Start-Process -FilePath $npmCmd `
  -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$UiPort") `
  -WorkingDirectory $Frontend `
  -RedirectStandardOutput $UiLog `
  -RedirectStandardError $UiErr `
  -WindowStyle Hidden `
  -PassThru

$session = [ordered]@{
  startedAt = (Get-Date).ToString("o")
  apiPort   = $ApiPort
  uiPort    = $UiPort
  apiPid    = $api.Id
  uiPid     = $ui.Id
  apiLog    = $ApiLog
  apiErr    = $ApiErr
  uiLog     = $UiLog
  uiErr     = $UiErr
  qdrant    = (-not $SkipQdrant)
}
$session | ConvertTo-Json | Set-Content -Path $SessionFile -Encoding utf8

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "Ready:" -ForegroundColor Green
Write-Host "  UI   http://127.0.0.1:$UiPort"
Write-Host "  API  http://127.0.0.1:$ApiPort"
Write-Host "  Docs http://127.0.0.1:$ApiPort/docs"
Write-Host "  Stop: .\scripts\dev-down.ps1  or task Code2Guide: Down"
Write-Host "  Logs: $LogDir"
Write-Host ("  PIDs: api={0} ui={1}" -f $api.Id, $ui.Id)
