# Source code and license information for release v1.1

## Application source

The complete preferred-form source of IRAN REMAINS CONNECTED, including the build workflow and Python tests, is publicly available at:

https://github.com/pacha2600/IRAN-REMAINS-CONNECTED/tree/v1.1

License: GPL-3.0-or-later (`LICENSE`). To rebuild the Windows installer, see `release/build-windows.ps1` and `.github/workflows/windows-release.yml`.

## Bundled sing-box source

The Windows installer contains **unmodified, separately executed** `sing-box.exe` **v1.14.4**, downloaded from the official SagerNet release with a fixed SHA-256 archive hash checked during the build.

The GitHub release `v1.1` distributes the tagged sing-box source as an additional, downloadable asset named **`sing-box-v1.14.4-source.zip`**, alongside the Windows Setup.exe. Its origin is:

https://github.com/SagerNet/sing-box/tree/v1.14.4

The unmodified upstream source archive is also at:
https://github.com/SagerNet/sing-box/archive/refs/tags/v1.14.4.zip

For rebuild dependencies and release compilation details, consult that tagged source tree (`go.mod`, `go.sum`, and upstream release scripts). The binary and source must correspond to the same version, including any downstream patches if such patches are introduced later.

The full sing-box GPL text and additional naming term are preserved in `licenses/LICENSE-sing-box.txt`, installed with the application; see `THIRD_PARTY_NOTICES.md`. The application makes no claim of affiliation with SagerNet.

## Practical redistribution checks

1. Keep the source repositories, bundled GPL notices, and sing-box source ZIP accessible to everyone downloading the public installer.
2. Do not distribute a new binary without the exact matching source and build instructions.
3. If the embedded core is ever modified, publish the modified corresponding source, not merely the unmodified upstream release.
4. Keep relevant copyright notices in source and binaries.
5. This document describes intended compliance measures; it is not a substitute for legal review.
