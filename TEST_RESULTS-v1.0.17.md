# IRAN REMAINS CONNECTED v1.0.17 — Verification report

Date: 2026-11-08

- **161 automated tests** passed using Python 3.13 and `xvfb-run` on Linux.
- GUI smoke test loaded **13,500 simulated nodes**, including 450 rows in the Working nodes tab, in approximately 0.64 seconds of table population.
- Regression tests cover HTML refusals and User-Agent fallback on unparseable subscriptions; prior `UnboundLocalError` after invalid feed fixed.
- Recent connection history saves, deduplicates, limits to ten entries, and clears correctly.
- All-working-node JSON/BPF/TXT exports verified to contain matching outbound selections for a mixed-origin fixture.
- Daily HTTP payload lower-bound accumulation tested.
- Adaptive rejected-config splitting verified to skip 64-node intermediate checks after a rejected 128-node group without losing any nodes.
- Working nodes table sorting state remains independent from the primary pool table.
- Black-circle/white-wordmark PNG and multi-size ICO generated and included in release build scripts.

**Not yet verified:** Windows 11 GUI on actual machine, real sing-box traffic and selected proxy routing, import of BPF into Android, live subscription body from the supplied private subscription URL (the accessible log only shows an HTTP body of 23,961 bytes and zero supported nodes), Windows Setup.exe compilation, and on-network speed gain after the batch-optimization change.

**Traffic reporting scope:** HTTP response payload bytes of successfully completed feed downloads, preliminary/confirmation tests, and direct baseline. TCP/UDP packets, TLS handshakes, proxy framing, response headers, incomplete/failed transfers, and connection retries are excluded. The displayed number is a **lower bound**, not exact ISP bandwidth usage.

## Log-based diagnosis

The 2026-11-08 v1.0.16 log records a 13,106-node full scan with only 67 passing HTTPS, 293 sing-box configuration rejections, and several late 128-node batches taking 65, 94, and other tens of seconds. It did not end in a deadlock. The recurring recursive sing-box validation explains the apparent plateau; v1.0.17 targets that by partitioning rejected 128-node groups into four 32-node groups before further bisection. This preserves every node and retains existing network tests; its live performance still needs benchmarking.

The other remote subscription delivered about 23,961 bytes twice, then the parser reported no supported nodes. The old loader subsequently raised an UnboundLocalError from an uninitialized state. The new loader distinguishes HTTP success from parse success, tries alternative client User-Agents, and never marks a zero-supported-node response as loaded. Its actual format remains unconfirmed until its response body can be inspected securely.
