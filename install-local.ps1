# Personal/offline setup: reuse D:\sing-box.exe; configure the remote OpenRay feed.
# The public install.ps1 retains the official downloadable core fallback.
param(
  [string]$LocalSingboxPath = 'D:\sing-box.exe',
  [string]$SubscriptionUrl = 'https://raw.githubusercontent.com/sakha1370/OpenRay/refs/heads/main/output/all_valid_proxies.txt'
)
$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot 'install.ps1'
& $installer -LocalSingboxPath $LocalSingboxPath -NoDownload
if (-not $?) { throw 'Local installation failed.' }
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
  throw 'The installer did not create the expected Python environment.'
}
& $venvPython (Join-Path $PSScriptRoot 'configure_subscription_source.py') $SubscriptionUrl --if-empty
if ($LASTEXITCODE -ne 0) { throw 'Could not configure the local subscription source.' }
Write-Host 'Local core installed; existing subscription selection preserved; new installs default to OpenRay URL. Run launch.cmd.' -ForegroundColor Green
