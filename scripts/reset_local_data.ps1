param([switch]$IncludeEvidence)
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
docker compose down 2>$null
Remove-Item "$Root\baseline\data" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$Root\analytics\data" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$Root\analytics\pipeline.duckdb" -Force -ErrorAction SilentlyContinue
if ($IncludeEvidence) { Remove-Item "$Root\evidence\runs" -Recurse -Force -ErrorAction SilentlyContinue }
Write-Host "Local runtime data reset."
