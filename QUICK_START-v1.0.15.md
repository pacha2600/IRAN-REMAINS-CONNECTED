# Quick start — v1.0.15

1. Extract this ZIP on Windows 11.
2. Open PowerShell in the `IranProxyMonitor` directory and run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install.ps1 -LocalSingboxPath 'D:\sing-box.exe'
   .\launch.cmd
   ```

3. Use **Update subscription** or **Run one cycle**, select a node, and click **Connect selected**. Alternatively connect a rank from a saved shortlist without running a scan.
4. Select **Manual HTTP/SOCKS5** to use only apps that you point at `127.0.0.1:20808`; select **Windows system proxy** for apps honoring Windows proxy settings; or launch the GUI **as administrator** and select **Device-wide TUN** for broader routing.
5. Click **Test connection**, then **Disconnect** when done.

All scan algorithms from v1.0.14 are unchanged. See [CLIENT_GUIDE-v1.0.15.md](CLIENT_GUIDE-v1.0.15.md) for precautions, how TUN works, and Windows acceptance tests.

For distribution of a real `Setup.exe`, push this source to GitHub and use `.github/workflows/windows-release.yml` on a Windows runner; publish the installer only after testing it on Windows.
