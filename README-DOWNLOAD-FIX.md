# Windows build fix: GitHub release asset HTTP 504

## Why the build failed

GitHub Actions passes the application's tests, then its Windows build script tries to download the pinned sing-box v1.14.4 Windows amd64 ZIP. GitHub's `/releases/download/` endpoint is returning HTTP 504 to some runners. Re-running the same old script can reproduce the same failure.

## Apply to your already-cloned GitHub Desktop repository

1. Extract this ZIP.
2. In GitHub Desktop, open **Repository -> Show in Explorer**.
3. Copy `release/build-windows.ps1` from this ZIP into your repository's `release` folder, replacing the existing file. Do not replace any other source files.
4. Commit `Use verified sing-box mirror fallback for Windows releases`, then **Push origin**.
5. In GitHub -> Actions -> IRAN REMAINS CONNECTED Windows Setup EXE, manually run the workflow on **main**, not on the v1.1 tag.
6. Confirm the log says `Verified sing-box v1.14.4 SHA256 from ...`, the job succeeds, and the output artifact includes `IranRemainsConnected-Setup-v1.1-win64.exe`, `SHA256SUMS.txt`, `sing-box-v1.14.4-source.zip`, and license notices.
7. Only after this manual build succeeds and you check the installer should you recreate/push the release tag `v1.1` on the latest commit.

## Security and integrity

The script tries the official GitHub asset first, then the SourceForge project mirror as a fallback. The script **always** checks the 64-character SHA-256 pinned in the old script (`99185d75d314a07dbba4a130c8ad986cbeb629a07927975636b341ca61f991df`). It deletes rejected or partial downloads and fails closed if no matching archive is available. This hash matches the Scoop package metadata for the official sing-box v1.14.4 Windows x64 ZIP.

The matching sing-box source ZIP is requested from `codeload.github.com` rather than the affected GitHub release-asset endpoint and is validated for expected source files.

This changes **only the release build script**. No Python scanner, GUI, VPN, subscription, node ranking, or other application code is touched. The patch was inspected and statically checked here; the actual Windows/GitHub build must still be verified in Actions.

If the build is still failing, send the fresh step's log. Do not disable SHA-256 verification to get a green build.
