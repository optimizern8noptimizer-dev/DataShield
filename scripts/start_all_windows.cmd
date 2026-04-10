@echo off
setlocal
cd /d %~dp0\..
if not exist .venv\Scripts\python.exe (
  echo [ERROR] .venv not found. Run scripts\bootstrap_windows_py315.ps1 first.
  exit /b 1
)
start "DataShield Worker" cmd /k "%~dp0start_worker.cmd"
call "%~dp0start_web.cmd"
endlocal
