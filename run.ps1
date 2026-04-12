param(
  [ValidateSet("start","stop","restart","status")]
  [string]$cmd = "status"
)

$ErrorActionPreference = "SilentlyContinue"

function Kill-Node {
  Get-Process node | Stop-Process -Force
  Start-Sleep -Seconds 2
}

function Start-All {
  Write-Host "START STACK (server + bridge)" -ForegroundColor Green

  # ENV propre
  $env:BROKER_MODE="live"
  $env:SAFE_MODE="0"

  # Lancer server.js (qui DOIT contenir toutes les routes, dont /tradingview/live)
  Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$PWD'; node server.js" -WindowStyle Minimized

  Start-Sleep -Seconds 2

  # Test port 4000
  try {
    $r = Invoke-WebRequest "http://127.0.0.1:4000" -UseBasicParsing -TimeoutSec 3
    Write-Host "SERVER ONLINE (4000)" -ForegroundColor Green
  } catch {
    Write-Host "SERVER KO (4000)" -ForegroundColor Red
  }

  # Test endpoint live
  try {
    Invoke-WebRequest "http://127.0.0.1:4000/tradingview/live" -UseBasicParsing -Method POST -Body "{}" -TimeoutSec 3 | Out-Null
    Write-Host "ENDPOINT /tradingview/live OK" -ForegroundColor Green
  } catch {
    Write-Host "ENDPOINT /tradingview/live KO" -ForegroundColor Yellow
  }
}

switch ($cmd) {
  "start"   { Kill-Node; Start-All }
  "stop"    { Kill-Node; Write-Host "ALL STOPPED" -ForegroundColor Yellow }
  "restart" { Kill-Node; Start-All }
  "status"  {
    if (Get-Process node) { Write-Host "NODE RUNNING" -ForegroundColor Green } else { Write-Host "NODE STOPPED" -ForegroundColor Red }
  }
}
