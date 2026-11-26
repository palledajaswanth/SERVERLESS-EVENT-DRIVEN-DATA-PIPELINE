param(
  [switch]$InstallMissing,
  [switch]$SkipSaturation,
  [switch]$SkipNegativeTests
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$RunId = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")

Write-Host "[1/6] Bootstrap" -ForegroundColor Cyan
& "$Root\scripts\bootstrap.ps1" -InstallMissing:$InstallMissing

Write-Host "[2/6] AWS deploy" -ForegroundColor Cyan
& "$Root\scripts\deploy.ps1" -AutoApprove

Write-Host "[3/6] Baseline + controlled workloads" -ForegroundColor Cyan
& "$Root\scripts\run_experiments.ps1" -RunId $RunId -SkipSaturation:$SkipSaturation

Write-Host "[4/6] CloudWatch + cost evidence" -ForegroundColor Cyan
$Py = "$Root\.venv\Scripts\python.exe"
& $Py "$Root\experiments\collect_cloudwatch.py" --minutes 60 --run-id $RunId
& $Py "$Root\experiments\capture_pricing.py"
if ($LASTEXITCODE -ne 0) {
  Write-Warning "AWS price capture could not be completed. Cost evidence will be marked HOLD rather than fabricated."
} else {
  Start-Sleep -Seconds 5
  & $Py "$Root\experiments\cost_analysis.py" --run-id $RunId
  if ($LASTEXITCODE -ne 0) { Write-Warning "Cost analysis is incomplete/HOLD. Inspect evidence\runs\$RunId\cost_analysis.json." }
}

if (-not $SkipNegativeTests) {
  Write-Host "[5/6] Five negative tests" -ForegroundColor Cyan
  & "$Root\scripts\run_negative_tests.ps1" -RunId $RunId
  if ($LASTEXITCODE -ne 0) { Write-Warning "One or more negative tests failed or were held. Inspect evidence\runs\$RunId\negative_tests. This is retained as evidence rather than hidden." }
} else {
  Write-Host "[5/6] Negative tests skipped by request" -ForegroundColor Yellow
}

Write-Host "[6/6] Evidence manifest" -ForegroundColor Cyan
& $Py "$Root\experiments\build_claim_map.py"
& $Py "$Root\experiments\generate_manifest.py"

Write-Host "FULL RUN COMPLETE" -ForegroundColor Green
Write-Host "Run ID: $RunId"
Write-Host "Evidence: $Root\evidence\runs\$RunId"
Write-Host "Dashboard: .\scripts\run_dashboard.ps1"
Write-Host "Cleanup AWS: .\scripts\destroy.ps1 -AutoApprove"
