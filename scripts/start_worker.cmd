@echo off
setlocal
cd /d %~dp0\..
if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\bootstrap_windows_py315.ps1 first.
  exit /b 1
)
for /f "usebackq delims=" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path '.env.local') { Get-Content '.env.local' | ? {$_ -and $_ -notmatch '^\\s*#'} | %% { \"set \" + $_ } }"`) do %%i
.venv\Scripts\python.exe -m datashield.worker
endlocal
