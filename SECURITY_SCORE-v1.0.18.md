# v1.0.18 encryption and configuration security score

The **Encryption** and **Security /100** columns in **All nodes**, **Working nodes** and **Recent connections** are computed locally from the sing-box outbound settings. They do **not** measure anonymity, the honesty of the proxy operator, DNS leakage, endpoint security, or cryptographic resistance in a live test. The upstream configuration can make claims that are incorrect or malicious. To inspect a specific assessment, select a row and right-click **Explain encryption / security score**.

## Static scoring rules (heuristic)

| Configured upstream layer | Starting score | Interpretation |
| --- | ---: | --- |
| VLESS / Trojan with REALITY/TLS | 94 | Explicit REALITY/TLS transport configured |
| VLESS / Trojan with TLS | 92 | TLS configured; normal cert validation expected |
| WireGuard | 94 | WireGuard authenticated encrypted tunnel configured |
| Hysteria, Hysteria2, TUIC, naive, AnyTLS | 92 | TLS-based proxy protocol configured |
| Shadowsocks 2022 AEAD | 91 | Modern authenticated cipher configured |
| Shadowsocks AEAD | 84 | AEAD cipher configured |
| VMess AEAD + TLS | 91 | VMess payload encryption and TLS configured |
| VMess AEAD without TLS | 77 | VMess payload encryption alone |
| VMess legacy cipher | 42 | Older cipher; avoid unless separately reviewed |
| VMess legacy cipher + TLS | 83 | TLS mitigates legacy payload cipher concerns |
| VMess cipher off, but TLS on | 86 | TLS is the configured security layer |
| HTTPS proxy (HTTP outbound with TLS) | 87 | TLS to upstream proxy |
| SSH | 84 | Encrypted SSH hop; host-key trust needs separate review |
| Plain HTTP/SOCKS, VLESS without TLS, Shadowsocks method `none`, or VMess encryption disabled without TLS | 5 | No identified encrypted upstream proxy hop |
| Unrecognized or missing encryption method | Unassessed | Score omitted rather than claiming it is insecure or secure |

When a node's TLS options include `insecure: true`, **subtract 35** from the starting score (minimum zero) and append **unverified cert** to its Encryption label. Certificate verification disabled is a serious active-impersonation risk.

Scores never add points merely because a subscription says a node is in a particular country, is named "secure", or offers a fast connection. They are based on normalized outbound fields, not raw descriptions. They do not perform cipher negotiations or inspect actual traffic on the wire.

**Impact on the rankings:** Best overall's existing performance-based score is multiplied by a configuration-security factor: `1.00` at scores ≥85; `0.91` at 70–84; `0.78` at 50–69; `0.60` at 20–49; `0.35` below 20; or `0.78` if unassessed. This intentionally lowers unencrypted nodes, while preserving every latency and throughput measurement. **Best download speed** and **Best ping** remain performance-only lists so users can compare them independently. **Best reliable** retains its prior definition: confirmed Flow ≥1 Mbps, then historical HTTPS success.

An HTTPS browser connection is often encrypted end-to-end to the *website* regardless of whether the upstream proxy hop itself is encrypted. The new column specifically describes the **device-to-proxy hop** and must not be mistaken for an assessment of all traffic or privacy. A proxy operator can still monitor destinations and non-end-to-end-encrypted content. TUN versus Manual determines which apps are captured, not whether the proxy provider itself is trustworthy. There is **no device-wide kill switch** in this release.

See the sing-box documentation for [VLESS](https://sing-box.sagernet.org/configuration/outbound/vless/), [VMess](https://sing-box.sagernet.org/configuration/outbound/vmess/), [Shadowsocks](https://sing-box.sagernet.org/configuration/outbound/shadowsocks/), and [TLS](https://sing-box.sagernet.org/configuration/shared/tls/).
