param(
  [switch]$InstallMissing
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Has-Command($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

$required = @(
  @{Name="python"; Winget="Python.Python.3.12"},
  @{Name="git"; Winget="Git.Git"},
  @{Name="aws"; Winget="Amazon.AWSCLI"},
  @{Name="terraform"; Winget="Hashicorp.Terraform"},
  @{Name="docker"; Winget="Docker.DockerDesktop"}
)

$missing = @()
foreach ($item in $required) {
  if (-not (Has-Command $item.Name)) { $missing += $item }
}

if ($missing.Count -gt 0) {
  Write-Host "Missing prerequisites:" -ForegroundColor Yellow
  $missing | ForEach-Object { Write-Host " - $($_.Name)" }
  if ($InstallMissing) {
    if (-not (Has-Command "winget")) { throw "winget is required for automatic prerequisite installation." }
    foreach ($item in $missing) {
      Write-Host "Installing $($item.Name) ..."
      winget install --id $item.Winget --exact --accept-package-agreements --accept-source-agreements
    }
    Write-Host "System tools were installed/updated. Re-open VS Code Terminal if a newly installed command is not yet on PATH." -ForegroundColor Yellow
  } else {
    throw "Install the missing prerequisites, or rerun: .\scripts\bootstrap.ps1 -InstallMissing"
  }
}

if (-not (Test-Path ".venv")) { python -m venv .venv }
$Py = Join-Path $Root ".venv\Scripts\python.exe"
& $Py -m pip install --upgrade pip
& $Py -m pip install -r requirements.txt

Write-Host "Running local unit tests..."
& $Py -m pytest tests/unit -q
if ($LASTEXITCODE -ne 0) { throw "Unit tests failed." }

Write-Host "Checking Docker engine..."
if (-not (Has-Command "docker")) {
  throw "Docker Desktop is not installed or not on PATH. Install Docker Desktop and rerun bootstrap."
}

$dockerOutput = @()
$dockerExitCode = 0
try {
  $dockerOutput = @(& docker info 2>&1)
  $dockerExitCode = $LASTEXITCODE
} catch {
  $dockerOutput = @($_.Exception.Message)
  $dockerExitCode = 1
}

$dockerText = ($dockerOutput | Out-String).Trim()
if ($dockerExitCode -ne 0) {
  $fatalPatterns = @(
    "cannot connect",
    "not running",
    "pipe/docker",
    "failed to connect",
    "No such file",
    "The system cannot find the file",
    "Cannot connect to the Docker daemon",
    "Is the docker daemon running",
    "permission denied",
    "cannot assign requested address"
  )

  $isFatal = $false
  foreach ($pattern in $fatalPatterns) {
    if ($dockerText -match $pattern) {
      $isFatal = $true
      break
    }
  }

  if (-not $isFatal) {
    if ($dockerText -match "WARNING:") {
      Write-Host "Docker is reachable, but emitted warnings: $dockerText" -ForegroundColor Yellow
    } else {
      throw "Docker check failed: $dockerText"
    }
  } else {
    throw "Docker Desktop is installed but the Docker engine is not running. Start Docker Desktop and rerun."
  }
}

Write-Host "Checking AWS identity..."
aws sts get-caller-identity
if ($LASTEXITCODE -ne 0) { throw "AWS credentials are not configured. Run 'aws configure' or authenticate with your AWS SSO profile." }

Write-Host "Bootstrap complete." -ForegroundColor Green
