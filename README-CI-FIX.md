# v1.1 — Windows GitHub Actions test corrections

The first Windows Actions run (42503667293) stopped on 5 failures out of 195 tests.
This patch changes four files; the application version stays v1.1.

## Changes

- `iran_proxy_monitor/monitor.py`: on cancelled subscription downloads, close the underlying socket after shutdown. Windows can otherwise leave a blocking read pending. Cancellation still never promotes partial bytes into the complete subscription cache.
- `iran_proxy_monitor/gui.py`: cancel delayed icon/layout callbacks when the GUI closes, and expose the dashboard content frame for layout verification.
- `tests/test_v110_release.py`: accept Windows short-path (`RUNNER~1`) and long-path (`runneradmin`) aliases when testing the bundled sing-box core; test the scrollbar against the actual required content height, which differs across Windows DPI/font settings.
- `.github/workflows/windows-release.yml`: update setup-python to v6 (Node.js 24).

## Apply to your repository

Extract the ZIP; copy its `.github`, `iran_proxy_monitor`, and `tests` folders into the ROOT of the Git repository, choosing **Replace** for files with the same names. Do not copy README-CI-FIX.md unless you want to keep these notes. In GitHub Desktop, review the four changed files, commit "Fix Windows CI test failures for v1.1" and click **Push origin**. Re-run **Actions > IRAN REMAINS CONNECTED Windows Setup EXE > Run workflow** on main. Do not create tag v1.1 yet.

## Verification

195 tests passed on Linux/Xvfb; Windows CI must be rerun to confirm cancellation and GUI behavior on Windows. No Setup.exe has been built or tested by this local patch.
