param([string]$action)

$port = 4000

function Stop-Port4000 {
    $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($conns) {
        $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($pid in $pids) {
            try { Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
}

function Stop-AllNode {
    Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

function Wait-PortFree {
    $max = 10
    for ($i=0; $i -lt $max; $i++) {
        $busy = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        if (-not $busy) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Test-Server {
    try {
        $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:4000/extension/data" -TimeoutSec 5
        Write-Host "SERVER RESPONSE:" -ForegroundColor Green
        Write-Host $r.Content
    } catch {
        Write-Host "SERVER TEST FAILED" -ForegroundColor Red
        Write-Host $_.Exception.Message
    }
}

function Start-Server {
    Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$PWD'; node server.js"
    Start-Sleep -Seconds 3
}

switch ($action) {
    "stop" {
        Stop-Port4000
        Stop-AllNode
        Start-Sleep -Seconds 2
        Write-Host "SYSTEM STOPPED" -ForegroundColor Yellow
    }
    "start" {
        Stop-Port4000
        Stop-AllNode
        Start-Sleep -Seconds 2
        Start-Server
        Test-Server
    }
    "restart" {
        Stop-Port4000
        Stop-AllNode
        Start-Sleep -Seconds 2
        if (-not (Wait-PortFree)) {
            Write-Host "PORT 4000 STILL BUSY" -ForegroundColor Red
            exit 1
        }
        Start-Server
        Test-Server
    }
    "status" {
        $busy = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        if ($busy) {
            Write-Host "PORT 4000 ACTIVE" -ForegroundColor Green
            $busy | Format-Table -AutoSize
        } else {
            Write-Host "PORT 4000 FREE / SERVER OFFLINE" -ForegroundColor Red
        }
    }
    default {
        Write-Host "Usage: .\run.ps1 stop|start|restart|status"
    }
}
