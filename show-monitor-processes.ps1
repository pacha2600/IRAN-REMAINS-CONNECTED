# Read-only diagnostic: show Python processes whose command line contains this app name.
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -match 'IranProxyMonitor' } |
  Select-Object ProcessId,Name,CommandLine | Format-List
Write-Host 'To stop an older stuck monitor, close its window or use Task Manager after verifying its PID.'
