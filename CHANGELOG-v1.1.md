# IRAN REMAINS CONNECTED v1.1 — first public release candidate

## Desktop layout and usability

- Restored an adaptive dashboard: normal-height windows expand the results tabs rather than wasting space in an outer canvas.
- The outer scrollbar is hidden when the dashboard fits, and appears only if the content is taller than the viewport. The mouse wheel scrolls the outer dashboard over controls, while Treeview and Text widgets retain their own wheel behavior.
- An expandable **Advanced scan settings** section retains detailed tuning without pushing results below the fold. The important **Probe ALL supported nodes** and **Test saved feed** switches remain visible.
- The footer stays fixed at the bottom at all window sizes, including live per-cycle HTTP-layer traffic and the version.
- Exclusive monitor action states: Update subscription, Run one cycle, Start auto monitoring, and Run once + auto disable other competing controls while a cycle or automatic timer is active. Stop remains available. A Stop request does not unlock controls prematurely; they are enabled when the worker actually exits.
- Retains previous scan logic, Flow Mbps ranking, four shortlist types, matched BPF/JSON/TXT exports, subscription merges and source cache, security scoring, connection history, and Manual/System Proxy/TUN connection modes.

## Windows publishing

- Updated version metadata to **1.1**, `IranRemainsConnected-Setup-v1.1-win64.exe`.
- GitHub Actions produces the single bundled installer from Python, PyInstaller, Inno Setup, and SHA-256-verified sing-box **1.14.4**. No separate Python or sing-box installation is required by end users.
- Includes release checksum and preparation guide. GitHub Actions / native Windows TUN remain awaiting user verification.

## Limitations

Manual/System Proxy routing applies only to participating applications; TUN lacks a leak-tested kill switch. Traffic estimates count observed HTTP-layer payload/headers rather than ISP billing usage. Windows installer execution, code-signing, and actual routing remain to be validated on a real Windows PC.
