# v1.0.15 verification

**Automated tests**: `xvfb-run -a python -m unittest discover -s tests -q`: 134 passed on Linux / Python 3.13.

All pre-existing 121 scanner tests are retained. New tests cover:

- Client configuration in manual, Windows system-proxy, and Windows TUN modes.
- Loopback listener, one selected proxy outbound, and absence of direct fallback.
- Strict Windows TUN route options and DoH-over-selected-node configuration.
- Selecting saved shortlist category and rank without a new scan.
- Start, stop, reconnect, config-check failure, and early core exit via a simulated local core.
- System-proxy snapshot/restore, respect for Karing taking over settings, and PAC protection via simulated Windows registry.
- Scan-setting compatibility.

**Tkinter smoke test**: Under Xvfb, the GUI opened at 1340×970, its requested size was 1246×892, it populated 12,050 rows, and copied a selected entry correctly. Client mode and saved-shortlist controls were visible.

**Not tested here**: A real sing-box client on the user's Windows 11 machine; Windows Job Object behavior; UAC/TUN/WinINet routing; DNS/IP leak checks; GitHub-built Windows Setup.exe; connectivity or speed of live proxies. The project is a *source ZIP with a Windows build workflow* until that acceptance testing is performed.
