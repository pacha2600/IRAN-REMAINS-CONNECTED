# IRAN REMAINS CONNECTED v1.0.16 — Verification report

**Local environment:** Linux Python 3.13 with a virtual X display (`xvfb-run`), not Windows 11. The package is source code and GitHub Actions installer recipe; no Windows `Setup.exe` was generated here.

## Checks completed

- `python -m compileall -q iran_proxy_monitor` — passed.
- `xvfb-run -a python -m unittest discover -s tests -q` — **152 tests passed**, including all v1.0.15 scanner regressions, plus new multi-source, snapshot, metrics and GUI tests.
- Source pool: newline/comma splitting, 40-source validation, duplicate URL suppression, canonical node deduplication across sources, stable order-insensitive source-set IDs, per-source cache fallback, incomplete feed diagnostics, update-only parsing without starting sing-box.
- Multi-source HTTPS resume: two simulated stalled downloads create **separate** saved partial bodies with private source-keyed names. Existing single-source resume tests remain valid.
- Best reliable: verified conservative Flow Mbps >= 1.000 enforced; higher historical HTTPS success ranks first; high average-but-low-flow and unverified nodes excluded.
- Traffic: loopback-only API configuration, per-session bearer secret, real local HTTP test of cumulative byte endpoint, monitoring thread converts total counters into transfer rates.
- Security: warning triggers for `tls.insecure` and upstream unencrypted HTTP/SOCKS proxies; core configuration does not add a direct fallback.
- Persistence: last successful HTTPS working-node pool is atomically saved and loaded, including all latency-passing nodes (not only the speed-tested top 250); broken snapshots fail safely.
- GUI: multi-line subscription editor and working-results notebook; selected working node can be retrieved for copying/connection.
- Additional 12,050-node GUI smoke test: loaded all entries and 500 successful HTTPS results into the working tab in the virtual display, with working-tab selection verified. The measured insert+update time in this environment was ~0.6 seconds; this is **not** a Windows performance benchmark.
- Source regression check: scanner `engine.py` is unchanged from v1.0.15 (same HTTPS/Flow benchmarks).

## Not tested / limits

- Running the official Windows sing-box 1.14.4 core with an active Clash API and checking counters against physical NIC bytes.
- Real traffic through Manual/System Proxy/TUN modes on Windows 11; DNS or IPv6 leak prevention; Windows administrator elevation, service restart, sleep/resume, anti-virus and crash behavior.
- Importing generated BPF on a physical Android device.
- The GitHub Actions Windows build workflow and Inno Setup installer compilation, actual sign-and-install tests.
- Live subscription downloads from partially blocked Iranian networks, throughput across multiple real ISPs or malicious-subscription threat modeling.

**Release readiness:** suitable for user testing of v1.0.16 source features. Treat as a **beta** for public connectivity/security claims until Windows acceptance and privacy leak tests are completed.
