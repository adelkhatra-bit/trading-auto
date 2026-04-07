param(
  [int]$Port = 4000,
  [string]$Route = "/tv-webhook",
  [string]$RuleName = "TradingAuto-Webhook-4000"
)

$ErrorActionPreference = "Stop"

$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
  Write-Host "[STEP] Elevating to Administrator for firewall configuration..." -ForegroundColor Yellow
  $argList = @(
    '-NoProfile',
    '-ExecutionPolicy',
    'Bypass',
    '-File',
    ('"{0}"' -f $PSCommandPath),
    '-Port',
    $Port,
    '-Route',
    ('"{0}"' -f $Route),
    '-RuleName',
    ('"{0}"' -f $RuleName)
  )
  Start-Process -FilePath 'powershell.exe' -ArgumentList ($argList -join ' ') -Verb RunAs | Out-Null
  exit 0
}

function Get-Json {
  param(
    [Parameter(Mandatory = $true)][string]$Url,
    [int]$TimeoutSec = 8
  )
  $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
  if ([string]::IsNullOrWhiteSpace($r.Content)) {
    return $null
  }
  return ($r.Content | ConvertFrom-Json)
}

function Invoke-JsonPost {
  param(
    [Parameter(Mandatory = $true)][string]$Url,
    [Parameter(Mandatory = $true)]$Payload,
    [int]$TimeoutSec = 8
  )
  $body = $Payload | ConvertTo-Json -Depth 8 -Compress
  $r = Invoke-WebRequest -Uri $Url -Method POST -ContentType "application/json" -Body $body -UseBasicParsing -TimeoutSec $TimeoutSec
  return ($r.Content | ConvertFrom-Json)
}

$healthUrl = ("http://127.0.0.1:{0}/health" -f $Port)
$logsUrl = ("http://127.0.0.1:{0}/system-log" -f $Port)
$agentStatusUrl = ("http://127.0.0.1:{0}/agent-status" -f $Port)
$routePath = if ($Route.StartsWith('/')) { $Route } else { "/$Route" }

$ipv4Regex = '^((25[0-5]|2[0-4][0-9]|[01]?[0-9]?[0-9])\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9]?[0-9])$'

Write-Host "[STEP] Checking local server..." -ForegroundColor Cyan
$health = $null
try {
  $health = Get-Json -Url $healthUrl
} catch {
  throw "Server is not reachable on $healthUrl. Start it first with: npm start"
}
if (-not $health -or -not $health.ok) {
  throw "Health endpoint did not return ok=true on $healthUrl"
}
Write-Host "[OK] Server is running on port $Port" -ForegroundColor Green

Write-Host "[STEP] Configuring Windows Firewall rule..." -ForegroundColor Cyan
$ruleExists = $false
try {
  & netsh advfirewall firewall show rule name=$RuleName | Out-Null
  if ($LASTEXITCODE -eq 0) { $ruleExists = $true }
} catch {
  $ruleExists = $false
}

$firewallOpened = $false
$firewallNote = ""
if ($ruleExists) {
  $firewallOpened = $true
  $firewallNote = "existing-rule"
  Write-Host "[OK] Firewall rule already exists: $RuleName" -ForegroundColor Green
} else {
  try {
    & netsh advfirewall firewall add rule name=$RuleName dir=in action=allow protocol=TCP localport=$Port profile=private enable=yes | Out-Null
    if ($LASTEXITCODE -eq 0) {
      $firewallOpened = $true
      $firewallNote = "created"
      Write-Host "[OK] Firewall rule created for TCP/$Port (Private profile)" -ForegroundColor Green
    } else {
      $firewallNote = "create-failed"
      Write-Host "[WARN] Could not create firewall rule (exit code $LASTEXITCODE)." -ForegroundColor Yellow
    }
  } catch {
    $firewallNote = "admin-required"
    Write-Host "[WARN] Firewall rule creation failed (possibly admin rights required)." -ForegroundColor Yellow
  }
}

$localIps = @()
try {
  $localIps = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
    Where-Object {
      $_.IPAddress -notlike '169.254.*' -and
      $_.IPAddress -ne '127.0.0.1' -and
      $_.PrefixOrigin -ne 'WellKnown' -and
      $_.IPAddress -match $ipv4Regex
    } |
    Sort-Object -Property InterfaceMetric |
    Select-Object -ExpandProperty IPAddress -Unique)
} catch {
  $localIps = @()
}
if (-not $localIps -or $localIps.Count -eq 0) {
  $fallback = (ipconfig | Select-String -Pattern 'IPv4' | ForEach-Object { ($_ -split ':')[-1].Trim() })
  $localIps = @($fallback | Where-Object {
      $_ -and $_ -notlike '169.254.*' -and $_ -ne '127.0.0.1' -and $_ -match $ipv4Regex
    } | Select-Object -Unique)
}
$localIp = if ($localIps.Count -gt 0) { [string]($localIps | Select-Object -First 1) } else { $null }

$publicIp = $null
try {
  $publicIp = (Invoke-WebRequest -UseBasicParsing -Uri 'https://api.ipify.org' -TimeoutSec 8).Content
} catch {
  $publicIp = $null
}

$localWebhookUrl = if ($localIp) { ("http://{0}:{1}{2}" -f $localIp, $Port, $routePath) } else { $null }
$publicWebhookUrl = if ($publicIp) { ("http://{0}:{1}{2}" -f $publicIp, $Port, $routePath) } else { $null }

$payload = @{
  symbol = "EURUSD"
  price = 1.12345
  source = "direct-http"
  event = "direct-route-check"
  timestamp = (Get-Date).ToString('o')
}

Write-Host "[STEP] Testing direct webhook POST (localhost)..." -ForegroundColor Cyan
$postLocalhostOk = $false
$postLocalhostResp = $null
try {
  $postLocalhostResp = Invoke-JsonPost -Url ("http://127.0.0.1:{0}{1}" -f $Port, $routePath) -Payload $payload
  $postLocalhostOk = [bool]$postLocalhostResp.ok
} catch {
  $postLocalhostOk = $false
}

$postLanOk = $false
$postLanResp = $null
if ($localWebhookUrl) {
  Write-Host "[STEP] Testing direct webhook POST (LAN IP)..." -ForegroundColor Cyan
  try {
    $postLanResp = Invoke-JsonPost -Url $localWebhookUrl -Payload $payload
    $postLanOk = [bool]$postLanResp.ok
  } catch {
    $postLanOk = $false
  }
}

$payloadSeenInLogs = $false
$agentStatusOk = $false
$agentTriggered = $false

try {
  $logs = Get-Json -Url $logsUrl
  $rows = @($logs.logs)
  $latestWebhookLog = ($rows | Where-Object {
      $_.from -eq 'tradingview-webhook' -and (
        $_.action -match 'WEBHOOK' -or
        $_.action -match 'EURUSD' -or
        $_.detail -match 'EURUSD'
      )
    } | Select-Object -First 1)
  $payloadSeenInLogs = $null -ne $latestWebhookLog
} catch {
  $payloadSeenInLogs = $false
}

try {
  $a = Get-Json -Url $agentStatusUrl
  $agentStatusOk = [bool]$a.ok
  $agentTriggered = [bool](
    ($null -ne $a.agents -and $a.agents.PSObject.Properties.Name -contains 'tradingview-webhook') -or
    ($null -ne $a.agents -and $a.agents.PSObject.Properties.Name -contains 'surveillance-agent')
  )
} catch {
  $agentStatusOk = $false
  $agentTriggered = $false
}

$result = [ordered]@{
  timestamp = (Get-Date).ToString('o')
  serverRunning = $true
  firewall = [ordered]@{
    opened = $firewallOpened
    note = $firewallNote
    ruleName = $RuleName
  }
  endpoints = [ordered]@{
    localhost = ("http://127.0.0.1:{0}{1}" -f $Port, $routePath)
    localIp = $localWebhookUrl
    publicIp = $publicWebhookUrl
  }
  tests = [ordered]@{
    postLocalhost = $postLocalhostOk
    postLocalIp = $postLanOk
    payloadSeenInLogs = $payloadSeenInLogs
    agentStatusEndpoint = $agentStatusOk
    agentsTriggered = $agentTriggered
  }
}

Write-Host "\n=== DIRECT WEBHOOK STATUS ===" -ForegroundColor Cyan
$result | ConvertTo-Json -Depth 8

if (-not $firewallOpened) {
  Write-Host "\n[NOTE] Firewall may still block LAN/public access. Run this script as Administrator to enforce inbound rule." -ForegroundColor Yellow
}
if (-not $publicIp) {
  Write-Host "[NOTE] Public IP is unavailable from this host now. Use LAN URL as internal relay fallback." -ForegroundColor Yellow
}
if ($publicIp) {
  Write-Host "[NOTE] Public IP URL requires router/NAT port-forwarding TCP/$Port to this machine." -ForegroundColor Yellow
}
