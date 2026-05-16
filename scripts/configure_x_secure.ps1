param(
    [string]$HostName = "20.235.64.162",
    [string]$UserName = "traderadmin",
    [string]$KeyPath = "C:\Users\LENOVO\.ssh\codex_ai_trading_ed25519",
    [string]$ProjectDir = "/home/traderadmin/veda-trading-ai"
)

$ErrorActionPreference = "Stop"

Write-Host "Veda X/Twitter secure setup"
Write-Host "Paste your X Bearer Token below. Input is hidden and will not be printed."

if (-not (Test-Path -LiteralPath $KeyPath)) {
    throw "SSH key not found: $KeyPath"
}

$secure = Read-Host "X Bearer Token" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}

$users = Read-Host "Approved X usernames, comma-separated"
if ([string]::IsNullOrWhiteSpace($token) -or [string]::IsNullOrWhiteSpace($users)) {
    throw "Bearer token and usernames are required."
}

$payloadPath = [System.IO.Path]::GetTempFileName()
$remotePayload = "/tmp/veda_x_config.json"
$remoteScript = "/tmp/veda_apply_x_config.py"
$scriptPath = [System.IO.Path]::GetTempFileName()

try {
    $payloadJson = @{
        X_BEARER_TOKEN = $token
        X_USERNAMES = $users
        X_INGEST_ON_START = "true"
    } | ConvertTo-Json
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($payloadPath, $payloadJson, $utf8NoBom)

    @"
import json
from pathlib import Path

project_dir = Path("$ProjectDir")
env_path = project_dir / ".env"
payload_path = Path("$remotePayload")

data = json.loads(payload_path.read_text(encoding="utf-8-sig"))
updates = {key: str(value) for key, value in data.items() if str(value).strip()}
lines = env_path.read_text().splitlines() if env_path.exists() else []
seen = set()
out = []

for line in lines:
    if line and not line.lstrip().startswith("#") and "=" in line:
        key = line.split("=", 1)[0]
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
    out.append(line)

for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")

env_path.write_text("\n".join(out) + "\n")
env_path.chmod(0o600)
payload_path.unlink(missing_ok=True)
Path("$remoteScript").unlink(missing_ok=True)
"@ | Set-Content -LiteralPath $scriptPath -Encoding UTF8

    scp -i $KeyPath $payloadPath "$UserName@$HostName`:$remotePayload"
    scp -i $KeyPath $scriptPath "$UserName@$HostName`:$remoteScript"

    ssh -i $KeyPath "$UserName@$HostName" "python3 $remoteScript && cd '$ProjectDir' && docker compose up -d api scheduler dashboard && curl -fsS http://localhost:8000/ingest/x/status && printf '\n\nRunning test ingestion...\n' && curl -fsS -X POST http://localhost:8000/ingest/x/configured -H 'Content-Type: application/json' -d '{""limit"":5}'"
}
finally {
    Remove-Item -LiteralPath $payloadPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue
    if ($token) {
        $token = $null
    }
}

Write-Host ""
Write-Host "Done. You can close this window after checking the output."
