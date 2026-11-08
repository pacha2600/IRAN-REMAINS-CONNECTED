# Optional GUI standalone EXE for a machine that already has sing-box installed.
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
& '.\.venv\Scripts\python.exe' -m pip install 'pyinstaller>=6,<7'
& '.\.venv\Scripts\python.exe' -m PyInstaller --clean --noconfirm --windowed --onefile --name IranRemainsConnected --icon assets\iran-remains-connected.ico --add-data "assets\iran-remains-connected.png;assets" --add-data "assets\iran-remains-connected.ico;assets" main.py
Write-Host 'Executable: dist\IranRemainsConnected.exe; keep bin\sing-box.exe beside it if using portable deployment.'
