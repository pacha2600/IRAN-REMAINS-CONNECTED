# IRAN REMAINS CONNECTED v1.0.18 — Quick start (Windows 11)

## Install this source build

Extract the ZIP to a new folder. In PowerShell in `IRAN-REMAINS-CONNECTED`:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -LocalSingboxPath 'D:\sing-box.exe'
.\launch.cmd
```

The release-building workflow at `.github/workflows/windows-release.yml` can create the **one-wizard** `IranRemainsConnected-Setup-v1.0.18-win64.exe` on a Windows runner. That installer is **not included** in this source ZIP. On Windows, the installer uses the existing black-circle `.ico` for the installed executable, wizard, shortcuts, and taskbar icon; if an older version was pinned to the taskbar, unpin the stale shortcut and pin the new application again.

## New columns and ranking

**Encryption** identifies the configured *proxy-hop* protection: for example TLS, REALITY/TLS, Shadowsocks AEAD, or Plain SOCKS. **Security /100** is a configuration-only heuristic, not an external cryptographic test or anonymity rating. Right-click a node and choose **Explain encryption / security score** to see its assumptions. Nodes without identified encryption have a substantially lower security score and are penalized in **Best overall**. The Best speed, Best ping, and Best reliable definitions otherwise remain unchanged. [Read the complete scoring criteria](SECURITY_SCORE-v1.0.18.md).

These columns appear in **All nodes**, **Working nodes**, and **Recent connections**. Recent also retains the time and mode, and stores available measurements from when you connected. Unknown past measurements display as `—`. Last ten connection records and their outbound credentials remain private under `%LOCALAPPDATA%\IranProxyMonitor\client-recent.json`.

## Changing modes while connected

Select a different **Mode** from the dropdown while the client is connected. The app will try to validate the new sing-box configuration **before** disconnecting the current session, then stop and restart the **same node** using that mode. If startup fails, it attempts to restore the previous mode. A connection *can* interrupt during the handoff: do not expect seamless streams or a VPN kill switch. TUN is only available when the application runs as administrator on Windows. Manual proxy mode is still useful for selective site-based routing through browser extensions.

If no client is connected, changing the dropdown only chooses the mode for your next connection. The status and totals above the results table are unchanged.

## Visual organization and icon

Subtle separators now divide **GENERAL / SOURCES**, **SCAN / MONITOR**, and **CONNECT / PROXY**. The redundant reliability description underneath shortlist selection has been removed; hover help is still available. The window/taskbar icon is loaded from `assets/iran-remains-connected.ico` on Windows, with the PNG used as an additional Tk fallback.

## Other features retained

All prior combined subscriptions, 13,000+ node scanning, sustained Flow Mbps, independent tab sorting, automatic JSON/TXT/BPF exports, daily lower-bound scan traffic and live client traffic remain in place. This source upgrade retains `%LOCALAPPDATA%\IranProxyMonitor` to preserve settings, recent connections, shortlists and history. Check the scan network independence when benchmarking: disconnect a TUN client first.
