# Automatic updates

The frozen Windows EXE checks GitHub's latest stable release once after each launch. The check runs on a background thread, so the tray and usage polling start normally. Running from Python source skips the check, and a failed check shows nothing.

## The update window

If a newer release has an uploaded `AIAgentsUsageMonitor.exe` with a size and a SHA-256 digest, the app copies its own EXE to a temporary folder and starts that copy as the update window - a running file cannot replace itself, so the window has to run from somewhere else. There is no dialog before it: the window is the offer.

The window is frameless and opens in the middle of the primary monitor. It shows, in one place:

- the current and the new version, with the release's one-line summary;
- a digest of the release notes - the bullets of each section, at most eight, with a link to the full notes on GitHub;
- five steps - **Download**, **Verify**, **Close app**, **Install**, **Restart** - and a progress bar.

**Later** closes the window; the app keeps running and removes the temporary copy straight away. The next launch offers the update again.

## What "Update now" does

1. **Download** - the window streams the exact EXE the release names into a temporary file beside the installed one, following HTTPS redirects only to GitHub's release-asset hosts. The app is still running.
2. **Verify** - the byte count and SHA-256 digest must match the release metadata, and the file must be a windowed Windows executable.
3. **Close app** - the installed EXE is copied aside as a backup, and only now is the running app asked to quit. The window waits up to 30 seconds for it to exit.
4. **Install** - the new EXE atomically replaces the old one in its folder.
5. **Restart** - the new version starts with the arguments the app was launched with (for example `--config-dir`), unpacking its own files rather than inheriting the window's. It has to still be running three seconds later.

When all five are done the window shows the result and closes itself after four seconds. While files are being swapped it cannot be closed, including with Alt+F4.

## When something fails

| Failed step | What you are left with |
|---|---|
| Download or Verify | The app never stopped; nothing was changed. |
| Close app | The app was asked to quit but did not exit in time; start it again yourself. |
| Install | The old EXE is untouched and is started again. |
| Restart | The backup is put back and the previous version is started again. |

The window names the step that failed and the technical reason. If even the previous version cannot be restored, its backup stays beside the EXE and the window asks you to start the app yourself. The target folder must be writable for the update to install.

## Network and data

- `api.github.com` is queried for public release metadata at startup, and once more by the update window. No account information, usage data or credentials are included.
- The EXE is requested from `github.com` only after **Update now**. TLS certificate verification stays enabled through the Windows certificate store.
- The updater writes a temporary copy of the app, a temporary download and a temporary backup beside the EXE, then replaces the app EXE. It removes the download and the backup when it finishes, and asks Windows to delete the temporary copy at the next reboot. It does not edit `config.json`, credentials or usage records.

See [PRIVACY.md](../PRIVACY.md) for the complete data and file-access inventory.
