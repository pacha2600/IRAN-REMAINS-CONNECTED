# Before making v1.1 public — license patch

This patch provides the project GPL-3.0-or-later license, explicit sing-box/PyYAML attribution, full matching sing-box source archive as a release asset, and installed license notices.

## Apply

1. **Before creating the `v1.1` tag**, open the repository folder through GitHub Desktop (**Repository → Show in Explorer**).
2. Copy **all files and folders** from this patch directory into the repository root. Preserve `.github/workflows/windows-release.yml` and `release/build-windows.ps1`, replacing these two files. **Do not replace** `gui.py`, `monitor.py`, or any scanner/VPN code.
3. Confirm GitHub Desktop shows `LICENSE`, `THIRD_PARTY_NOTICES.md`, `SOURCE_AND_COMPLIANCE.md`, and changes in the workflow and build script.
4. Commit **Add GPL license and sing-box redistribution notices**, push to `main`.
5. Manually run Actions → Windows Setup EXE and verify the artifact includes `sing-box-v1.14.4-source.zip`, `THIRD_PARTY_NOTICES.md`, and `SOURCE_AND_COMPLIANCE.md` beside the installer and checksum.
6. Confirm that the installed app contains `licenses/LICENSE`, `licenses/LICENSE-sing-box.txt`, `licenses/LICENSE-PyYAML.txt`, and the two notices. If any file is absent, stop and fix the workflow.
7. Once the matching source and installer are confirmed, publish/tag v1.1 and make the repository public.

## What this does *not* change

It changes only the license/documentation and release packaging. **No scanning, ranking, client routing, TUN, proxy, GUI, or app settings are modified.**

## Important owner check

The GPL-3.0-or-later choice for original application code is a practical open-source choice intended to align with the bundled GPL core. You, as repository owner, should confirm you have the rights to license the code and that the repository contains no private keys, proprietary copied material, or subscription credentials. This is not a formal legal opinion.
