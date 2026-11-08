# IRAN REMAINS CONNECTED v1.0.18 — Verification

## Results completed here

- **173/173 Python unit and regression tests passed** using Linux/Python 3.13 with a virtual Tk desktop. The v1.0.17 baseline included 161 tests; 12 new v1.0.18 tests cover the security classification and scores, ranking downgrade, legacy/new Recent metadata, table-column parity, reconnect-to-new-mode, validation failure with old connection preserved, startup failure rollback, and preventing unauthorized TUN selection.
- **13,500-row GUI smoke passed:** 13,500 synthetic pool nodes and 450 working nodes populated, new encryption/security columns displayed, main/working sorting stayed independent, Recent tab contained all pool columns plus timestamp/mode, and the window closed cleanly.
- **Windows ICO contents inspected:** sizes 16, 24, 32, 48, 64, 128 and 256 pixels. PyInstaller script embeds the ICO as the executable icon and includes it as a runtime data asset; Inno Setup also uses the ICO for the installer. The GUI explicitly calls Tk `iconbitmap` on Windows after `iconphoto`, and `main()` registers a stable Windows taskbar app ID.
- **Source/version checks passed:** version 1.0.18 in Python, PowerShell release recipe and Inno Setup definition; no unverified Windows binaries bundled.
- **ZIP integrity verified** after packaging; see delivery link and archive entry count in the response.

## What remains unverified

- Native **Windows 11** execution and taskbar/pinned-shortcut appearance.
- Live transitions between Manual, Windows System Proxy and administrator-only TUN with an actual sing-box core, including rollback after startup failures. Test DNS/IP leaks and routing; **there is no device-wide kill switch**.
- Cryptographic properties of individual server implementations, real TLS negotiations and operator trust. The new **Security /100** is a *static configuration heuristic*, not a security audit.
- Performance of the scanner against the user's Iranian connection. No latency or throughput algorithms were altered in this patch, except for a new **Best overall ranking penalty** for weak/missing proxy-hop protection.
- Creation of the standalone Windows `Setup.exe`. The included GitHub Actions recipe requires a Windows runner and is not a precompiled installer.

## User log reviewed

The uploaded log on 2026-11-08 ended with a completed scan: `attempted=13106`, `passed=212`, `core rejected=293`, `speed_tested=67`, and repeated successful `client-connected mode=manual` entries. This release focuses on the requested GUI/security and mode-switch changes rather than claiming to fix those network-dependent scan failures.
