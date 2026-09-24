# Automatic updates

Starting with version 3.0.0, the frozen Windows EXE checks GitHub's latest stable release once after each launch. The check runs on a background thread, so the tray and usage polling can start normally. Running from Python source skips the check.

If a newer release has an uploaded `AIAgentsUsageMonitor.exe`, a size and a SHA-256 digest, the app asks whether to install it. Choosing No leaves the app running. The app does not silently download or replace itself.

Choosing Yes copies the running EXE to a temporary helper EXE and starts that copy as a separate process. The helper shows preparation, download, verification, waiting, installation and completion states. The main app exits. The helper downloads the exact EXE named by the release, checks its byte count and SHA-256 digest against the release metadata, waits for the running process to close, then atomically replaces the EXE in its current folder. Click **Close** after completion; the app does not automatically restart.

If the download, verification or replacement fails, the original EXE remains in place and the helper shows the error. The target folder must be writable for replacement. If another running instance still holds the same EXE, close it and retry at the next launch. A helper copy left in the operating system's temporary folder is scheduled for removal at the next reboot.

## Network and data

- `api.github.com` is queried for public release metadata at startup. No account information, usage data or credentials are included.
- After consent, the helper requests the release asset from `github.com` and accepts HTTPS redirects only to GitHub's release-asset hosts.
- TLS certificate verification remains enabled through the Windows certificate store. The downloaded file must match the release's size and SHA-256 digest before it can replace the existing EXE.
- The updater writes a temporary helper and temporary download, then replaces the app EXE. It does not edit `config.json`, credentials or usage records.

See [PRIVACY.md](../PRIVACY.md) for the complete data and file-access inventory.
