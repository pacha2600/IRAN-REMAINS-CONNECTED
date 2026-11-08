# IRAN REMAINS CONNECTED — v1.1

**First public release candidate**: a Windows proxy/subscription scanner with Manual, System Proxy and TUN connection modes. v1.1 restores an adaptive, non-scrolling results dashboard at normal window sizes, adds wheel scrolling when the window is too short, collapsible advanced settings, and exclusive scan/update/auto-monitor controls. Existing scanning algorithms, security grading, last-10 connection history, matched JSON/TXT/BPF exports, and fixed live-traffic footer are preserved.

- **[First public release guide](RELEASE_V1.1.md)** — exact steps to build the all-in-one Windows Setup.exe and publish it on GitHub.
- [v1.1 changelog](CHANGELOG-v1.1.md)
- [v1.1 test report](TEST_RESULTS-v1.1.md)
- [Security scoring methodology](SECURITY_SCORE-v1.0.18.md)

**Current artifact is a source ZIP**, not a compiled Windows installer. The Windows build and TUN routing must be validated on a Windows 11 PC.

---

# IRAN REMAINS CONNECTED — v1.0.19

**Windows 11 proxy scanner + local HTTP/SOCKS5, system-proxy and TUN client.** v1.0.19 adds a fixed bottom status bar with version, a live HTTP-layer scan data breakdown, 60-minute per-source feed refresh reuse for ordinary scans, the requested monitor button order and styling, a scrollable dashboard for non-maximized windows, and a corrected Windows titlebar/taskbar icon application path. The scan and ranking algorithms are retained.

- [v1.0.19 quick start](QUICK_START-v1.0.19.md)
- [v1.0.19 changes](CHANGELOG-v1.0.19.md)
- [v1.0.19 tests](TEST_RESULTS-v1.0.19.md)
- [Encryption and scoring methodology](SECURITY_SCORE-v1.0.18.md)

**Accuracy note:** Reported scan usage counts observable HTTP-layer bytes, not full network/interface bytes or exact ISP billing. Window and taskbar native icon behavior still needs testing on Windows 11. The included GitHub Actions workflow can build the one-click Windows installer; this ZIP contains source, not a compiled Setup.exe.

---

# IRAN REMAINS CONNECTED — v1.0.18

**Windows 11 proxy scanner + selectable Windows proxy/TUN client.** New in v1.0.18: upstream encryption and configuration-security scoring in All nodes, Working nodes and Recent connections; an automatic safe-attempt mode handoff on dropdown selection; a full Recent nodes table; section dividers; and the `.ico` taskbar integration. The underlying HTTPS latency/throughput scanning algorithms are unchanged.

- [v1.0.18 quick start](QUICK_START-v1.0.18.md)
- [Encryption and scoring methodology](SECURITY_SCORE-v1.0.18.md)
- [v1.0.18 changelog](CHANGELOG-v1.0.18.md)
- [v1.0.18 tests](TEST_RESULTS-v1.0.18.md)

**Important:** The security score grades *declared configuration*, not the real-world integrity of the proxy service, DNS-leak behavior, operator trust, or anonymity. Manual/System proxy modes are not device-wide tunnels. Mode switches interrupt traffic; a switch failure can leave you disconnected. No kill switch is provided.

---

# IRAN REMAINS CONNECTED — v1.0.16

**Windows sing-box proxy scanner and on-demand client.** Combine up to 40 subscription URLs or local files (one per line or comma-separated), scan one deduplicated node pool, inspect all HTTPS-responsive nodes in the **Working nodes** tab, and connect directly to selected or ranked saved nodes using Manual HTTP/SOCKS5, Windows System Proxy, or elevated TUN.

New: live per-session upload/download rates and cumulative byte counts on the `CONNECTED` line, plus **Best reliable** (historical HTTPS availability, requiring ≥1.000 Mbps *confirmed Flow*). Existing latency and throughput measurement algorithms are unchanged.

- [v1.0.16 quick start](QUICK_START-v1.0.16.md)
- [v1.0.16 security & privacy review](SECURITY_AND_PRIVACY-v1.0.16.md)
- [v1.0.16 technical and test notes](TEST_RESULTS-v1.0.16.md)
- [Existing v1.0.15 client reference](CLIENT_GUIDE-v1.0.15.md)

**Important:** Manual/System Proxy modes do not tunnel all device traffic. TUN requires administrator rights and has no kill switch. This release has not been penetration-tested or validated for traffic leak prevention on a real Windows device. Never assume a connected indicator equals safe routing.

The app intentionally retains `%LOCALAPPDATA%\IranProxyMonitor` and internal `IranProxyMonitor.exe` so existing user settings, history, saved outputs, and previous installer upgrades remain compatible.

---

## Historical documentation

# Iran Proxy Monitor v1.0.15

**NEW: On-demand connection modes.** See [CLIENT_GUIDE-v1.0.15.md](CLIENT_GUIDE-v1.0.15.md) for Windows Manual HTTP/SOCKS5, Windows system proxy, and administrator-only TUN, plus cleanup and security guidance. The v1.0.14 scanner and rankings remain unchanged.

# Iran Proxy Monitor v1.0.11 — source-safe subscription updates and resume recovery

Windows 11 desktop application for measuring **real HTTPS latency and sustained proxy download throughput** through a local sing-box core, then creating independent shortlists for Karing. The application does not alter your original subscription, Karing data, or system proxy settings.

## Install on the current test computer

1. Extract `IranProxyMonitor-Windows11-v1.0.11.zip` to a **new** folder.
2. Make sure your existing `D:\sing-box.exe` is available.
3. Open PowerShell in the extracted `IranProxyMonitor` folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-local.ps1
.\launch.cmd
```

`install-local.ps1` copies **`D:\sing-box.exe`** without downloading sing-box. For a new installation with no saved source, it uses:

```text
https://raw.githubusercontent.com/sakha1370/OpenRay/refs/heads/main/output/all_valid_proxies.txt
```

It also sets the network **feed stall timeout** to **300 seconds**. This is an inactivity timeout for an HTTP read or connection operation, **not a guarantee the entire download will complete within five minutes**. The downloader requests uncompressed bytes, reads incrementally, logs retry attempts and byte counts without recording the URL, and attempts to resume after an interrupted response using HTTP `Range` when supported. A blocked server or a proxy configuration issue can still prevent successful downloading; the application preserves existing exports and may use only a source-matched cache during full monitoring cycles (not when you explicitly request an update).

The installer does **not** modify your `D:\all_valid_proxies.txt`; you can use it again by changing the source field in the GUI. History and settings remain under `%LOCALAPPDATA%\IranProxyMonitor`. **The installer no longer overwrites a saved source selection**, including an IDM-downloaded `.txt` file.

**Public GitHub installer:** `install.ps1` remains in the ZIP. It validates an existing sing-box core in the application folder or a shared local cache and otherwise downloads the pinned, SHA-256-verified official Windows sing-box 1.14.4 release. People using the public installer supply their own subscription URL. Python 3.11+ with Tkinter is required; bundled pure-Python YAML handling means pip does not have to download packages.

## What changed in v1.0.11 — the wrong subscription was being shown

The previous releases wrote every successful subscription to a shared `subscription-last-good.dat` and unconditionally fell back to it when a remote URL failed. This caused a serious diagnostic error: **after a new URL failed to download, the dashboard showed the previous OpenRay node counts and labels as though the new subscription had been parsed.** This is fixed.

- **Source identity is now enforced.** Last-successful feed bodies are stored under `%LOCALAPPDATA%\IranProxyMonitor\subscription-sources\<sha256-of-source>.dat`. Only an exact match of the URL/path may be used for fallback. Neither URLs nor subscription tokens are stored in cache filenames, cache metadata, or logs.
- **Update subscription requires a fresh fetch.** If it fails, the GUI explicitly says **Selected source NOT loaded**, retains the old rows for reference, and does **not** report the old node counts as the results of the new source. It does not replace existing exports or saved monitoring statistics.
- **Full monitoring cycles may use a same-source cached file.** A stalled server can still be tested against its prior good body, but the GUI explicitly identifies this as **STALE CACHE (same source; update failed)**. A different source's data will never be substituted.
- **Resume validation failures are recoverable.** If the ETag/Last-Modified changes, a `206` response has a wrong byte offset/size, or the server rejects an obsolete Range, the downloader discards the partial body and retries from byte zero. It never joins incompatible revisions.
- **Changing sources discards unrelated partial bytes.** A private partial file is only resumed when its stored SHA-256 key equals the selected URL's key.
- **Traceable identity:** GUI and download logs display an opaque 10-character source ID (not the actual URL). On a successful update, the table and counters reflect the newly loaded feed. Older saved runs without a source ID are labeled **source unknown**.

### Migration note

The old `subscription-last-good.dat` is intentionally kept on disk for manual recovery, but **v1.0.11 does not automatically trust its origin** because older versions never recorded a trustworthy source identifier. A first successful import of the currently selected URL or local `.txt` is needed to establish its source-specific cache. You can still select your complete IDM-downloaded local TXT for immediate offline parsing.

### What this does NOT fix

Your log showed several interrupted HTTPS transfers that delivered only 31–41 KB between multi-minute stalls, and occasional connection resets. Those are real fetch/network failures; **this change fixes the misleading cache behavior, not the network conditions**. The download timeout remains 300 seconds per socket-read stall. If Python continues to time out on the full URL, importing the complete local file remains the proven workaround. You can also compare the `system` and `direct` feed network settings for the same URL. The official public installer still retains the sing-box download fallback; the personal installer reuses `D:\sing-box.exe`.

## Why v1.0.7 was slow

Your log showed some 96-node groups requiring around 30–45 seconds. Although you selected a 2.5-second latency timeout, Python's HTTPS operations could consume a separate timeout on TCP CONNECT, TLS handshake, and response-header reading. Additionally, one entire sing-box group ran at a time, and an occasional group startup failure marked the group's nodes as failed even when smaller groups might run.

**v1.0.8 latency improvements:**

- The latency probe opens an HTTP CONNECT tunnel through the specific node's sing-box listener, completes TLS with standard certificate/hostname verification, then requests HTTPS response headers. Every stage shares **one** configured wall-clock deadline per endpoint attempt. This is still an actual per-node HTTPS check, **not** a misleading TCP-only ping.
- **v1.0.10:** Four separate core groups now run in parallel by default. Each can check up to 128 nodes concurrently (a potential 512 concurrent HTTPS probes). Previously there were 2 × 96. This is an intentionally aggressive preset; it may overload weaker connections and reduce discovery quality. Compare its success counts with 2 × 96 when troubleshooting.
- A sing-box batch that stops at runtime is split into smaller groups and retried rather than automatically losing every node. Configurations that sing-box itself rejects are excluded with an explicit safe error category.
- Each batch logs its elapsed time, and per-node results continue appearing live.

Because the new full-deadline interpretation is stricter than the old *per-stage* timeout, it may produce fewer successes among nodes whose HTTPS setup takes more than 2.5 seconds. If so, try **Latency timeout s = 4** (or 5) before increasing worker counts. The number of valid nodes found is as important as scan speed. The single default HTTPS endpoint per node may also be blocked; choose 2 or 3 endpoints for a coverage-focused run.

## What “Unsupported” means

`Unsupported (parser)` means the source entry could not be safely represented as an outbound by our parser. Examples include unknown URI options, unsupported transports or plugins, and missing required values. **It does not prove the node is dead.** A different client such as Karing may support the original entry. The original text is preserved and may still be copied.

`Core rejected configuration` is separate: the parser accepted the entry, but the installed sing-box version rejected the translated configuration. Right-click a selected row and choose **Explain selected result** to see its reason; the redundant top-level button was removed. This release categorizes core rejection without displaying or logging full core errors that could contain credentials. The detailed parser report is saved at `%LOCALAPPDATA%\IranProxyMonitor\unsupported-nodes.csv`.

`Core startup error` indicates a process/listener failure and **does not prove a configuration is unsupported**. `Latency failed` means the configured HTTPS attempt failed in this cycle. No failed node is permanently blacklisted.

In your v1.0.7 screenshot, 156 of the 890 unique loaded nodes were parser-unsupported; another 12 supported VLESS entries were rejected by the core during the actual scan. Those are different categories.

## Download tests and reliability

The endpoints and speed settings are unchanged unless you edit them:

- Latency endpoints: `https://www.gstatic.com/generate_204`, `https://www.cloudflare.com/cdn-cgi/trace`, `https://www.google.com/generate_204`; one attempted by default per node, rotated by node ID.
- Download endpoints: `https://speed.cloudflare.com/__down?bytes={bytes}` and `https://speed.hetzner.de/100MB.bin`.
- Preliminary transfer: up to **192 KiB** per node, **3.5-second** request target, up to **5 concurrent** download workers. This only discovers candidates; it does not qualify high speed.
- Confirmation transfer: adaptive **8–32 MiB** cap per selected candidate, **9-second** request target, at least **4 seconds** of observation. Data must arrive over multiple seconds; this release also requires activity in **three distinct one-second buckets** (at least 1 KiB in each bucket) to avoid a single delayed burst masquerading as sustained throughput. The full request elapsed time, including delays, is used to calculate Mbps. HTML error pages are not counted as download payloads.
- Planned response-body budget: **128 MiB** per cycle. This does not include TLS headers, retransmissions, probe traffic or direct baseline tests.

**Interpretation:** A result of 0.596 Mbps marked verified is a measured effective HTTPS transfer rate through that proxy over its sample, not a prediction of VPN TUN throughput in Telegram, browsers, and other applications. Congestion, throttling, different server destinations, traffic bursts, and protocol details may produce different application speeds. For a stricter evaluation, increase confirmation duration and bandwidth budget, or compare multiple test destinations. Do not treat a preliminary-only speed as sustained.

## Shortlists and copying

Three independent output categories are written to `%LOCALAPPDATA%\IranProxyMonitor\exports` after sing-box JSON validation:

| Category | Files | Selection |
|---|---|---|
| Best download speed | `best-download-speed-latest.json`, `best-download-speed-share-links.txt` | Highest **verified sustained Mbps**, regardless of latency |
| Best ping | `best-ping-latest.json`, `best-ping-share-links.txt` | Lowest HTTPS latency among nodes with at least one **successful actual download**, useful for messaging |
| Best overall | `best-overall-latest.json`, `best-overall-share-links.txt` | Normalized sustained speed + HTTPS latency + historical reliability |

Shortlists may contain fewer than 10 nodes and will never be filled with fake or unverified throughput measurements. Previous exports are retained if an update has no qualifying candidates. All loaded entries appear in the table in real time. Select any row and press **Ctrl+C**, or click **Copy selected** / **Save selected**, to preserve the exact original share URI. For non-URI input, a sing-box outbound JSON snippet is copied instead. Treat these as credentials and do not post them publicly.

## Defaults and controls

| Setting | Default |
|---|---:|
| Subscription stall timeout | **300 s** per network blocking operation |
| Parallel sing-box batches | **4** (aggressive) |
| Latency batch size | **128** |
| Latency HTTPS workers per batch | **128** |
| Whole-HTTPS-attempt timeout | **2.5 s** |
| Latency endpoints per node | **1** |
| Probe all supported nodes | On |
| Responsive target for speed candidate selection | 1000 ms, **not a hard exclusion** |
| Max speed candidates / download workers | **250 / 5** |
| Slow-ping exploration quota | 30% |
| Confirmation duration / minimum verified window | 9 s / 4 s |
| Download body budget / update interval | **256 MiB** / 120 min |

Click **Fast scan** after upgrading if an older installation retains different values. Custom settings otherwise persist. Start automatic monitoring while the GUI is open, or use the optional Windows Task Scheduler scripts for unattended scheduled runs. The application checks that only one monitoring cycle operates at a time.

## Logs and troubleshooting

When downloading a feed, the status footer shows bytes downloaded and the attempt number. Diagnostic logs also identify source retry offsets and elapsed time for core batches:

```powershell
Get-Content "$env:LOCALAPPDATA\IranProxyMonitor\logs\monitor.log" -Tail 80
```

Files:

- `%LOCALAPPDATA%\IranProxyMonitor\settings.json` — source URL and preferences, private.
- `%LOCALAPPDATA%\IranProxyMonitor\subscription-last-good.dat` — original subscription payload cache, private.
- `%LOCALAPPDATA%\IranProxyMonitor\history.sqlite3` — node history, private.
- `%LOCALAPPDATA%\IranProxyMonitor\unsupported-nodes.csv` — parser problem categories.
- `%LOCALAPPDATA%\IranProxyMonitor\logs\monitor.log` — redacted diagnostics.

This application was verified with 76 automated tests, including a real local stalled-HTTP cancellation test, and a Linux/Xvfb GUI smoke test. **It has not been run against your Iranian network or validated through Karing 1.2.25.2802 on Windows.** The official downloader remains available to eventual GitHub users; your specific installer still uses `D:\sing-box.exe` and avoids downloading it.

Run the tests yourself after installation:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```


## v1.0.10 — what changes for the full 11,763-node subscription

Your v1.0.9 full-list scan found 9,860 parser-supported nodes, 375 successful
HTTPS connectivity checks, and 70/100 successful preliminary downloads. The
latency scan took approximately 23 minutes; the download stages took roughly
2 minutes. The new release targets *latency startup and testing overhead*:

- The **Top speed nodes** cap is now **250** (including migration from the old default of 100).
- The aggressive preset is **4 parallel sing-box processes × 128 HTTPS workers**, with **128 outbounds per batch**. This can use ~512 simultaneous sockets. Real speedup is unknown until tested on your Iranian connection; raising concurrency can also decrease the pass rate.
- **Definite single-node sing-box configuration rejections** are cached by core version and hashed outbound ID in `%LOCALAPPDATA%\IranProxyMonitor\core-compatibility.json`. This avoids repeating expensive group bisection in later cycles. The cache expires after **six hours**, and a new core version invalidates it immediately; even rejected nodes are eventually rechecked. **Network failures and startup timeouts are never cached.**
- The default download body budget grows from **128 MiB to 256 MiB** so 250 preliminary downloads leave room for multi-second confirmations. The limit accounts for HTTP response bodies, not every network overhead byte. The original `install-local.ps1` still copies `D:\sing-box.exe` without downloading; the public `install.ps1` keeps the official download fallback.
- Previous 96/96/2 and 100-candidate default settings migrate; explicitly custom latency worker/batch settings remain unchanged. Click **Fast scan** to request the new aggressive values directly.
- Every dashboard field, label, metric, button, and table heading has a short **hover explanation** after approximately 600 ms. Test-endpoint editor inputs are covered too.
- Select exactly one supported row and click **Compare selected** to test that same node against **two distinct HTTPS download hosts** separately. The comparison can use up to **8 MiB** and does **not** change the global rankings, history or Karing exports. The popup identifies which destination succeeded, its measured Mbps and elapsed time, and whether its sample was sustained enough.
- A nine-second confirmation now needs receive activity in at least **55% of observed one-second buckets**, as well as the existing multi-second span requirement. This rejects more intermittent burst patterns. A status of **Confirmed (test host)** still means only that destination-specific HTTP sample passed the checks.

### Why a 6.224 Mbps result can be terrible in Karing

This application routes a *specific HTTPS download* through sing-box's local
HTTP CONNECT listener. It does not measure how fast all of Telegram, browsers,
streaming services, and Karing's DNS/routing will be. For example:

1. A Cloudflare download may be fast while other domains are filtered, delayed,
   reset, or severely throttled. A different server may reveal the difference.
2. The single nine-second sample can be temporarily favorable despite multiple
   receive-activity safeguards. Do not treat it as a general speed guarantee.
3. Karing/NekoBox may have different DNS, domain rules, global-vs-rule routing,
   system proxy or TUN interception, and core configurations. A valid sing-box
   JSON file or a low displayed ping does **not** prove your browser traffic
   is actually using the selected outbound.
4. The Karing screenshot showed **Rule** mode and nearly zero active traffic.
   For a controlled comparison, select the intended node explicitly, temporarily
   choose **Global**, and ensure your test application actually routes through
   Karing's **System Proxy** (if supported) or **TUN**. Verify that Karing's
   connection count and download counters increase when you load the test page.
   When finished, restore your preferred routing settings.

Official Karing references: https://karing.app/en/app-manual/home and
https://karing.app/en/faq . Karing says System Proxy only captures applications
that honor it; TUN captures a wider range of traffic. **This release does not
claim to measure Karing/NekoBox runtime performance or to solve their routing
configuration automatically.**

### Remote subscription downloads remain an open issue

The 300-second inactivity timeout, validated HTTP Range resumption, and
cancelable reader from v1.0.9 remain. This release **does not** add a new
network fetch backend. The browser/Python feed stalls on your connection are
not yet explained or fixed. The complete IDM-downloaded `.txt` is the safest
known input for testing until we compare downloader behavior. Choosing a local
file and clicking **Update subscription** does not contact the raw GitHub URL.

## v1.0.9: fixing the stuck feed and cycle lock

Your v1.0.8 log showed the original Python process still downloading the feed after two 300-second read timeouts. Newly opened app windows could not start because the first process correctly held the cross-process cycle lock. Replacing backslashes with forward slashes in a valid Windows file path does not affect this lock.

**Before installing:** close all older Iran Proxy Monitor windows; if an older process remains stuck, use Windows Task Manager to end *only that monitor's* Python process, not unrelated Python jobs. You can inspect processes using the provided `show-monitor-processes.ps1`. The OS releases its file lock when that process exits; **do not just delete `cycle.lock`**.

- **Stop now interrupts a blocked HTTP body read** using a dedicated socket watcher, with a maximum 30-second initial header connection attempt. A normal slow response may still take 300 seconds between chunks.
- **Cross-process cancellation:** v1.0.9+ writes the owning process ID and a random cycle token to `cycle.owner.json`. Pressing Stop in a different *v1.0.9+* window requests cancellation. Earlier releases do not understand this signal; close those windows instead.
- A busy cycle reports **Another operation running**, rather than `Cycle failed`. The old dashboard statistics/exports are not overwritten by a busy or cancelled cycle.
- **Downloaded `.txt` files are the recommended source on very restricted connections.** Browse .txt → choose the complete IDM file → the choice saves immediately → Update subscription; no HTTPS download occurs for that step. Source selection is preserved by `install-local.ps1` when upgrading.
- HTTP URL feeds keep a **private partial download on disk**, keyed by a SHA-256 hash of the source URL. Resumption across app restarts is attempted **only when the server supplies a strong ETag or Last-Modified validator and a known total length**. If the server ignores Range or the file changed, the app restarts the body instead of combining incompatible responses. The partial content may contain proxy credentials; keep the local AppData directory private.
- The **300-second feed timeout is not an overall deadline**, nor a guarantee the server completes. A server that repeatedly sends 32 KB every five minutes could still take hours. An independently downloaded local file remains a good and fully supported fallback.
- **Update subscription** does not replace your persisted speed results; it only parses and displays the new source. Full test cycles continue to update the saved statistics and validated exports.

PowerShell commands (from the extracted `IranProxyMonitor` folder):

```powershell
powershell -ExecutionPolicy Bypass -File .\install-local.ps1
.\launch.cmd
```

Use **Stop** before switching from a remote URL to a locally downloaded file while a cycle is running. For a v1.0.8 process, close the old window first; v1.0.9 cannot remotely cancel code that does not yet support cancellation.

---

## v1.0.12: feed proxy selection and Android BPF profiles

**Subscription-only proxy modes.** In **Feed network** choose `system` (use Windows/environment proxy), `direct` (do not honor the Windows proxy setting), `manual-http` (HTTP CONNECT proxy), or `manual-socks5` (SOCKS5 with remote DNS). Choose **Feed proxy settings** to enter the proxy hostname/IP and port; `127.0.0.1:3067` is an *example*, not a universal Karing port. Use the actual local proxy listener port shown by Karing or NekoBox. Optional username/password authentication is supported. Credentials are kept in memory for the current process only; usernames and passwords are not written to `settings.json` or diagnostic logs. Restarting the app requires re-entering proxy credentials. HTTPS uses normal certificate verification through the tunnel. The chosen feed proxy affects **subscription downloads only**, not per-node HTTPS tests.

**Recommended censored-feed workflow:** Start Karing, enable a working local HTTP or SOCKS5 listener, choose the matching manual mode, fill in the port, then click **Update subscription**. Once the download finishes, enable **Test saved feed (no download)**. You may then disconnect Karing before **Run one cycle**, avoiding an unwanted double-tunnel during benchmarking. This checkbox is per selected source and uses only that source's verified cache; it does not silently reuse a different URL's subscription. **Update subscription always requests the remote source**, regardless of this checkbox. If an OS-wide TUN VPN remains active, the operating system may route outbound test traffic through it; the app cannot automatically bypass that interception.

**Android profiles:** Every successful shortlist now exports a `best-download-speed-latest.bpf`, `best-ping-latest.bpf`, and `best-overall-latest.bpf` in `%LOCALAPPDATA%\IranProxyMonitor\exports`. Each BPF is a binary **local sing-box profile** (libbox ProfileContent v1) with a whole sing-box configuration, selector, **the exact same selected outbounds as its JSON counterpart**, and an Android TUN inbound. A BPF can contain many nodes; it is not a single share URL. The parallel `...-share-links.txt` file remains available for clients supporting URI lists.

**No manual export required:** `.bpf` is generated automatically during each successful category export. The standalone "Make Android BPF" button was removed in v1.0.13. Existing JSON shortlists can still be converted via the Python helper `rebuild_android_bpf_from_saved_json()` if needed; new complete cycles do it automatically. Failed Android validation keeps the last good BPF and JSON for that category.

On Android use the official sing-box for Android app's **local profile import** rather than assuming tapping a `.bpf` file in a file manager launches the app; some app/Android releases have file-association bugs. After importing, select one of the profile's nodes and verify the Android VPN connects and routes data correctly. Import and VPN functionality cannot be verified on Android from this development environment. Share profile files privately; they contain proxy passwords/UUIDs.

### One-click Windows release installer

A Windows **release build recipe** is included at `release/build-windows.ps1`, `release/IranProxyMonitor.iss`, and `.github/workflows/windows-release.yml`. Upload this source tree to a GitHub repo, open **Actions → Windows Setup EXE → Run workflow**, and download the resulting `IranProxyMonitor-Setup-Windows` artifact containing a single `.exe` installer. Recipients double-click `IranProxyMonitor-Setup-v1.0.13-win64.exe`, accept the installation prompts, and launch via the Start menu. They **do not need Python, pip, sing-box, or PowerShell installed**: the installer bundles PyInstaller's Python runtime and a pinned, SHA-256-verified official sing-box core. The Windows build takes place on a GitHub-hosted Windows runner; the development source ZIP itself is *not* a ready-built Windows installer. Publishing Git tags beginning with `v` can create a GitHub Release automatically.

Before public distribution, review the third-party licenses (sing-box GPLv3 and the bundled PyYAML license), provide the corresponding sing-box source, scan the compiled files and consider code-signing the installer. Release tooling downloads and bundles license notices. See `release/README.md`.


## v1.0.13: explicit SOCKS5 feed repair, safe automatic scheduling, and streamlined controls

The error in the November 7 manual SOCKS5 feed logs was caused by accessing an
internal Python `HTTPSHandler._check_hostname` field that is absent in modern
Python (including 3.13/3.15). The SOCKS5 HTTPS connector now passes the SSL
context directly and does not access that removed attribute. HTTPS certificate
validation remains enabled by default. Local integration tests establish a
real SOCKS5 handshake, remote DNS, HTTPS/TLS and a feed response without Internet.

**Karing setup:** Enable Karing's local SOCKS5 listener. In the dashboard choose
**Feed proxy settings** and select `manual-socks5` inside the dialog, and enter `127.0.0.1` and Karing's **actual SOCKS5**
port (not its HTTP port). Use **Test feed route** to fetch one byte from the
currently selected subscription through that exact route. If it succeeds,
click **Update subscription**. For an HTTP CONNECT listener, choose
`manual-http` and its HTTP port instead. `system` uses the proxy information
that Python can discover from Windows/its environment; it may not be equivalent
to Karing's internal proxy routing. Merely displaying host/port in the dialog
does not activate a manual proxy while mode is `system`. TUN interception routes
process traffic independently but is not needed with a functioning manual route.
The proxy choice affects subscription downloads only. Avoid leaving a VPN/TUN
enabled during proxy benchmarking if you want to measure the original route.

**Automatic monitoring** has two deliberately different controls:

- **Start auto monitoring** arms a timer without running anything immediately.
  First scan is due `Refresh min` after the button press, while the GUI remains
  open. A 120-minute setting means 120 minutes of real elapsed time.
- **Run once + auto** starts a full scan now, then waits `Refresh min` after that
  scan finishes before the next cycle. **Run one cycle** runs only once (unless
  a separate auto timer is already enabled). **Stop** cancels the timer and
  requests cancellation of any active scan.

The schedule uses wall-clock timestamps: sleep/hibernate **counts**. If you
hibernate for 60 minutes immediately after arming a 120-minute timer, one hour
remains on resume. If the deadline passed while asleep, ONE scan starts on
resume, not dozens of catch-up scans. A successful completed cycle schedules
its next scan based on completion time. Failed/skipped scans schedule a retry
no sooner than five minutes later. The scheduler is **not a background Windows
service**: it runs only while this GUI remains open and is intentionally not
automatically restored when restarting the application. Use Windows Task
Scheduler separately for unattended background operation.

**Auto pause when disconnected:** When the automatic timer comes due, a
conservative OS TCP-route check first distinguishes *definite* missing IPv4 and
IPv6 outbound routes. In that case it avoids starting a scan and retries in
five minutes. It deliberately does **not** mistake a blocked or timed-out
public IP for confirmed offline, since censorship can make direct endpoints
unavailable even when working proxies exist. This is not a full Internet
connectivity guarantee.

**No blank overwrite:** A scan with no HTTPS-connected nodes, no download
candidates, or no successful preliminary download raises a non-destructive skip.
The current live table may still show attempted checks, but old saved rankings,
statistics, JSON, TXT, and BPF outputs remain in place. This covers ordinary
complete disconnection as well as blocked test endpoints or core failures; it
cannot always distinguish those causes. In auto mode it keeps the timer armed
and retries after a pause. It does not claim an offline diagnosis solely on
failure of a censored destination.

**Interface cleanup:** The **Default scan** and **Fast scan** preset buttons
appear side by side, above the advanced tuning inputs. Default is a balanced
2-process/64-node batch with 3.0s HTTPS timeout and two candidate latency URLs;
Fast is the aggressive 4-process/128-node 2.5s scan. The active feed mode is now shown on the toolbar; the only selector is inside **Feed proxy settings** (v1.0.14). **Make Android BPF** is gone:
BPF is exported alongside JSON and available share links automatically for
all validated categories.

**Verification:** tests are run on Linux/Python 3.13 here, including a local
TLS/SOCKS5 integration test, 111 total standard-library tests, and static
syntax checks. The user should verify the feed route with their actual Karing
version on Windows 11 / Python 3.15; the Windows Setup.exe is built using the
provided GitHub Actions workflow, not cross-compiled in this source ZIP.

## v1.0.14: conservative flow metric and one feed mode selector

The new **Flow Mbps** table column shows a robust lower-quartile of consecutive
2-second transfer-window rates, based on 1-second HTTPS response-byte arrival
buckets (including zero-traffic seconds). A node with a short large burst and
multi-second silences has a low flow floor even when its average Mbps looks
high. A flow confirmation requires a long enough observation, significant
traffic in at least 75% of its whole-second buckets, reasonable floor/mean
ratio, and no prolonged gap or reported stall. The **Stable Mbps** headline,
Best download speed and Best overall rankings use the conservative floor; the
Avg Mbps is still visible for diagnosis. The quick/preliminary stage remains
intentionally unverified; the Best ping category accepts real preliminary
traffic for text messaging. All metrics are specific to the test destination.

The default long confirmation is now capped at 12 seconds with an 8-second
minimum. The exact old preset durations 9/4 and 10/4 are migrated; custom
durations are kept. **Default scan** and **Fast scan** both apply the new
confirmation durations without initiating a scan.

The dashboard no longer has an editable Feed network combobox. It displays
only the active mode as read-only text. The sole mode selector is under
**Feed proxy settings**, alongside host/port and **Test feed route**. Apply
changes with **Save proxy settings**; Cancel/Escape/window close discard them.
Existing subscription-only proxy functionality is preserved. Historical
exports remain intact if there are no new stable shortlist qualifiers.

See `QUICK_START-v1.0.14.md` for installation and the flow-based ranking caveats.


## v1.0.17 — scan diagnostics and connection history

See [QUICK_START-v1.0.17.md](QUICK_START-v1.0.17.md). This release includes new formats, per-scan HTTP payload lower bound, all-working-node exports, the last ten connections, independent Working tab sorting, and a Windows app icon.
