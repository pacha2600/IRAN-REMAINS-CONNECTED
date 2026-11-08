# IRAN REMAINS CONNECTED v1.0.19

- Bottom status bar anchored outside the scrollable main dashboard. Displays the application version, scanner messages, and live HTTP accounting; remains visible when the window is not maximized.
- Main dashboard scrolls vertically on smaller Windows displays, so a dense settings panel cannot permanently hide results tabs or their controls.
- Subscription cache TTL of 60 minutes per exact remote subscription URL. Full scans and automatic scans use a verified successful response less than 60 minutes old. **Update subscription** forces a new fetch every time. An explicit **Test saved feed (no download)** remains independent of TTL. Local files are loaded from disk each time so edits are noticed.
- Last-success per-source receipts are stored beside source-scoped snapshots using SHA-256 URL identifiers. Stale fallback snapshots are not presented as recent updates. On first upgrade from v1.0.18, older snapshots without receipts are not treated as fresh automatically.
- Live measured scan traffic by phase: downloaded feed response bytes, HTTPS latency HTTP CONNECT/response headers, speed-test downloaded bodies, and direct baseline downloaded bodies. Visible in the seventh summary card and the anchored bottom line. Measured HTTP-layer lower bounds do NOT include TLS handshakes, proxy protocol, encryption overhead, lost packets, and unobserved failed traffic.
- Scan buttons in the requested order across two compact lines: Update subscription, Run one cycle, Start auto monitoring (neutral), Run once + auto (blue), Stop, View logs, Copy selected, Save selected, Compare selected.
- Native Windows title bar/taskbar icon fix: application-specific process ID is retained; ICO is loaded with 64-bit-safe Windows API signatures and assigned to the wrapper's 16px and 32px slots. PNG remains the Tk fallback. The PyInstaller bundle and Inno Setup already embed the ICO. **Actual Windows taskbar behavior cannot be tested from Linux.**
- Preserves existing connection lifecycle, automatic BPF/TXT/JSON exports, Flow Mbps ranking and security scores.

Windows build artifact target: `IranRemainsConnected-Setup-v1.0.19-win64.exe` (not included in source ZIP).
