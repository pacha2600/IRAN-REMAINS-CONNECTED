# Windows CI fix 2 — subscription cancellation

The second Windows Actions run passed 194 tests and failed only
`test_cancel_interrupts_real_blocking_http_body`.

The old cancellation strategy closed a socket from a watcher thread. On
Windows a blocked recv() may not wake when another thread shuts down the
socket. The updated feed downloader checks socket readability every 250 ms
*after the first received body chunk*, so it can respond to Stop without
waiting for a 120-second read timeout. It preserves the original feed stall
limit, byte budget and partial-download checkpointing. A new regression test
disables the watcher to verify cancellation does not depend on socket closing.

Changes: iran_proxy_monitor/monitor.py and tests/test_v109.py only.

To apply: extract this ZIP and copy its two folders into the existing GitHub
repository folder, replacing the corresponding two files. Commit and push
with summary `Fix Windows subscription cancellation in CI`, then manually
rerun the Windows Setup EXE Actions workflow on main. Do not tag v1.1 yet.

Validation here: 196 tests passed under Linux/Xvfb. A Windows Actions rerun
is still required to verify Windows behavior and build the Setup EXE.

Limit: establishing a new HTTP connection can still block for its configured
connect timeout; the new polling behavior applies after the first response
body chunk. This fix does not change the scanner/proxy connection algorithms.
