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

function Test-PortOpen([int]$Port) {
  try {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $c
  } catch {
    return $false
  }
}

function Stop-PortListeners([int]$Port) {
  $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  foreach ($c in @($conns)) {
    if ($c.OwningProcess -and $c.OwningProcess -gt 0) {
      & taskkill /PID $c.OwningProcess /T /F 2>$null | Out-Null
    }
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

if (Test-PortOpen $ApiPort) {
  Write-Host "-> Port $ApiPort busy - stopping previous listener" -ForegroundColor DarkYellow
  Stop-PortListeners $ApiPort
}
if (Test-PortOpen $UiPort) {
  Write-Host "-> Port $UiPort busy - stopping previous listener" -ForegroundColor DarkYellow
  Stop-PortListeners $UiPort
}

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
