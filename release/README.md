# Windows release build (no Python requirement for end users)

**For first-release step-by-step instructions see `../RELEASE_V1.1.md`.**

**Development/test ZIP**: source Python and the existing `install.ps1` installer.

**Public Windows release**: upload the repository to GitHub, select **Actions → Windows Setup EXE → Run workflow**. Download `IranRemainsConnected-Setup-Windows` artifact after the workflow completes. Inside is `IranRemainsConnected-Setup-v1.1-win64.exe` for Windows 11 users to double-click. No Python, pip or PowerShell required for users.

A `v1.1` Git tag additionally publishes the Setup EXE in GitHub Releases (provided Actions permissions permit release creation). The workflow uses a Windows runner, Python 3.12, PyInstaller, and Inno Setup 6. It includes the pinned, SHA-256-verified sing-box 1.14.4 core in the installer so end users do not have to download the core separately.

Build locally on Windows by installing Python 3.11–3.13 and Inno Setup 6 and running `release/build-windows.ps1` from PowerShell. **The developer builds with Python and PowerShell; end users do not.**

The executable installer is **not** included in the development source ZIP unless the Windows CI workflow has built it. The CI recipe is prepared but has not been executed on a Windows runner in this environment. Avoid presenting it as a verified release binary until the workflow passes.

Stored settings, history, and exports remain in `%LOCALAPPDATA%\IranProxyMonitor` across app upgrades and uninstall/reinstall (they are not part of the Inno Setup installation directory). The release recipe includes the GPLv3 sing-box license and the bundled PyYAML license in `licenses/`. Before publishing, review the GPLv3 redistribution/source obligations, ensure sing-box corresponding source is available from the official project, run a security scan, and consider code-signing the unsigned installer.
