param(
  [string]$Region = "",
  [switch]$AutoApprove
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Python environment missing. Run .\scripts\bootstrap.ps1 first." }

$Project = Get-Content "$Root\config\project.json" -Raw | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace($Region)) { $Region = $Project.aws_region }

Write-Host "AWS identity:" -ForegroundColor Cyan
aws sts get-caller-identity
if ($LASTEXITCODE -ne 0) { throw "AWS authentication failed." }

Push-Location "$Root\terraform"
try {
  terraform init -upgrade
  if ($LASTEXITCODE -ne 0) { throw "terraform init failed" }
  terraform fmt -check
  if ($LASTEXITCODE -ne 0) { terraform fmt }
  terraform validate
  if ($LASTEXITCODE -ne 0) { throw "terraform validate failed" }

  $args = @("apply", "-var", "aws_region=$Region", "-var", "s3_retention_days=$($Project.s3_retention_days)")
  if ($AutoApprove) { $args += "-auto-approve" }
  & terraform @args
  if ($LASTEXITCODE -ne 0) { throw "terraform apply failed" }

  $raw = terraform output -json | ConvertFrom-Json
  $runtime = [ordered]@{
    api_url = $raw.api_url.value
    bucket_name = $raw.bucket_name.value
    queue_url = $raw.queue_url.value
    dlq_url = $raw.dlq_url.value
    dynamodb_table = $raw.dynamodb_table.value
    ingestion_function = $raw.ingestion_function.value
    transformer_function = $raw.transformer_function.value
    cloudwatch_dashboard = $raw.cloudwatch_dashboard.value
    aws_region = $raw.aws_region.value
  }
  $json = $runtime | ConvertTo-Json
  [System.IO.File]::WriteAllText("$Root\config\runtime.json", $json, (New-Object System.Text.UTF8Encoding($false)))
} finally {
  Pop-Location
}

Write-Host "Running deployed smoke test..." -ForegroundColor Cyan
& $Py "$Root\tests\integration\smoke_test.py"
if ($LASTEXITCODE -ne 0) { throw "AWS smoke test failed." }

Write-Host "Deployment complete. Runtime configuration: config\runtime.json" -ForegroundColor Green
