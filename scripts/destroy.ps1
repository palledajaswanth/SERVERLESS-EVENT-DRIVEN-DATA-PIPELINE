param([switch]$AutoApprove)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location "$Root\terraform"
try {
  $args = @("destroy")
  if ($AutoApprove) { $args += "-auto-approve" }
  & terraform @args
  if ($LASTEXITCODE -ne 0) { throw "terraform destroy failed" }
} finally { Pop-Location }
Remove-Item "$Root\config\runtime.json" -ErrorAction SilentlyContinue
Write-Host "AWS project infrastructure destroyed." -ForegroundColor Green
