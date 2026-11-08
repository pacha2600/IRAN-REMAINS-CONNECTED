# v1.0.18

- Added Encryption and Security /100 to All nodes and Working nodes, with contextual per-node explanations. The heuristic is based on normalized outbound settings, *not* a live security audit.
- Applied a tiered configuration-security penalty to Best overall ranking only. Kept the scanner's latency, Flow Mbps, throughput, reliability and other ranking algorithms unchanged.
- Expanded Recent connections to show every scan-pool column plus connected timestamp and mode; captured available metrics when a profile is connected, preserving compatibility with old metric-free entries.
- Switched connection mode automatically on dropdown selection while connected: preflight, stop old core, start new mode with same node; attempt rollback on failed startup. Guarded TUN without administrator permission.
- Added section separators to distinguish sources, scan settings and client controls; retained the status and metrics positions above the result tabs. Removed the redundant reliability explanation line.
- Applied the Windows `.ico` as the final Tk window/taskbar icon and included `.ico` in the PyInstaller runtime data. Preserved the PyInstaller executable icon, Inno Setup icon and stable Windows taskbar application ID.
- Updated release build scripts and documentation to v1.0.18.
