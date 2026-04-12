param([string]$cmd)

function Kill-Node {
    Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 1
}

function Start-Server {
    Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$PWD'; node server.js"
}

switch ($cmd) {
    "start" {
        Kill-Node
        Start-Server
        Write-Host "SERVER STARTED"
    }
    "stop" {
        Kill-Node
        Write-Host "SERVER STOPPED"
    }
    "restart" {
        Kill-Node
        Start-Sleep -Seconds 1
        Start-Server
        Write-Host "SERVER RESTARTED"
    }
    default {
        Write-Host "Usage: .\run.ps1 start|stop|restart"
    }
}
