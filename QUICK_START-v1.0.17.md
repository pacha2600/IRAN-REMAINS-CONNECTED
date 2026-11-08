# IRAN REMAINS CONNECTED v1.0.17 — Windows 11

## Development installation

Extract the ZIP; run from the `IRAN-REMAINS-CONNECTED` directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -LocalSingboxPath 'D:\sing-box.exe'
.\launch.cmd
```

The normal Windows `IranRemainsConnected-Setup-v1.0.17-win64.exe` can be built from GitHub Actions (provided); it is **not** in this source ZIP.

## New GUI behavior

- **All nodes:** combined, deduplicated imported pool. Column headings sort this table.
- **Working nodes:** every node that passed a real HTTPS latency check; sorting works independently from the All nodes tab.
- **Recent connections:** last 10 successfully connected profiles. Select one and press **Reconnect highlighted recent node**. The mode at the top of the window is used. Remove the sensitive local history with **Clear recent history**.
- **Connect highlighted node:** chooses the currently highlighted table row (either main pool or working pool).
- **Connect shortlist rank:** chooses a saved category and rank from the explicit shortlist dropdown, without requiring a highlighted node.
- **Manual HTTP/SOCKS5:** only applications configured to use the loopback listener are proxied; other apps and websites can remain direct. HTTPS browsing remains TLS-encrypted to the website, independent of this traffic-splitting arrangement. The proxy protocol itself may or may not add upstream encryption.
- **All working nodes:** after a completed scan with HTTPS-passers, `exports/all-working-nodes-latest.{json,bpf,txt}` appears. JSON/BPF contain *all* working outbounds; TXT contains original share URIs when available and one-line outbound JSON for nodes that cannot faithfully be represented as a URI. Thus TXT is a complete text archive, but not necessarily importable as a single share-link subscription. A companion `all-working-nodes-share-links.txt` includes only original share URIs for import into URI-only clients.
- **Scan HTTP MiB ≥:** lower-bound measured response body bytes from feeds, download tests and direct baseline; the footer also shows the accumulated lower bound for the current local calendar day. **It is NOT an exact ISP usage meter**. TLS handshakes, proxy framing, response headers, failures, and canceled transfers can consume additional data. Totals are saved in `%LOCALAPPDATA%\IranProxyMonitor\scan-usage.json`.
- **Alternative subscription formats:** for HTTPS sources whose response has zero usable nodes, the app tries v2rayNG, ClashMeta, and sing-box User-Agent requests. It understands Base64/URI lists, Clash YAML, sing-box/Xray JSON and several JSON wrappers. Some private panels may still return unsupported formats, an HTML login page, or only expired configurations. Logs store no source URL/token; download a sample of the *non-secret* response if you need to diagnose a remaining format.

## The slow final batches

The supplied 2026-11-08 log shows 13,106 candidates and 293 core-config rejections; individual batches lasted up to 94 seconds during late-stage recursive validation. In this release, rejected 128-node configurations split directly into 32-node groups before refining further, without discarding candidate nodes. This targets the observed overhead; it has not been benchmarked on the user's Windows network.

## Privacy and security

`%LOCALAPPDATA%\IranProxyMonitor\client-recent.json` stores the actual outbound settings, **including any proxy authentication secret**, so the recent profiles can reconnect. It is a private local file (and 0600 on Unix). Anyone with access to your Windows user account can read it. Use **Clear recent history** if shared or untrusted PCs are involved. The logs never contain the outbound passwords.

Encrypted proxy protocols can protect the hop between device and proxy; HTTPS continues to protect content between the browser and site. A plain upstream HTTP/SOCKS proxy alone does not encrypt the first hop, and neither TUN nor manual mode provides anonymity against the proxy provider.
