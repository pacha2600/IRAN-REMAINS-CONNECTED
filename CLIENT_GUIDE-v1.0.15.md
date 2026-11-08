# Iran Proxy Monitor v1.0.15 — Connect mode

## What changed

The complete v1.0.14 scan, throughput analysis, ranking, subscription handling, exports (JSON/TXT/BPF), and monitoring schedule are retained. A separate, optional **Connect** panel runs one saved/selected proxy node as a persistent local sing-box client. **No connection starts automatically.**

### How to connect

1. Use **Update subscription** or **Run one cycle** to load nodes. Select **one supported** entry in the results table, then click **Connect selected**.
2. Or, without refreshing/loading the subscription, choose **Saved shortlist** (`best-overall`, `best-download-speed`, `best-ping`), set **Rank** 1–30, and click **Connect saved node**. This reads the corresponding existing `*-latest.json` file under `%LOCALAPPDATA%\IranProxyMonitor\exports`.
3. Pick the mode before connecting:
   - **Manual HTTP/SOCKS5:** exposes HTTP CONNECT and SOCKS5 on `127.0.0.1:20808` by default; only applications configured to use it are routed through the selected proxy. Both protocols share one port. No Windows proxy setting is changed.
   - **Windows system proxy:** enables the same loopback listener and updates **per-user WinINet Internet Settings** to `127.0.0.1:<port>`. Applications that honor Windows proxy settings are routed through it; **not all applications honor WinINet**. Original settings are backed up and restored on normal Disconnect/exit. Existing PAC URL configurations are refused rather than silently replaced.
   - **Device-wide TUN:** on Windows only, requires launching **Iran Proxy Monitor as Administrator** (right-click its shortcut or executable). This launches a sing-box TUN interface with auto-routing, strict_route, and DNS interception. Other VPN/TUN clients, including Karing TUN, may conflict; stop them first. The outbound's original credentials and protocol settings are preserved.
4. Press **Test connection** to make a genuine proxied HTTPS check using your first configured connectivity endpoint. `CONNECTED` by itself means the local sing-box service is running, **not** that the selected remote server is reachable.
5. Press **Copy proxy address** to copy `http://127.0.0.1:20808`. For an app supporting SOCKS5 use `socks5://127.0.0.1:20808` instead (both are available in all three modes).
6. **Disconnect** stops the persistent core and (if still owned by this application) restores Windows proxy settings. **Stop** continues to control the scanner/auto-monitor timer only.

The client is independent of the scanner's sing-box subprocesses. To avoid skewed results, a full benchmark cannot start **while this app's TUN is connected**. You can still update subscriptions over the current TUN connection. Scans in manual/system modes are otherwise unchanged, but disconnect first for a clean baseline.

## Operational and safety notes

- The local listener binds to **127.0.0.1 only**, with no remote/LAN access and no authentication. Any local process can use this endpoint. Do not forward the port to the network.
- **No direct fallback** is configured: the selected node is the only outbound for the client. If it fails, the local proxy will fail, not silently switch to a different node.
- This is an **on-demand single-node client**, not yet a full Karing clone. It does not implement Karing's rule sets, subscription auto-switching, mobile VPN controls, or a network-level kill switch.
- Windows system proxy does **not** cover arbitrary UDP traffic, software that ignores the OS proxy, or all Windows services. TUN intercepts more traffic but must be tested on actual Windows; VPN conflicts, IPv6 behavior, and DNS privacy should be verified on the target machine. Avoid interpreting a 'connected' label as proof of leak-free tunneling.
- On Windows, a **Job Object** terminates the persistent sing-box process when the GUI crashes, to reduce the risk of orphaned TUN routes. A per-user recovery snapshot is used to restore the previous Windows proxy when the GUI is next launched after an abnormal exit. If the OS proxy remains enabled after a power failure, disable it in **Windows Settings → Network & internet → Proxy**.
- The client config contains proxy credentials, is stored temporarily with user-only permissions where available, and is removed on disconnect. Don't share the temporary config or saved shortlist exports publicly.
- Installing/uninstalling this release must not change system proxy settings. Only pressing **Connect selected / Connect saved node** in system mode does.
- Device-wide TUN is not an always-on service or kill switch. Closing the GUI disconnects it.

## Install/update locally (development ZIP)

Extract the ZIP to a new folder, open PowerShell inside `IranProxyMonitor`, and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -LocalSingboxPath 'D:\sing-box.exe'
.\launch.cmd
```

The supplied **GitHub Actions** workflow builds a Windows Setup.exe on a Windows runner using the included PyInstaller + Inno Setup recipe. The ZIP here is source; the Windows Setup.exe requires the workflow build and a Windows acceptance test before publication.

## Windows acceptance checklist

1. Manual listener: Connect selected, check `http://127.0.0.1:20808` in a browser's explicit proxy settings; press Test connection; disconnect, confirm listener closes.
2. Saved nodes: restart app (with no loaded table), connect rank 2 in `best-overall` if it exists; confirm correct node name and reconnect to rank 1.
3. System proxy: record existing Windows proxy settings; connect; verify the Settings panel shows the loopback proxy; disconnect and compare the original values. Verify unexpected core termination restores the original values without overwriting changes from Karing.
4. TUN (admin): disconnect Karing's TUN; run app as admin; connect; verify browser + DNS and normal app traffic; disconnect; confirm the virtual interface and routes are removed.
5. Try a dead node: Test connection must report failure; it must **not** fall back to a direct path.
6. Run original 10k-node benchmark in disconnected state, compare counts/shortlists with v1.0.14, and verify JSON/TXT/BPF generation.

**Verification to date:** Automated unit/integration tests and Tkinter smoke tests ran on Linux; actual Windows WinINet, elevation, Wintun, routed traffic, and installer executable have **not** been validated here.
