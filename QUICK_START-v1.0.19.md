# IRAN REMAINS CONNECTED v1.0.19 — quick start

Extract the source ZIP into a new folder, then open PowerShell from the `IRAN-REMAINS-CONNECTED` directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -LocalSingboxPath 'D:\sing-box.exe'
.\launch.cmd
```

Your subscriptions, saved nodes, traffic history, proxy settings and exports remain under `%LOCALAPPDATA%\IranProxyMonitor`.

## Subscription update policy

**Update subscription** always downloads the selected remote sources (or reads local files) and reparses the combined pool without benchmarking. A normal **Run one cycle** or an automatic scan reuses the last successful response from each *exact remote URL* if it was downloaded less than 60 minutes ago. After 60 minutes, or after an unsuccessful update, the normal cycle tries the network. A changed URL or a failed source never borrows a different source's cache. The first cycle after upgrading from an older version without a successful-download receipt may still download once. **Test saved feed (no download)** is different: it deliberately uses a saved snapshot regardless of age, with clear identification.

## Scan data monitor

The seventh summary card shows **Scan HTTP MiB ≥** as a *live* measured lower bound. The bottom fixed status bar splits bytes into **Feed**, **Latency** (HTTP CONNECT/request/response headers), **Speed** (download response bodies) and **Baseline** (direct download bodies), all converted from bytes to MiB. Values are reset for each new cycle and retained in the completed cycle statistics. They will not match the exact bytes billed by the ISP: TLS handshakes, encrypted upstream traffic, retransmissions, DNS, failed/unobserved transfers and other overhead cannot be counted from these Python-level measurements. A canceled or failed cycle may have consumed additional unmeasured traffic.

## Interface / icon

The dashboard scrolls vertically when not maximized, while the bottom two-line status and version indicator remain pinned to the window bottom. The primary scan actions are on their own row, in the requested order; only **Run once + auto** uses blue. All other scan, import/export, and connection functions remain available.

The source launch invokes `pythonw.exe`; Windows may use the Python shortcut's cached taskbar icon, especially for an old pinned shortcut. The new code sets the Tk icon and native Windows small/large window icons. For a permanent branded taskbar application, build the Windows `.exe` using `release/build-windows.ps1` or the GitHub Actions Windows release workflow, then unpin old `pythonw.exe` shortcuts and pin the installed `IranRemainsConnected.exe`. Windows behavior must be checked on Windows 11.

## Safety

Windows device-wide TUN still requires administrator rights. There is no full kill switch and no independent Windows privacy audit. Manual proxy mode only routes applications configured to use the local proxy; TUN routing and system-proxy restoration should be tested before wide distribution.
