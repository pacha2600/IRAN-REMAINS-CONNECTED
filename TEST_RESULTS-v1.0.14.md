# v1.0.14 validation

- Executed: `xvfb-run -a python -m unittest discover -s tests -q`.
- Outcome: 121 tests passed, including 10 new flow/UI tests, on the Linux test environment.
- Additional checks: Python syntax compilation; Tk modal tests under a virtual display; a Tk GUI smoke test loaded 11,800 synthetic nodes and displayed all ten table columns.
- Coverage added: continuous flow vs 4-second bursts; alternating on/off bursts; small drips hiding a burst; ranking by flow floor instead of mean Mbps; upgrade of exact old preset durations; GUI has one proxy-mode combobox in its modal; Save commits / Cancel discards.
- Existing coverage remains for parser, SOCKS5 HTTPS, subscription cache and restart/resumption, offline-aware auto scheduling, download concurrency, automatic BPF export and GUI loading.

Limits: No live 12,000-node scan on an Iranian link, no Windows 11/Python 3.15 execution, no Karing interoperability test, no Android BPF import test, and no Windows `Setup.exe` build executed in this environment. Measurements are not guaranteed cross-destination VPN performance.
