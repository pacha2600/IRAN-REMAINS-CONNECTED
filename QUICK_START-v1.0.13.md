# Iran Proxy Monitor v1.0.13 — Quick start (Windows 11)

This is the Python **source package**, not a precompiled Windows Setup.exe. Your existing `%LOCALAPPDATA%\IranProxyMonitor` settings, previous shortlists and historical data remain untouched by extraction.

## Install and run

Extract the ZIP to a *new* folder. Open PowerShell in the nested `IranProxyMonitor` folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -LocalSingboxPath 'D:\sing-box.exe'
.\launch.cmd
```

If `D:\sing-box.exe` is unavailable, run `install.ps1` without `-LocalSingboxPath`. It reuses a previously cached verified core if available; otherwise it downloads and verifies the pinned official release. Python 3.11+ is required for the source ZIP (including Python 3.15). The **Windows Setup.exe** recipe for nontechnical users is in `.github/workflows/windows-release.yml`.

## Fetch a censored feed through Karing (without TUN)

1. In Karing, confirm that its local SOCKS5 listener is **enabled** and note its actual port. Its HTTP proxy port might be different.
2. Choose **Feed network: manual-socks5** in Iran Proxy Monitor. The mode selector and **Feed proxy settings** button are side by side.
3. Enter **127.0.0.1** and the *SOCKS5* port, click **Test feed route**, then **Save proxy settings**.
4. With the subscription URL in the main screen, choose **Update subscription**. The feed timeout (default 300s) allows slow/stalled reads; it is not a total deadline.
5. If Karing is still tunneling all app traffic via TUN, disable that for *independent* proxy benchmarks. Check **Test saved feed (no download)** and then **Run one cycle** to test the recently downloaded source without needing Karing for fetching.

If Karing only offers an **HTTP CONNECT listener**, choose `manual-http` with its corresponding port. In `system` or `direct` mode the manual IP/port are **not used**. A failure of the 12-second quick route test may reflect a slow feed; it is diagnostic, and the longer normal update can still be attempted.

## Buttons and timing

- **Run one cycle**: start now, once.
- **Start auto monitoring**: arm a wall-clock timer, first scan in **Refresh min** minutes, *not* now.
- **Run once + auto**: run now, then next scan **Refresh min** after it completes.
- **Stop**: disable auto timer and request cancellation.
- **Default scan / Fast scan**: balanced and aggressive presets above the detailed settings.

Sleep/hibernate counts toward the timer. If the due time expires while the laptop sleeps, a single scan is initiated after resume. If Windows has *no outbound IPv4/IPv6 route*, the auto scan is paused, retries after five minutes, and previous exports are left alone. Since an Iranian connection can block public probes while remaining online, the app never assumes a timeout alone means there is no internet. No successful measured traffic => previous saved outputs and rankings are retained. Automatic monitoring requires this GUI to remain open.

## Exported formats

When category results qualify, the app automatically writes `best-download-speed`, `best-ping`, and `best-overall` shortlist files in `%LOCALAPPDATA%\IranProxyMonitor\exports` as `.json` and `.bpf`, plus `-share-links.txt` when the original nodes have share URIs. Each `.bpf` contains exactly the same selected proxy **outbounds** as its JSON, and can include several nodes. It is not a single share link.

Detailed logs: `%LOCALAPPDATA%\IranProxyMonitor\logs\monitor.log`.

## Verification and limitations

111 offline unit and integration tests passed on Linux/Python 3.13, including a real local TLS connection through a simulated SOCKS5 proxy and simulated network outages/sleep. The Tkinter GUI and proxy settings popup opened in an Xvfb graphical test. The changes target the Python 3.15 handler regression reported in your logs. **An actual Windows 11/Karing session, Android BPF import and Windows Setup.exe have not yet been end-to-end tested in this environment.**
