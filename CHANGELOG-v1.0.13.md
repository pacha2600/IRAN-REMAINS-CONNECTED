# v1.0.13 (2026-11-07)

- Fixed manual SOCKS5 HTTPS AttributeError in Python 3.13+/3.15; preserved TLS verification and remote DNS.
- Added a one-byte Test feed route action with mode-specific status and sanitized logging.
- Made proxy mode and settings adjacent and explicit; clarified that system mode ignores manual host/port.
- Automatic BPF export for every validated category retained; removed unnecessary BPF button.
- Added Default scan and Fast scan presets side by side above advanced settings.
- Split auto timer into schedule-only Start auto monitoring and Run once + auto.
- Wall-clock scheduling includes hibernation; no missed-run backlog; next interval begins after completion.
- Conservative automatic-cycle route preflight: pause five minutes if the OS reports no IPv4/IPv6 route.
- Safe skip on zero connectivity or usable downloads; old stats/export files are preserved. Five-minute retry.
- Added offline unit/integration regression tests, including local TLS over SOCKS5 and schedule time travel.
- Windows EXE release recipe version bumped to 1.0.13; native packaging remains Windows CI-only.
