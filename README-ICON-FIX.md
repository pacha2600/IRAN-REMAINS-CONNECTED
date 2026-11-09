# IRAN REMAINS CONNECTED v1.1 — Windows titlebar/taskbar icon patch

This is a targeted fix for the published Setup.exe showing the correct icon on its shortcut but a generic icon on the **running** window and taskbar.

## Files to copy to the ROOT of the GitHub repository

- `iran_proxy_monitor/gui.py` — applies the icon to Windows' decorated top-level HWND at startup and mapping; cleans up callbacks safely.
- `iran_proxy_monitor/windows_icon.py` — explicit small/large WM_SETICON, Tk top-level discovery via GetAncestor, class fallback, frame update.
- `tests/test_v11_windows_icon.py` — on Windows, verifies both icon sizes on the real HWND; skips on non-Windows.

No scan/ranking/network/proxy/TUN code was changed. The version stays **1.1**.

## Install/test workflow

1. Unzip the patch.
2. In GitHub Desktop, choose Repository > Show in Explorer.
3. Copy **iran_proxy_monitor** and **tests** folders from this ZIP into the repository folder, merging/replacing files.
4. Commit `Fix Windows titlebar and taskbar icons` and **Push origin**.
5. Trigger the Windows Setup EXE workflow manually on `main` (DO NOT tag or publish yet).
6. Confirm the **Windows-only native icon test passes** and download the new Setup.exe artifact.
7. Exit the old application; install the new Setup.exe over the old version.
8. Launch from the Start menu. Unpin old taskbar icons and pin the running app again if Windows caches the prior icon.

## Verification

Linux/Xvfb: 197 tests passed (one Windows-only test skipped). No direct Windows UI screenshot or live Win11 icon test was possible here.

If the new taskbar/titlebar icon still does not appear, inspect `%LOCALAPPDATA%\\IranProxyMonitor\\logs\\monitor.log` for `application-icon-warning`, send a screenshot and the last 50 log lines. This patch records an `application-icon-applied` event for diagnostics.
