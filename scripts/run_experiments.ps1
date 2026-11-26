param(
  [string]$RunId = "",
  [int]$Events = 0,
  [int]$Concurrency = 0,
  [switch]$SkipSaturation
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = "$Root\.venv\Scripts\python.exe"
$Cfg = Get-Content "$Root\config\project.json" -Raw | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace($RunId)) { $RunId = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ") }
if ($Events -le 0) { $Events = [int]$Cfg.default_events }
if ($Concurrency -le 0) { $Concurrency = [int]$Cfg.default_concurrency }

& "$Root\scripts\start_baseline.ps1"

Write-Host "Baseline workload..." -ForegroundColor Cyan
& $Py "$Root\workload\load_test.py" --target baseline --count $Events --concurrency $Concurrency --run-id $RunId
if ($LASTEXITCODE -gt 2) { throw "Baseline workload failed to execute." }

Write-Host "AWS serverless workload..." -ForegroundColor Cyan
& $Py "$Root\workload\load_test.py" --target aws --count $Events --concurrency $Concurrency --run-id $RunId
if ($LASTEXITCODE -gt 2) { throw "AWS workload failed to execute." }

if (-not $SkipSaturation) {
  & $Py "$Root\experiments\saturation.py" --target baseline --count $Events --run-id "$RunId-saturation"
  & $Py "$Root\experiments\saturation.py" --target aws --count $Events --run-id "$RunId-saturation"
}

$BaselineSummary = "$Root\evidence\runs\$RunId\baseline_summary.json"
$AwsSummary = "$Root\evidence\runs\$RunId\aws_summary.json"
if ((Test-Path $BaselineSummary) -and (Test-Path $AwsSummary)) {
  & $Py "$Root\experiments\compare_results.py" --baseline $BaselineSummary --aws $AwsSummary --output "$Root\evidence\runs\$RunId\comparison.json"
}

Write-Host "Waiting briefly for queued events to drain before analytics sync..."
Start-Sleep -Seconds 8
& $Py "$Root\analytics\rebuild.py"

Write-Host "Experiment run complete: evidence\runs\$RunId" -ForegroundColor Green
