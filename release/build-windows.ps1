# Build on Windows. Users who install the output Setup.exe need NO Python or PowerShell.
# For automatic generation, see .github/workflows/windows-release.yml.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
$version = '1.14.4'
$expectedSha256 = '99185d75d314a07dbba4a130c8ad986cbeb629a07927975636b341ca61f991df'
$binDir = Join-Path $root 'release-core'
$core = Join-Path $binDir 'sing-box.exe'
$archive = Join-Path $env:TEMP "iran-proxy-monitor-$version-amd64.zip"
New-Item -ItemType Directory -Path $binDir -Force | Out-Null
# Never trust a previously copied executable: verify the official archive hash
# on EVERY build, then freshly extract the core into the release directory.
$url = "https://github.com/SagerNet/sing-box/releases/download/v$version/sing-box-$version-windows-amd64.zip"
if (-not (Test-Path $archive)) {
  Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing
}
$hash = (Get-FileHash -Path $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($hash -ne $expectedSha256) {
  Remove-Item $archive -Force
  throw 'Official sing-box archive SHA256 mismatch. Aborting release build.'
}
$extract = Join-Path $env:TEMP 'iran-proxy-monitor-core-build'
if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
Expand-Archive $archive -DestinationPath $extract
$found = Get-ChildItem $extract -Recurse -Filter 'sing-box.exe' | Select-Object -First 1
if (-not $found) { throw 'Core missing in official archive.' }
Copy-Item $found.FullName $core -Force
Remove-Item $extract -Recurse -Force

& $core version
if ($LASTEXITCODE -ne 0) { throw 'Core version command failed.' }
python -m pip install 'pyinstaller>=6.10,<7'
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed.' }
python -m PyInstaller --clean --noconfirm --windowed --onedir --name IranRemainsConnected --icon assets\iran-remains-connected.ico --add-data "assets\iran-remains-connected.png;assets" --add-data "assets\iran-remains-connected.ico;assets" main.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
$dist = Join-Path $root 'dist\IranRemainsConnected'
New-Item -ItemType Directory -Path (Join-Path $dist 'bin') -Force | Out-Null
Copy-Item -LiteralPath $core -Destination (Join-Path $dist 'bin\sing-box.exe') -Force
# Include third-party licenses in public binaries.
$licenseDir = Join-Path $dist 'licenses'
New-Item -ItemType Directory -Path $licenseDir -Force | Out-Null
Copy-Item (Join-Path $root 'iran_proxy_monitor\_vendor\PyYAML-LICENSE.txt') (Join-Path $licenseDir 'LICENSE-PyYAML.txt') -Force
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/SagerNet/sing-box/v$version/LICENSE" -OutFile (Join-Path $licenseDir 'LICENSE-sing-box.txt') -UseBasicParsing
$iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
if (-not (Test-Path $iscc)) { $iscc = Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe' }
if (-not (Test-Path $iscc)) { throw 'Install Inno Setup 6 on your build computer, or run GitHub Actions.' }
& $iscc (Join-Path $root 'release\IranProxyMonitor.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup packaging failed.' }
Write-Host "Ready: $root\release-output\IranRemainsConnected-Setup-v1.1-win64.exe" -ForegroundColor Green
