# IRAN REMAINS CONNECTED v1.1 — verification report

- **195 automated Python unit/integration tests passed**, including the complete 183-test v1.0.19 regression suite and 12 new tests for adaptive sizing, mouse-wheel behavior, exclusive monitor controls, preserved advanced settings, release metadata, and packaged-core fallback.
- Tkinter GUI geometry: `1600×960` and `1380×900` display results without an outer scrollbar. At `1060×700` an outer scrollbar appears; mouse-wheel events over monitor buttons scroll the dashboard. Mouse-wheel events on Treeview keep the table's native scroll behavior.
- Advanced settings expand and collapse without altering the configured values; the footer remains visible and the version string matches the Inno Setup metadata.
- **Large-list GUI smoke:** 13,500 synthetic pool nodes and 400 working nodes displayed, with independent column sorting and small-window wheel scrolling.
- The v1.0.19 scan engine, subscription loader, throughput algorithm, scheduler, proxy client and exporter are unchanged by v1.1.
- Windows Setup.exe recipe has a pinned sing-box v1.14.4 SHA-256 (verified against the public Scoop manifest), an installer artifact check, and release SHA256SUMS output.

## Not verified here

The actual Windows **Setup.exe has not been compiled or installed** in this Linux environment. GitHub Actions execution, Windows taskbar identity, native DNS/TUN routing, real subscription download, and proxy traffic leak protection require testing on Windows 11 before public distribution.

## Reproduce tests

On Linux with a graphical virtual display: `xvfb-run -a python -m unittest discover -s tests -q`. On Windows with a working Tkinter installation: `python -m unittest discover -s tests -q`.
