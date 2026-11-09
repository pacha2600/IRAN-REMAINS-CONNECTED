# Third-party notices — IRAN REMAINS CONNECTED v1.1

IRAN REMAINS CONNECTED is an independent, community-developed application. It is not affiliated with, sponsored by, or endorsed by SagerNet or the sing-box project.

## sing-box v1.14.4

- **Component:** official upstream sing-box executable, shipped as a separately launched process in `bin/sing-box.exe`; not modified by this project.
- **Copyright:** Copyright (C) 2022 nekohasekai and sing-box contributors.
- **License:** GNU General Public License, version 3 or (at your option) any later version, plus the upstream naming/non-affiliation condition.
- **Project:** https://github.com/SagerNet/sing-box
- **Exact upstream version:** https://github.com/SagerNet/sing-box/tree/v1.14.4
- **Corresponding source:** The public v1.1 GitHub release attaches `sing-box-v1.14.4-source.zip`, a copy of the tagged upstream source archive. See `SOURCE_AND_COMPLIANCE.md` for exact instructions.
- **Full license text:** `licenses/LICENSE-sing-box.txt` installed with the application, and https://github.com/SagerNet/sing-box/blob/v1.14.4/LICENSE
- **Additional upstream term (preserved verbatim):** “In addition, no derivative work may use the name or imply association with this application without prior consent.”

Using the phrase “powered by sing-box” is only a factual attribution and does not suggest endorsement.

## Vendored PyYAML code

- **Component:** code within `iran_proxy_monitor/_vendor/`.
- **License:** See `licenses/LICENSE-PyYAML.txt` in the installer and `iran_proxy_monitor/_vendor/PyYAML-LICENSE.txt` in the repository.

## IRAN REMAINS CONNECTED itself

The original application source in this repository is offered under **GPL-3.0-or-later**; see the top-level `LICENSE`. This notice does not supersede the separate applicable licenses of upstream components.

## Additional bundled dependencies

Python and PyInstaller are used for packaging, and Python standard-library components are included in the frozen build. Their upstream copyright/license terms remain applicable; see https://docs.python.org/3/license.html and https://pyinstaller.org/en/stable/license.html . Before distribution, review the final PyInstaller distribution for any other bundled third-party libraries and retain their notices.
