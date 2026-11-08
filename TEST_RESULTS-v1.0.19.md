# v1.0.19 verification

- Legacy regression suite: 173 tests maintained.
- New tests: 10 (source-specific 60-minute receipt, forced update, stale receipt, changed URL, explicit cached mode, HTTP CONNECT accounting, live speed/latency counters and no double counting, footer at 1060×700, scan button styles/order, source icon availability).
- Total: **183 tests**, Python 3.13 with Xvfb graphical display, passed.
- GUI smoke: 1060×700 window; fixed footer remained visible; vertically scrollable results notebook exists; live traffic labels updated.
- Windows release scripts now point to v1.0.19, including the ICO.
- No native Windows build or taskbar test, no real proxy scan, and no exact ISP packet metering were performed.
