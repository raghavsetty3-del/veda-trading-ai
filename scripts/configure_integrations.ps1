param(
    [string]$HostName = "20.235.64.162",
    [string]$UserName = "traderadmin",
    [string]$KeyPath = "C:\Users\LENOVO\.ssh\codex_ai_trading_ed25519",
    [string]$ProjectDir = "/home/traderadmin/veda-trading-ai"
)

$ErrorActionPreference = "Stop"

Write-Host "Veda integration setup launcher"
Write-Host "Target: $UserName@$HostName"
Write-Host ""

if (-not (Test-Path -LiteralPath $KeyPath)) {
    throw "SSH key not found: $KeyPath"
}

$remote = @"
cd '$ProjectDir'
chmod +x scripts/configure_integrations.sh
PROJECT_DIR='$ProjectDir' bash scripts/configure_integrations.sh
"@

ssh -i $KeyPath "$UserName@$HostName" $remote
