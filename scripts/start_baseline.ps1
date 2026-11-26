$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
New-Item -ItemType Directory -Force "$Root\baseline\data" | Out-Null
docker compose up -d --build baseline
if ($LASTEXITCODE -ne 0) { throw "Could not start baseline container." }

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
  try {
    $r = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
    if ($r.ok) { $ready = $true; break }
  } catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) { docker compose logs baseline; throw "Baseline did not become healthy." }
Write-Host "Always-on baseline is healthy at http://127.0.0.1:8000" -ForegroundColor Green
