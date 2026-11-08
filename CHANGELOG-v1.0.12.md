# Iran Proxy Monitor v1.0.12

- Added four subscription-only download transports: system, direct, manual HTTP proxy, manual SOCKS5 proxy (remote DNS). Local Karing HTTP/SOCKS listeners are supported by hostname and port.
- Added optional proxy authentication; proxy usernames/passwords remain in memory and are never saved in plaintext in settings.json.
- Added a feed proxy configuration dialog and hover tooltips.
- Added **Test saved feed (no download)** to separate fetching a blocked subscription (through Karing) from later independent benchmark tests.
- Added one multi-node sing-box Android `.bpf` for each successful JSON/TXT export category, containing the exact selected outbounds plus a mobile TUN inbound.
- Added **Make Android BPF** to convert previously exported JSON shortlists without re-running the full latency scan.
- Added offline BPF structural verification, independent Go decoder verification, SOCKS5 handshake integration tests, and saved-export regression tests.
- Added GitHub Actions Windows setup builder and Inno Setup installer recipe with a pinned official sing-box core, so end users need no Python or PowerShell.
- Retained all v1.0.11 logs, source-specific caching, partial-download recovery, scheduling, ranking, and per-node test functionality.

## Verification boundaries

- 100 automated tests pass on Linux/Python 3.13, including SOCKS5 integration and BPF multi-node tests.
- Go standard-library decoder successfully decoded the BPF payload independently.
- Tkinter smoke test passed under Xvfb.
- Windows `Setup.exe` has **not** been compiled in this Linux environment, and real Android SFA import has **not** been tested.
- Windows core validation and remote subscription download through your live Karing listener still require on-device testing.
