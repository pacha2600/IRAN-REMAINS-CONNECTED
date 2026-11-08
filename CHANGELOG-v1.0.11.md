# v1.0.11 — source-safe subscription updates

This release fixes the incorrect impression that a newly entered subscription URL loaded successfully when the previous successful feed was actually displayed from a global cache.

- Saves last-good feed bodies under a SHA-256 source identifier rather than silently reusing an unrelated feed.
- An explicit **Update subscription** must download and parse the selected source; it reports failure instead of substituting a cache.
- Monitoring can continue with a *same-source* cache when the network fails, and labels it STALE.
- A changed ETag / Content-Range during HTTP resume causes a safe restart rather than repeated `ValueError` failures.
- Discards partial bytes when switching source URLs and labels source identifiers in logs without exposing URLs.
- GUI shows which subscription the displayed rows are from, and marks old rows after a failed request.
- The legacy last-good cache and existing exports remain preserved for recovery, but an unverified legacy cache is never assigned to a new source.
- 85 automated tests pass; Tkinter source-switching smoke test also passes on Linux/Xvfb.

**Still open:** The network can stall or reset during GitHub downloads. This release makes such failures explicit and recoverable where possible; it does not prove that the source can be downloaded successfully from every network.
