# v1.0.12 tests and verification

| Test | Result |
|---|---|
| Full Python unittest discovery | **100 passed** |
| Original application tests from v1.0.11 | Passed |
| New multi-node local BPF create/decode | Passed |
| Matching JSON/BPF outbound lists and three export categories | Passed |
| Preserve previous exports if Android sing-box validation fails | Passed |
| Rebuild BPF from saved JSON without running a proxy test | Passed |
| SOCKS5 remote DNS integration using a local mock SOCKS5 server | Passed |
| SOCKS5 username/password handshake | Passed |
| Manual feed proxy configuration validation | Passed |
| Sensitive proxy credentials not persisted to settings file | Passed |
| GUI smoke test with feed proxy dialog and save | Passed under Xvfb |
| Independent cross-language Go BPF decoder | Passed |
| Windows Setup EXE build | **Not run** — requires Windows runner |
| Windows Python-free installation of Setup EXE | **Not run** |
| Android SFA import/VpnService behavior | **Not run** |
| Live censored-network subscription fetch through Karing | **Not run** |

Run suite from the source root: `python -m unittest discover -s tests -v`.

All fake nodes in tests have non-working example.org addresses. They do not indicate real proxy performance or import availability. No private subscription URLs or proxy credentials were included in test artifacts.
