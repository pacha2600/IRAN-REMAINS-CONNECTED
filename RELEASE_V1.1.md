# IRAN REMAINS CONNECTED v1.1 — Windows publishing guide

This repository includes a complete **single-file Setup.exe build recipe**. The application, its Python interpreter and dependencies, sing-box v1.14.4, icons, and license notices will all be contained in the generated installer. **The source ZIP itself is not the installer.** A Windows runner must compile it.

## A. Upload the source repository

1. Download and extract `IRAN-REMAINS-CONNECTED-v1.1-source.zip`. Inside is a folder named `IRAN-REMAINS-CONNECTED`.
2. Install **GitHub Desktop** from https://desktop.github.com/ and sign in to https://github.com.
3. Open GitHub Desktop → File → Add local repository → select the **inner** `IRAN-REMAINS-CONNECTED` folder. If prompted to create a repository there, do so.
4. Review **Changes** for any personal subscriptions, passwords, logs, or cached nodes; these must not be committed. Review the license considerations below.
5. Commit the source files, then click **Publish repository**. Start with a private repository for release testing if desired.
6. Verify that `main.py`, `iran_proxy_monitor/`, `release/`, `tests/` and the hidden `.github/workflows/windows-release.yml` are in the repository root. Do not upload only the ZIP.

## B. Build the Setup.exe without installing Python locally

1. On GitHub, open the repository → **Actions** → **IRAN REMAINS CONNECTED Windows Setup EXE**.
2. Choose **Run workflow** → branch `main` → **Run workflow**. The workflow needs to be present in the default branch and GitHub Actions enabled.
3. Wait for a green check on the Windows runner. It runs all Python tests, installs Inno Setup, downloads sing-box 1.14.4 using its pinned SHA-256 hash, bundles the application through PyInstaller, and builds the single Inno Setup wizard.
4. Open that workflow run → **Artifacts** → download `IranRemainsConnected-Setup-Windows`. Unzip it.
5. The artifact contains `IranRemainsConnected-Setup-v1.1-win64.exe` and a `SHA256SUMS.txt` file for verification.
6. If the workflow fails, open its failing job and inspect the logs. Do not guess that a successful source test implies a successful Windows build.

## C. Test on a real Windows 11 machine

1. Run `IranRemainsConnected-Setup-v1.1-win64.exe`. It should install via a normal wizard. Do **not** install Python or sing-box separately for this test.
2. Launch from the Windows Start menu and confirm the branded icon and version **v1.1** at the bottom right.
3. Confirm that the integrated `bin\sing-box.exe` is found (Open/Test endpoints), subscriptions load, and a scan exports JSON/TXT/BPF.
4. Verify window sizes 1600×960, 1380×900, and approximately 1060×700. Check table scroll, the outer wheel on short windows, and footer visibility.
5. Click Update subscription during a slow fetch: the three competing run/auto buttons should be disabled. Click Stop and verify the buttons re-enable **after** the task stops. Test Run once and both auto-monitor modes similarly.
6. Test Manual HTTP/SOCKS5 via a browser configured to use it and ensure non-proxied sites remain direct. Test Windows system-proxy settings restoration. Test TUN only with administrator rights and with no other TUN client active. Check IPv4/IPv6 DNS and disconnect behavior before describing it as full-device secure VPN.
7. Close, reopen, and uninstall to verify application settings/history survive and Windows proxy settings are not left pointing at a dead proxy.

## D. Publish the public GitHub release

1. Choose and document the project's own source license, and ensure the applicable sing-box GPL-3.0-or-later redistribution and source obligations are met. The build includes sing-box's license notice; licensing must still be reviewed by the project owner.
2. Confirm Windows install/scan/connect tests pass. Make the GitHub repository public when ready.
3. Tag the **tested commit** `v1.1` and push it, e.g. in a Git-enabled terminal inside the repository: `git tag v1.1` followed by `git push origin v1.1`. Do not tag a different untested commit.
4. Pushing the tag triggers the same Windows workflow; after a successful build it creates **GitHub Releases → v1.1** and attaches the Setup.exe and `SHA256SUMS.txt`. The tag is created **after** testing because tag builds automatically publish a release.
5. Check the public release's Assets and checksum; add release notes and minimum supported Windows version. If the binary is unsigned, disclose that honestly and consider a code-signing certificate before a wide public release.

Expected public URL: `https://github.com/YOUR-USERNAME/YOUR-REPOSITORY/releases/tag/v1.1`. Replace the two placeholders with your GitHub details.

## Optional developer-only local build

On Windows, with Python 3.12 and Inno Setup installed, from the repository root: `powershell -ExecutionPolicy Bypass -File .\release\build-windows.ps1`. The result appears in `release-output/`. This is **for builders**, not end users.

## What the installer does NOT provide yet

No code-signing certificate, auto-update mechanism, leak-tested kill switch, native Android application, or verified Windows TUN routing. Do not present automated Linux tests as a Windows security audit.
