# v1.0.17 — Diagnostics, compatibility, and usability

- Diagnose late scan stalls; split rejected large core-config groups sooner and report progress.
- Retry format negotiation by User-Agent when a fetched subscription contains no supported nodes.
- Fix erroneous successful-source state on parse failure.
- Store last 10 successfully connected proxy profiles with a dedicated tab.
- Export all HTTPS-passing nodes in JSON, BPF, and TXT.
- Add per-cycle/day lower-bound HTTP payload counters.
- Make both result tables sortable; improve connection controls and manual-proxy wording.
- New black-and-white Windows icon.
