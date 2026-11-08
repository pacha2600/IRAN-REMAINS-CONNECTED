# Security & privacy review — IRAN REMAINS CONNECTED v1.0.16

This is a practical threat-model summary, **not** a third-party security audit. No release is guaranteed private or leak-free solely because it runs sing-box.

## Security properties of the application as currently written

- The client launches one **separate** sing-box process with one selected outbound and no silent direct-fallback outbound. Scanner subprocesses remain separate. CONNECTED means a *local listener* started; use **Test connection** to check an actual proxied HTTPS request.
- The Manual mixed HTTP/SOCKS5 listener binds **only to 127.0.0.1**; apps must opt in. Other local programs may use the listener because it has no local authentication. Keep the computer free of malicious programs.
- Windows system-proxy mode enables and restores user WinINet settings. Applications that ignore WinINet, UDP clients and some system services can **bypass** this proxy. This is **not** device-wide privacy.
- Elevated TUN configures `auto_route`, `strict_route`, and DNS interception; remote DNS is configured to use DoH through the selected proxy, with a local DNS bootstrap to resolve the proxy *server*. On Windows, `strict_route` is documented as blocking some multihomed DNS leaks. **There is no full-traffic kill switch**, and Windows-specific IPv6, DNS, application bypass, sleep/resume, crash behavior and routing need real validation.
- The optional metrics endpoint is a sing-box Clash-compatible API on a randomly selected local port, bound to **127.0.0.1**, with a **new random bearer secret for every session**. It uses a direct loopback HTTP call so Windows system proxy configuration cannot intercept its own metrics request. Only cumulative byte counters are read; no browsing history is uploaded to an external service by this feature.
- The GUI asks for confirmation if a chosen node explicitly disables TLS certificate validation (`tls.insecure`) or configures a plaintext upstream HTTP/SOCKS proxy without TLS. Users can still choose those risky nodes. A proxy provider may see metadata and unencrypted application traffic.
- Feed URLs, cached subscription bodies, saved working-node snapshots, shortlisted outbounds, and temporary sing-box profiles can contain passwords, UUIDs, URLs with tokens, or other proxy secrets. They are stored **locally** under the existing user-specific AppData directory; file permissions are best-effort. Do not upload these data, logs, settings, or exports publicly. Original feed text is not rewritten.
- Failures that find no usable measured nodes do not replace a previously valid shortlist. A failed cycle does not erase the last successful working-nodes snapshot. The system-proxy restoration mechanism avoids overwriting changes made by a different proxy app; nonetheless, recovery should be tested after crashes.

## Why this is not yet equivalent to Karing

Karing is a mature Flutter client using a sing-box-family core and offers routing features and multiple platform-specific integrations. Our program and Karing may use similar cryptographic protocol implementations, but their **DNS policies, routing tables, platform integrations, process/service lifecycles, failover, kill-switch behavior, and defaults are not identical**. The testing/ranking features do not automatically confer the same traffic privacy. The node or subscription operator may also be untrustworthy irrespective of client quality. We cannot promise the same security as Karing without an audit and real Windows tests.

## Windows acceptance and leak tests before public promotion

1. **Manual:** connect; point only a test browser at `127.0.0.1:<port>`; test HTTPS and verify a second browser (not configured) remains unaffected. Disconnect and verify listener closes.
2. **System proxy:** snapshot existing Windows user proxy state first; connect and verify browser traffic goes through selected node. Check an app that ignores system proxy does **not** silently get advertised as protected. Disconnect and verify previous settings are restored exactly.
3. **TUN:** disconnect Karing and all competing VPNs; run as administrator; test IPv4/IPv6 IP location, DNS resolver, UDP traffic, app connectivity, and traffic after Wi-Fi disconnect/reconnect and sleep/resume. Confirm no unexpected direct routing or DNS leakage; test both on success and during a dead node. Verify OS routes restore after disconnect and abrupt core termination. If any leakage occurs, do not represent TUN mode as privacy-safe.
4. **Metrics:** compare API `downloadTotal`/`uploadTotal` with observed browser uploads/downloads and check that totals increase during traffic, reset on a new connection, and are not visible over LAN or without its bearer token.
5. **Executable and updates:** verify SHA256-pinned sing-box archive, source of bundled dependencies, GPL obligations and third-party notices; sign builds or otherwise publish a verifiable release checksum. Ensure no subscriptions, UUIDs or user settings are committed to the public repository.
6. **Input hygiene:** inspect any `tls.insecure` node, unencrypted HTTP/SOCKS upstream, suspicious URL, provider-operated DNS, or untrusted subscription; do not treat a latency-passed node as a secure VPN service.

**Conclusion:** Same engine family is a good starting point, not a privacy certification. Use Karing for critical privacy until this new client's TUN/routing and leak behavior has been independently confirmed on the target devices.
