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
# Download a pinned release. GitHub release-asset endpoints can return 504 from
# GitHub-hosted runners; SourceForge is an independently hosted project mirror.
# Never install *anything* from either endpoint unless SHA256 matches the
# independently pinned official release hash above.
function Test-PinnedArchive([string]$candidate, [string]$expected) {
  if (-not (Test-Path -LiteralPath $candidate)) { return $false }
  try {
    $actual = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
    return $actual -eq $expected
  } catch { return $false }
}

$assetName = "sing-box-$version-windows-amd64.zip"
$downloadUrls = @(
  "https://github.com/SagerNet/sing-box/releases/download/v$version/$assetName",
  "https://sourceforge.net/projects/sing-box.mirror/files/v$version/$assetName/download",
  "https://downloads.sourceforge.net/project/sing-box.mirror/v$version/$assetName"
)
if (Test-PinnedArchive $archive $expectedSha256) {
  Write-Host 'Using SHA256-verified cached official sing-box archive.'
} else {
  if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
  $downloaded = $false
  foreach ($sourceUrl in $downloadUrls) {
    for ($attempt = 1; $attempt -le 2; $attempt++) {
      # Use a new temporary file for each attempt: never accept truncated or
      # accidentally concatenated downloads from failed attempts.
      $temporary = "$archive.downloading"
      if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
      try {
        $origin = ([uri]$sourceUrl).Host
        Write-Host "sing-box download: host=$origin attempt=$attempt/2"
        Invoke-WebRequest -Uri $sourceUrl -OutFile $temporary -UseBasicParsing -TimeoutSec 150 -MaximumRedirection 10
        if (-not (Test-PinnedArchive $temporary $expectedSha256)) {
          throw "Downloaded sing-box archive failed pinned SHA256 verification (host=$origin)."
        }
        Move-Item -LiteralPath $temporary -Destination $archive -Force
        $downloaded = $true
        Write-Host "Verified sing-box v$version SHA256 from $origin"
        break
      } catch {
        # No unverified artifact survives a failed attempt.
        Write-Warning "sing-box download failed or hash mismatched (host=$origin, attempt=$attempt): $($_.Exception.Message)"
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
        if ($attempt -lt 2) { Start-Sleep -Seconds 3 }
      }
    }
    if ($downloaded) { break }
  }
  if (-not $downloaded) {
    throw 'Cannot retrieve SHA256-verified sing-box 1.14.4 from official GitHub or its mirror. Build halted; no unverified binary will be bundled.'
  }
}
# Re-verify immediately before extraction, including on cached downloads.
if (-not (Test-PinnedArchive $archive $expectedSha256)) {
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
# Ship our own GPL terms and third-party/source notices alongside upstream notices.
foreach ($file in @('LICENSE', 'THIRD_PARTY_NOTICES.md', 'SOURCE_AND_COMPLIANCE.md')) {
  Copy-Item (Join-Path $root $file) (Join-Path $licenseDir $file) -Force
}
# Keep corresponding sing-box source together with the binary release.
# Obtained from the exact official tag; binary itself is hash-verified above.
$outputDir = Join-Path $root 'release-output'
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
$sourceZip = Join-Path $outputDir "sing-box-v$version-source.zip"
# codeload is independent of GitHub release-asset delivery.
$sourceUrls = @(
  "https://codeload.github.com/SagerNet/sing-box/zip/refs/tags/v$version",
  "https://github.com/SagerNet/sing-box/archive/refs/tags/v$version.zip"
)
$sourceFetched = $false
foreach ($sourceUrl in $sourceUrls) {
  try {
    if (Test-Path $sourceZip) { Remove-Item $sourceZip -Force }
    Invoke-WebRequest -Uri $sourceUrl -OutFile $sourceZip -UseBasicParsing -TimeoutSec 150
    if ((Get-Item $sourceZip).Length -lt 1024) { throw 'Source archive too small.' }
    $sourceFetched = $true
    break
  } catch { Write-Warning "sing-box source retrieval failed: $($_.Exception.Message)" }
}
if (-not $sourceFetched) { throw 'Could not download matching sing-box source archive.' }
Add-Type -AssemblyName System.IO.Compression
$sourceArchive = [System.IO.Compression.ZipFile]::OpenRead($sourceZip)
try {
  $entryNames = @($sourceArchive.Entries | ForEach-Object { $_.FullName })
  if (-not ($entryNames | Where-Object { $_ -match '/LICENSE$' })) { throw 'sing-box source archive lacks LICENSE' }
  if (-not ($entryNames | Where-Object { $_ -match '/go.mod$' })) { throw 'sing-box source archive lacks go.mod' }
} finally { $sourceArchive.Dispose() }
Copy-Item (Join-Path $root 'THIRD_PARTY_NOTICES.md') (Join-Path $outputDir 'THIRD_PARTY_NOTICES.md') -Force
Copy-Item (Join-Path $root 'SOURCE_AND_COMPLIANCE.md') (Join-Path $outputDir 'SOURCE_AND_COMPLIANCE.md') -Force
$iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
if (-not (Test-Path $iscc)) { $iscc = Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe' }
if (-not (Test-Path $iscc)) { throw 'Install Inno Setup 6 on your build computer, or run GitHub Actions.' }
& $iscc (Join-Path $root 'release\IranProxyMonitor.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup packaging failed.' }
Write-Host "Ready: $root\release-output\IranRemainsConnected-Setup-v1.1-win64.exe" -ForegroundColor Green
