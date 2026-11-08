# Iran Proxy Monitor v1.0.11 — verification report

**85 automated tests passed** (`python -m unittest discover -s tests -q` on Linux/Python 3.13), including all previous tests and nine new v1.0.11 regressions:

- Switching to an unavailable URL/file never substitutes the previous source's nodes, even if the shared legacy snapshot exists.
- A source with its own prior successful download may use *its own* cache for a full cycle, but an explicit **Update subscription** must report a failed fresh fetch.
- Switching A → B → A retains source identity for separate successful source caches.
- An interrupted partial from source A is discarded when source B is selected.
- An ETag change during a resumed `206 Partial Content` response resets to byte zero and fetches the new body cleanly, including across app invocations.
- Cache metadata and safe logged source IDs do not contain full subscription URLs or node credentials.
- GUI messages distinguish old saved rows, fresh successful updates, and same-source stale cache.

**Real Tkinter GUI smoke test (Linux/Xvfb, not Windows):** Parsed and displayed 1,250 local nodes, changed the selected source to a three-node file and observed three new rows and a different source ID, then switched to a missing file and confirmed that the GUI displayed **Selected source NOT loaded** without erasing or mislabeling the previous rows. The original core/throughput tests also pass; the testing engine and three shortlist rankings are unchanged in this release.

**ZIP verification:** source code, Windows scripts and regression suite included; Python compileall and archive integrity checked.

**Unverified:** Windows 11/PowerShell execution, real remote GitHub performance or successful download on the user's restricted network, actual sing-box/Karing traffic parity. This is a subscription identity and error-reporting fix; it is not evidence that the 300-second network stalls have been solved.

---

# Iran Proxy Monitor v1.0.10 — verification report

**Result: 76 automated tests passed** (`python -m unittest discover -s tests -q`) using the source package on Linux/Python 3.13. Existing parser, downloader, cache/cancellation, engine, history, three-category exporter, and GUI regression tests remain in the suite.

**Ten new v1.0.10 tests** verify:

- Default 250 speed candidates, 4 parallel core batches, 128 outbounds/workers, and 256 MiB budget.
- Migration of exact v1.0.9 defaults without overwriting custom latency worker settings.
- Two independent HTTPS hosts in selected-node comparison, separate measurements through one isolated local sing-box listener, and a strict 8 MiB combined body cap.
- Clear error if both endpoint templates use the same host.
- Core-rejection cache persistence without storing raw passwords or server addresses, and no caching of transient timeouts. Cache expiration and core-version invalidation are tested.
- Rejection of three isolated burst-activity buckets in a nine-second confirmation and qualification of a more distributed sample.

**GUI smoke tests (Linux + Xvfb, not Windows):** Launched the real Tkinter window, showed delayed tooltips, applied the aggressive preset, displayed and copied rows from a 2,500-node list and a 12,050-node synthetic list, and exercised the selected-node comparison callback with mocked HTTPS results. The comparison popup contained both results and no credential text.

**Unverified / limits:** No direct access to the user's Iranian connection, Karing/NekoBox instance, or Windows 11/Python 3.15 runtime; therefore no measured 23-minute-to-new-version latency speedup, real Karing speed parity, or confirmation of the full raw-GitHub feed downloader on their network. A speed confirmation remains specific to the HTTPS test destination. Four concurrent 128-node batches may cause congestion and lower node discovery; benchmark locally. The sample's 55%-activity rule uses application read timestamps, not packet-level inspection.

---

## Previous release test record (v1.0.9)

## Automated tests

**66 automated tests passed** on Linux/Python in this development environment:

```bash
python -m unittest discover -s tests -q
```

This retains the prior parser, history, engine, live GUI, test-budget, and export tests. Six new v1.0.9 tests additionally cover:

1. **Live cancellation of a stalled HTTP response.** A real local HTTP server sends 1,024 bytes, pauses, and the monitoring client's Stop interrupts the blocked read within 3 seconds, despite a configured 120-second network timeout.
2. **Cross-process cancellation ownership.** A cycle's token and process ID are recorded separately from the OS lock; requests target that cycle token and cannot cancel a subsequent run. A 250 ms poll cache limits filesystem overhead.
3. **Older-process lock behavior.** An OS lock held without v1.0.9 metadata is reported as busy, not misclassified as a subscription, parser, or proxy failure.
4. **Installer source preservation.** A pre-existing local `.txt` selection survives the personal installer; new installs can still select the OpenRay URL.
5. **Parse-only metrics preservation.** Updating/parsing a source does not overwrite the last saved full monitoring-cycle statistics.
6. **Private cross-run HTTP Range resumption.** After an interrupted transfer with a strong ETag and known content length, a later invocation requests exactly the missing bytes and verifies the total response. The partial cache metadata does not contain the source URL.

The existing 60 tests also cover mid-response Range recovery in a separate real localhost HTTP server, source formats, 12,000+ synthetic nodes, source caching, security redaction, throughput budget limits, and the three shortlist exports.

## GUI smoke test

Actual Tkinter UI under Linux/Xvfb:

- Selecting a temporary local-file path through Browse saves the path without changing source bytes.
- Loaded **2,000 synthetic rows** into the live table without Python errors.
- Selected a node and copied its original share URI to the clipboard.
- Confirmed redundant **Why unsupported?** top button is removed, but **Explain selected result** remains in the row context menu.

## Windows installation

- The bundled Python code compiles successfully.
- `install-local.ps1` uses the user's known `D:\sing-box.exe` via the existing verified installer path; it does not download sing-box.
- The standard `install.ps1` still includes the verified GitHub release download path for public users.
- **PowerShell and Windows/Python 3.15.2 were not available in this environment.** Windows installer execution and Windows cancellation behavior require the user's test.

## Important limitations

- The blocked-read cancellation was validated with a **real local HTTP server**, not the user's exact GitHub source or the network in Iran. TLS socket cancellation still requires testing on Windows.
- The **300-second feed timeout measures inactivity**, not whole-download time. A server that only transmits tens of kilobytes between long stalls may remain extremely slow. The app now preserves verified HTTP partial progress across restarts when possible, but the complete IDM local file remains a recommended option.
- A v1.0.8 process does **not** recognize the new cross-process Stop request. Close or end that older process first. Do not delete `cycle.lock` while a monitor is running; the OS lock is tied to the actual process.
- Tests here do **not** establish actual Iranian proxy throughput or Karing v1.2.25.2802 import success.
- Files under the private AppData cache can contain working proxy credentials; they should not be published publicly.

## Repro commands

```bash
python -m compileall -q iran_proxy_monitor
python -m unittest discover -s tests -q
```
