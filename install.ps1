# Windows installer. Public/GitHub mode: use an existing verified core or download
# the pinned official release. For a manually supplied core:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -LocalSingboxPath 'D:\sing-box.exe'
param(
  [string]$LocalSingboxPath = '',
  [switch]$NoDownload
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
Write-Host 'Iran Proxy Monitor installer' -ForegroundColor Cyan

function Test-PythonRuntime {
  param([string]$Executable, [string[]]$PrefixArguments)
  try {
    $ErrorActionPreference = 'SilentlyContinue'
    $probe = @($PrefixArguments) + @('-c', 'import sys;sys.exit(0 if sys.version_info >= (3, 11) else 1)')
    & $Executable @probe 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
  } catch { return $false }
}

$pythonCmd = $null
$pythonArgs = @()
if ((Get-Command py -ErrorAction SilentlyContinue) -and (Test-PythonRuntime -Executable 'py' -PrefixArguments @('-3'))) {
  $pythonCmd = 'py'
  $pythonArgs = @('-3')
} elseif ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-PythonRuntime -Executable 'python' -PrefixArguments @())) {
  $pythonCmd = 'python'
} else {
  throw 'Python 3.11+ was not found. Check "py list" or "python --version".'
}
Write-Host 'Selected Python:' -ForegroundColor Cyan
& $pythonCmd @pythonArgs --version
if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }
& $pythonCmd @pythonArgs -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Unable to create virtual environment.' }
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) { throw 'Virtual environment Python was not created.' }
& $venvPython (Join-Path $root 'verify_environment.py')
if ($LASTEXITCODE -ne 0) { throw 'Bundled YAML parser or Tkinter verification failed.' }

$version = '1.14.4'
$expected = '99185d75d314a07dbba4a130c8ad986cbeb629a07927975636b341ca61f991df'
$archive = Join-Path $env:TEMP "iran-proxy-monitor-sing-box-$version.zip"
$url = "https://github.com/SagerNet/sing-box/releases/download/v$version/sing-box-$version-windows-amd64.zip"
$bin = Join-Path $root 'bin'
$exe = Join-Path $bin 'sing-box.exe'
$sharedBin = Join-Path $env:LOCALAPPDATA 'IranProxyMonitor\bin'
$sharedExe = Join-Path $sharedBin 'sing-box.exe'
New-Item -ItemType Directory -Path $bin, $sharedBin -Force | Out-Null

function Test-Core {
  param([string]$Candidate)
  if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $false }
  try {
    # Ensure this is an executable sing-box core; do not invoke untrusted config files.
    $output = @(& $Candidate version 2>$null)
    if ($LASTEXITCODE -ne 0) { return $false }
    $first = if ($output.Count -gt 0) { [string]$output[0] } else { '' }
    return ($first -match '^sing-box version [0-9]+\.')
  } catch { return $false }
}

# Explicit source always takes precedence. No network requests in local mode.
if ($LocalSingboxPath) {
  $source = [System.IO.Path]::GetFullPath($LocalSingboxPath)
  if (-not (Test-Core $source)) {
    throw "Local sing-box core is missing or cannot run: $source"
  }
  if (-not [string]::Equals($source, $exe, [System.StringComparison]::OrdinalIgnoreCase)) {
    Copy-Item -LiteralPath $source -Destination $exe -Force
  }
  Write-Host "Copied local sing-box core from $source" -ForegroundColor Green
} elseif (Test-Core $exe) {
  Write-Host 'Reusing sing-box already in this application folder; no download.' -ForegroundColor Cyan
} elseif (Test-Core $sharedExe) {
  Copy-Item -LiteralPath $sharedExe -Destination $exe -Force
  Write-Host 'Reusing cached sing-box core from a previous installation; no download.' -ForegroundColor Cyan
} else {
  if ($NoDownload) {
    throw 'No verified local/cached sing-box core found; -NoDownload forbids fetching it.'
  }
  # Retain this branch for GitHub/public installs on machines without a local core.
  Write-Host 'Downloading official sing-box core (31 MB)...' -ForegroundColor Cyan
  try { Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing }
  catch {
    Write-Warning 'Core download failed. Retry with -LocalSingboxPath pointing to a trusted sing-box.exe.'
    throw
  }
  $actual = (Get-FileHash -Path $archive -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -ne $expected) {
    Remove-Item $archive -Force
    throw 'Checksum mismatch: downloaded sing-box archive rejected.'
  }
  $extract = Join-Path $env:TEMP 'iran-proxy-monitor-sing-box-extract'
  if (Test-Path $extract) { Remove-Item $extract -Force -Recurse }
  try {
    Expand-Archive $archive -DestinationPath $extract -Force
    $core = Get-ChildItem $extract -Recurse -Filter 'sing-box.exe' | Select-Object -First 1
    if (-not $core) { throw 'sing-box.exe missing from official release archive.' }
    Copy-Item -LiteralPath $core.FullName -Destination $exe -Force
  } finally {
    if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
  }
}

if (-not (Test-Core $exe)) { throw 'sing-box version verification failed.' }
# Save for future upgrades extracted to other directories. No download required next time.
if (-not [string]::Equals($sharedExe, $exe, [System.StringComparison]::OrdinalIgnoreCase)) {
  Copy-Item -LiteralPath $exe -Destination $sharedExe -Force
}
Write-Host 'Installed sing-box version:' -ForegroundColor Cyan
& $exe version
if ($LASTEXITCODE -ne 0) { throw 'sing-box core failed to run.' }

# The previous dashboard may have retained a version-specific bin\sing-box.exe path.
# Change only an empty, missing, or previously packaged bin\sing-box.exe setting.
& $venvPython (Join-Path $root 'configure_core_path.py') $exe
if ($LASTEXITCODE -ne 0) { throw 'Unable to update installed core path.' }
Write-Host 'Installation complete. Run launch.cmd. Logs appear under %LOCALAPPDATA%\IranProxyMonitor\logs.' -ForegroundColor Green
