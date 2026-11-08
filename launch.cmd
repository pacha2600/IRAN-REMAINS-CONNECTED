@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Application not installed. Run install.ps1 first.
  pause
  exit /b 1
)
start "Iran Proxy Monitor" ".venv\Scripts\pythonw.exe" main.py
