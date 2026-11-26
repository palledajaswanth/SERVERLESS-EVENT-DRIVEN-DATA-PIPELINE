$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = "$Root\.venv\Scripts\python.exe"
& $Py "$Root\analytics\rebuild.py"
& $Py -m streamlit run "$Root\dashboard\app.py"
