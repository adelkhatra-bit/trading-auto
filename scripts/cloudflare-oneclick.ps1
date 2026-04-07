param(
    [string]$TunnelName = "trading-bridge",
    [string]$Hostname = $env:CF_TUNNEL_HOSTNAME,
    [int]$LocalPort = 4000,
    [switch]$RequireStable = $true
)

$ErrorActionPreference = "Stop"
$real = "C:\ProgramData\chocolatey\lib\cloudflared\tools\cloudflared.exe"
if (-not (Test-Path $real)) {
    throw "cloudflared binary not found at $real"
}

$cfDir = Join-Path $env:USERPROFILE ".cloudflared"
if (-not (Test-Path $cfDir)) {
    New-Item -ItemType Directory -Path $cfDir | Out-Null
}

# Hard stop ngrok to enforce Cloudflare-only exposure.
Get-Process ngrok -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

$certPath = Join-Path $cfDir "cert.pem"
if (-not (Test-Path $certPath)) {
    Write-Host "[STEP] Login required: browser opens, click Authorize once." -ForegroundColor Yellow
    & $real tunnel login
    if (-not (Test-Path $certPath)) {
        throw "cert.pem not generated after login; authorization was not completed."
    }
}

# Create or reuse one named tunnel.
$tunnels = @()
try {
    $raw = & $real tunnel list --output json
    if ($raw) { $tunnels = $raw | ConvertFrom-Json }
} catch {
    $tunnels = @()
}

$tunnel = $tunnels | Where-Object { $_.name -eq $TunnelName } | Select-Object -First 1
if (-not $tunnel) {
    Write-Host "[STEP] Creating tunnel: $TunnelName" -ForegroundColor Cyan
    & $real tunnel create $TunnelName | Out-Host

    $raw2 = & $real tunnel list --output json
    $tunnels2 = @()
    if ($raw2) { $tunnels2 = $raw2 | ConvertFrom-Json }
    $tunnel = $tunnels2 | Where-Object { $_.name -eq $TunnelName } | Select-Object -First 1
}

if (-not $tunnel) {
    throw "Unable to create or locate tunnel '$TunnelName'."
}

$tunnelId = [string]$tunnel.id
$credFile = Join-Path $cfDir ("{0}.json" -f $tunnelId)
if (-not (Test-Path $credFile)) {
    throw "Tunnel credential file not found: $credFile"
}

# Try to create/update DNS route only when hostname is provided.
if ([string]::IsNullOrWhiteSpace($Hostname)) {
    if ($RequireStable) {
        throw "Stable public URL is impossible without CF_TUNNEL_HOSTNAME on a Cloudflare DNS zone. Temporary tunnels are intentionally blocked."
    }
    Write-Host "[WARN] CF_TUNNEL_HOSTNAME not provided. Running without DNS hostname will not create a stable public URL." -ForegroundColor Yellow
} else {
    Write-Host "[STEP] Routing DNS hostname to tunnel: $Hostname" -ForegroundColor Cyan
    & $real tunnel route dns --overwrite-dns $TunnelName $Hostname | Out-Host
}

$configPath = Join-Path $cfDir "config.yml"
$configLines = @(
        "tunnel: $tunnelId",
        "credentials-file: $credFile",
        "",
        "ingress:",
        "  -"
)

if (-not [string]::IsNullOrWhiteSpace($Hostname)) {
        $configLines += "    hostname: $Hostname"
}

$configLines += @(
        "    path: /tv-webhook",
        "    service: http://localhost:$LocalPort",
        "  - service: http_status:404"
)

$config = $configLines -join "`n"

Set-Content -Path $configPath -Value $config -Encoding UTF8
Write-Host "[OK] Config written: $configPath" -ForegroundColor Green

if (-not [string]::IsNullOrWhiteSpace($Hostname)) {
    Write-Host "[OK] Stable webhook URL: https://$Hostname/tv-webhook" -ForegroundColor Green
}

# Start persistent tunnel process (foreground). Use separate terminal for long-running service.
Write-Host "[STEP] Starting tunnel with config..." -ForegroundColor Cyan
& $real tunnel --config $configPath run $TunnelName
