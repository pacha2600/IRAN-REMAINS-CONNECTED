# v1.0.16 — IRAN REMAINS CONNECTED

- Renamed desktop UI, heading, instructional subtitle, Inno Setup display names and GitHub release title. Kept existing AppData path and internal executable for upgrade compatibility.
- Added 1-second **live upload/download** payload rates and cumulative **per-connection-session** byte totals from an authenticated, loopback-only sing-box Clash API.
- The subscription field accepts up to 40 HTTP(S) URLs and absolute local files separated by commas or newlines; all parsed nodes are combined and deduplicated by canonical outbound ID. Each source has independent successful-feed caching, and multi-source HTTP resumptions have independent checkpoints.
- New **Working nodes** tab shows all HTTPS-latency-passing nodes live, with speed/Flow updates when tested. The previous fully completed working-node snapshot is restored as historical on next launch. Failed scans preserve it.
- Added **best-reliable** category: historically highest HTTPS availability among nodes with current **confirmed** lower-percentile Flow Mbps >= 1.000. Matching JSON, BPF and original-URI TXT exports are automatically produced on qualifying scans.
- Added connection warning when selected TLS configuration skips certificate verification or configures an unencrypted upstream HTTP/SOCKS proxy.
- Original scanner latency, downloader, parallelism, Flow Mbps qualification, candidate counts, scheduler and other three rankings are preserved.
- Source package includes Windows build scripts for expected `IranRemainsConnected-Setup-v1.0.16-win64.exe` (not compiled in Linux environment).

See QUICK_START-v1.0.16.md and SECURITY_AND_PRIVACY-v1.0.16.md.
