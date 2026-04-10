param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonCmd = "python",
    [string]$AdminUser = "admin",
    [string]$AdminPassword = "__REPLACE_ME_ADMIN_PASSWORD__",
    [string]$AuditKey = "__REPLACE_ME_MIN_32_CHARS__"
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectRoot

Write-Host "[1/6] Project root: $ProjectRoot"
& $PythonCmd --version

Write-Host "[2/6] Creating virtual environment"
& $PythonCmd -m venv .venv

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$venvPip = Join-Path $ProjectRoot ".venv\Scripts\pip.exe"

Write-Host "[3/6] Upgrading pip/setuptools/wheel"
& $venvPython -m pip install --upgrade pip setuptools wheel

Write-Host "[4/6] Installing DataShield editable package"
& $venvPip install -e .

Write-Host "[5/6] Writing local environment file"
@"
DATASHIELD_AUDIT_KEY=$AuditKey
DS_BOOTSTRAP_ADMIN=$AdminUser
DS_BOOTSTRAP_PASSWORD=$AdminPassword
DS_CONTROL_DB_URL=sqlite:///./datashield_control.db
DS_WEB_HOST=127.0.0.1
DS_WEB_PORT=8080
DS_WEB_THREADS=8
DS_WORKER_POLL_INTERVAL=2
"@ | Set-Content -Path (Join-Path $ProjectRoot ".env.local") -Encoding UTF8

Write-Host "[6/6] Done"
Write-Host "Local env file created: $ProjectRoot\.env.local"
Write-Host "Next: run scripts\\start_all_windows.cmd"
