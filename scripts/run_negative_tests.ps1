param([string]$RunId = "")
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = "$Root\.venv\Scripts\python.exe"
if ([string]::IsNullOrWhiteSpace($RunId)) { $RunId = "accept-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ") }

& $Py "$Root\experiments\capture_pricing.py"
if ($LASTEXITCODE -ne 0) { Write-Warning "AWS pricing capture failed. NT-3 will correctly report HOLD rather than using fabricated pricing." }

& $Py "$Root\negative_tests\run_all.py" --run-id $RunId
$code = $LASTEXITCODE
& $Py "$Root\experiments\generate_manifest.py"
exit $code
