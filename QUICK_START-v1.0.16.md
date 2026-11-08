# IRAN REMAINS CONNECTED v1.0.16 — Windows Quick Start

This is the **source/development package**, not a precompiled Windows executable. It upgrades v1.0.15 without removing any scan algorithm, endpoint, ranking, or monitoring control. It reuses `%LOCALAPPDATA%\IranProxyMonitor` (including saved feed and history) and your existing `D:\sing-box.exe` if configured.

## Install on the development Windows 11 computer

Extract the ZIP, open PowerShell in the folder containing `main.py`, and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -LocalSingboxPath 'D:\sing-box.exe'
.\launch.cmd
```

Public release users will eventually install `IranRemainsConnected-Setup-v1.0.16-win64.exe`, built with the bundled GitHub Actions Windows workflow. The installer itself has **not** been compiled or tested here.

## Feed pool

Paste up to **40** absolute local paths or HTTP(S) subscription URLs into **Subscriptions**, separated by new lines or commas:

```text
https://provider-one.example/subscription
https://provider-two.example/subscription, C:\Users\User\Downloads\extra-nodes.txt
```

Commas are separators, including commas inside source URLs/filenames; avoid using commas in individual source addresses. Identical source addresses and identical supported proxy outbounds are deduplicated. The number labeled **Total nodes** includes source lines before cross-source deduplication; **Supported** counts unique translated nodes. Sources are downloaded one by one; each has its **own** saved successful body, and multi-source downloads have independent partial/resume files so one blocked source cannot erase another's progress. Missing or failed sources are individually reported; incomplete pools are explicitly marked. Different sources never share cached nodes accidentally.

**Update subscription** reads/downloads each source without testing. **Run one cycle** combines the available sources and scans each *unique* supported node once, preserving the same existing latency, download, ranking, budget and auto-monitoring algorithms. Use **Feed proxy settings** if Karing's local SOCKS5 or HTTP proxy is needed to download blocked source URLs. To avoid skewing benchmarks, disconnect Karing before running a scan. **Test saved feed (no download)** lets you scan locally cached source bodies without fresh downloads.

## Results tabs

**All nodes · combined pool** shows the entire deduplicated pool, including unsupported and failed checks.

**Working nodes · HTTPS passed** fills *live* as proxies respond successfully to the HTTPS header probe and continues receiving speed/confirmation updates. **HTTPS passed does not necessarily mean confirmed download performance or guaranteed VPN usability.** All latency-passing nodes appear, including those not selected among the 250 speed candidates. The list from the *last successfully completed scan* is saved privately and shown after restart as **Previous scan**. A new scan replaces it; incomplete/failed cycles preserve it.

Both tabs support copying original share links and connecting selected nodes. The original subscriptions are never overwritten.

## Reliability-first shortlist

Choose **best-reliable** in the Saved shortlist dropdown and **Connect saved node**. This shortlist is produced automatically alongside best-overall, best-download-speed and best-ping, including matching JSON/BPF and original URI TXT where available. To qualify for best-reliable, the node must have a **current confirmed Flow Mbps ≥ 1.000** (conservative lower-percentile measurement, *not* the short average) and is sorted by historical HTTPS probe success estimate, then by confirmed flow speed. If no nodes qualify, previous best-reliable files remain untouched; check their age before connecting.

## Connect + traffic meters

Connect using Manual HTTP/SOCKS5, Windows system proxy, or elevated TUN. When the client starts, its status line shows the node, mode, localhost port and **live rates** `↓ KB/s ↑ KB/s`, followed by **cumulative session totals** `Total ↓ MiB ↑ MiB`. Download (`↓`) is data delivered to your device through the client; upload (`↑`) is data sent from your device via the client. The sing-box API measures payload counters, not total physical Ethernet/Wi-Fi bytes (headers/overhead can differ). Totals reset with each newly started sing-box client session; they are not lifetime per-node totals. During startup or an unavailable API, the status explicitly says traffic data are unavailable instead of fabricating readings.

A per-session, randomly authenticated Clash-compatible metrics API is bound to **127.0.0.1**; it is never exposed to the LAN. Manual proxy itself is also loopback-only. Only connections traversing this application's sing-box client are counted.

## What this does not establish

The code passed automated simulated/local tests, but **Windows TUN, DNS leak protection, real Karing comparisons, and traffic-counter behavior with your sing-box 1.14.4 binary remain untested on your device.** There is no VPN kill switch, no always-on background service, and no claim of equivalence to Karing's full rule engine. See [SECURITY_AND_PRIVACY-v1.0.16.md](SECURITY_AND_PRIVACY-v1.0.16.md) and run the acceptance checklist before a public release.
