# Optional: scheduled cycles run even when GUI is closed, using Windows Task Scheduler.
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $MyInvocation.MyCommand.Path
$exe=Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $exe)) { throw 'Run install.ps1 first.' }
$interval=120
$settingsFile=Join-Path $env:LOCALAPPDATA 'IranProxyMonitor\settings.json'
if (Test-Path $settingsFile) {
  try {
    $settings=Get-Content $settingsFile -Raw | ConvertFrom-Json
    if ($settings.refresh_minutes -ge 5 -and $settings.refresh_minutes -le 10080) { $interval=[int]$settings.refresh_minutes }
  } catch { Write-Warning 'Settings unavailable; defaulting to 120 minutes.' }
}
$action=New-ScheduledTaskAction -Execute $exe -Argument '-m iran_proxy_monitor.cli --once' -WorkingDirectory $root
$trigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes $interval)
Register-ScheduledTask -TaskName 'Iran Proxy Monitor' -Description 'Refresh proxy shortlist every two hours' -Action $action -Trigger $trigger -Force | Out-Null
Write-Host "Scheduled every $interval minutes. Disable with disable-task.ps1."
