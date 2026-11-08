# v1.0.13 verification — 2026-11-07

Environment: Linux container, Python 3.13.5, Tkinter + Xvfb; no live user proxy or Windows machine was available.

- `python -m unittest discover -s tests -q`: **111 tests passed** in approximately 3.5 seconds.
- `python -m compileall -q iran_proxy_monitor`: passed.
- Tkinter GUI smoke test under Xvfb: opened the application, found Start auto monitoring, Run once + auto, Default scan, Fast scan, Feed proxy settings; confirmed BPF button absent; toggled presets; armed and disabled the timer. Passed.
- Tkinter feed proxy dialog smoke test: opened dialog, verified `Test feed route` and `Save proxy settings` buttons. Passed.
- `test_v113`: 11 regression tests for Python 3.13+ urllib `HTTPSHandler` private-attribute removal, real TLS-over-SOCKS5 with remote DNS, wrong port/protocol failure, scheduler wall-clock sleep semantics, retry semantics, definitive-route pause behavior, and zero-results preservation. Passed.
- Automatic BPF generation tests from v1.0.12 remain included and pass (JSON outbounds == BPF outbounds, multi-node BPF, non-empty validation guard).

Outstanding platform-specific validation: Windows 11 with Python 3.15.2 and the user's actual Karing SOCKS5 listener, blocked subscription download, Android sing-box BPF import, Windows GitHub Actions `Setup.exe` build. The release source ZIP is not the compiled Windows installer.
