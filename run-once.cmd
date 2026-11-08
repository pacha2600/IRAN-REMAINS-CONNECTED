@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m iran_proxy_monitor.cli --once >> "%LOCALAPPDATA%\IranProxyMonitor\scheduled.log" 2>&1
