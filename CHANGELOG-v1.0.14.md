# Iran Proxy Monitor v1.0.14 — flow consistency and simplified feed proxy (2026-11-08)

- **Conservative Flow Mbps:** Record received response bytes in one-second buckets during confirmation. Compute the **lower quartile of 2-second sliding-window Mbps**, including zero-traffic seconds and TLS/TTFB delay. This resists bursts that make the mean Mbps look attractive while practical throughput stalls.
- **Stricter confirmation:** Real streaming data now requires the user-configured minimum duration, meaningful activity during at least 75% of whole seconds, a conservative floor at least 50% of the average rate, no more than one continuous quiet second in the bucket sample, no observed inter-read gap over 2.5 seconds, and no recorded socket stall. Confirmed (test host) is now called **Consistent flow (test host)**. These are heuristics, not guaranteed speed in messaging or video apps.
- **Longer default observation:** The default/fast presets now use a 12-second confirmation cap and an 8-second minimum observation; saved exact v1.0.13 presets (9/4 and 10/4) upgrade automatically, while other custom values remain unchanged.
- **Rank by consistency:** `Best download speed` and `Best overall` use the conservative verified flow Mbps rather than a burst-inflated average. `Best ping` still permits preliminary success because it targets lightweight messaging. If there are no newly verified flow-consistent nodes, old verified exports stay intact.
- **Live table:** Keep average download speed visible as `Avg Mbps` and add `Flow Mbps` beside it. `Stable Mbps` at the top reports the best conservative verified rate. Tooltips explain the distinction.
- **Exactly one editable feed proxy mode:** Removed the duplicate dashboard combobox. The toolbar now displays the active mode as read-only text. The only mode selector is in **Feed proxy settings**; the dialog is transactional. Closing or clicking **Cancel** does not change the active proxy. **Save proxy settings** validates and applies the selected mode/host/port and persists them (never proxy credentials).
- **Stability and GUI cleanup:** Prevented Tk after-callback errors on closing the feed dialog or main app in GUI tests. Existing automated BPF exports, scheduler and old-export protection are retained.
- Windows release recipe version advanced to 1.0.14. The ZIP is source, not a precompiled Setup.exe.

## Caveats

A high Flow Mbps is still a **test-server-specific** estimate and is not proof that the same node will perform well through Android or Karing. Some fast nodes may not get a stability verdict if the response-byte cap is reached before eight seconds. Source/package tests are performed on Linux/Python 3.13; Windows 11 and live Iranian network behavior remain to be verified.
