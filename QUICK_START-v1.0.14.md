# Iran Proxy Monitor v1.0.14 — Windows 11 quick start

This ZIP contains the **Python source/development build**, not the precompiled Windows one-click Setup.exe.

## Install or upgrade

Extract it to a new folder. Run from PowerShell in the inner `IranProxyMonitor` folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -LocalSingboxPath 'D:\sing-box.exe'
.\launch.cmd
```

Existing settings, cached subscriptions, SQLite history, previous JSON/TXT/BPF exports are in `%LOCALAPPDATA%\IranProxyMonitor` and are not removed when extracting a new version. To build a standalone `Setup.exe` for other Windows users, use the included `release/` and GitHub Actions workflow. The packaged Setup.exe has **not** been built/tested here.

## Download subscriptions through Karing's local SOCKS5

Click **Feed proxy settings**. There is now *one* editable mode selector, inside this dialog. Choose `manual-socks5`, set `127.0.0.1` and Karing's real **SOCKS5 listener port**, then click **Test feed route**. Click **Save proxy settings** to activate these settings. The main window now only displays the active mode; it has no second selector. The mode is used for subscription downloads, not the sing-box per-node benchmarks. In `system` and `direct` modes, the manual host/port is ignored.

Close/Cancel the proxy dialog to discard pending changes. Credentials are session-only and are never persisted.

## What Avg Mbps and Flow Mbps mean

- **Avg Mbps:** total download bytes divided by elapsed time for that HTTPS destination. One large burst may make this look good.
- **Flow Mbps:** lower-quartile *two-second* throughput, calculated from 1-second arrival buckets including zero-traffic windows. A spike followed by multi-second silence scores near zero.
- **Stable = Yes:** must transfer meaningful bytes in at least 75% of one-second buckets over a long observation, keep a meaningful lower speed floor and avoid long gaps/stalls. No longer certifies a brief 4-second burst.

The defaults now give each finalist up to **12 seconds**, needing at least **8 seconds** to qualify. Default/Fast scan buttons apply those values. Changing time/budget can reduce the number of qualifying nodes; the app never replaces good old shortlists with empty rankings. Full scans still have the same aggressive latency strategy and the default 250 preliminary speed candidates. Up to 15 finalists are confirmed, limited by the download budget.

`Best download speed` and `Best overall` now use the **Flow Mbps** metric. `Best ping` still includes nodes with a real preliminary download, even if not confirmed consistent—this is intended for lightweight messages rather than media.

Flow metrics are still test-host-specific. For a candidate you intend to use, press **Compare selected** to check a second host, and do a real browsing/messaging test in Karing.

## Automatic mode and exports

**Run one cycle** is manual. **Start auto monitoring** waits `Refresh min` before the first scan. **Run once + auto** runs now and schedules its next scan `Refresh min` after completion. Hibernate time counts. In definite offline conditions auto scanning pauses without deleting previous exports. The GUI must stay open for its timer to operate.

Valid shortlists automatically export three categories in JSON, share-link TXT where available and Android BPF (no extra BPF button). Find them in `%LOCALAPPDATA%\IranProxyMonitor\exports`.

Logs: `%LOCALAPPDATA%\IranProxyMonitor\logs\monitor.log`.
