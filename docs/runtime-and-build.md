# Portable runtime and build

## Running the single EXE

Keep `AIAgentsUsageMonitor.exe` in a writable folder. The public EXE is a .NET Framework launcher compiled from `launcher.cs`; it contains the PyInstaller application as an embedded resource. No separate runtime files need to be distributed.

For each launch it creates `.AIAgentsUsageMonitor-runtime-<unique id>` beside itself, copies the embedded application there, and sets that application's `TEMP` and `TMP` to a private `temp` subfolder. Python libraries, popup pages, fonts, certificates and the WebView2 temporary profile all stay under that runtime folder. Cleaning the system temporary directory therefore cannot remove files the running app still needs.

The launcher waits for the application to exit, then deletes its runtime folder. If termination or a file lock leaves a folder behind, the next launch checks its ownership marker and tries to remove it. A marker held open by either the launcher or Python identifies an active runtime; another instance leaves it alone. Unmarked folders, folders owned by another executable and directory junctions are skipped. If the EXE's folder is not writable, startup reports the error rather than extracting elsewhere.

The public EXE remains the identity used for settings lookup, autostart, event-command working directories and update replacement. `runtime.py` provides that identity separately from the internal Python executable. Event commands receive the original `TEMP` and `TMP`, so a program opened by a quick action can outlive the monitor independently.

The updater uses a separate `ai-agents-updater-*` staging folder beside the installed EXE. This staging folder survives the installed app's shutdown; see [automatic updates](automatic-update-check.md) for its verification, replacement and cleanup lifecycle.

## Building

Use Windows with the Python dependencies in `requirements.txt` installed and the virtual environment activated. `build.py` uses the .NET Framework compiler and Windows metadata already present on Windows for both the glass layer and the launcher.

```powershell
. .\.venv\Scripts\Activate.ps1
$buildTemp = 'F:\temp\AIAgentsUsageMonitor'
New-Item -ItemType Directory -Path $buildTemp -Force | Out-Null
$env:TEMP = $buildTemp
$env:TMP = $buildTemp
$env:PYINSTALLER_CONFIG_DIR = Join-Path $buildTemp 'pyinstaller-cache'
python build.py
```

The build checks the version sources and local screenshot fingerprint, compiles the glass layer, builds the PyInstaller payload in the build working directory, and embeds it in the public launcher. It then starts the resulting EXE with `--self-test`. That check verifies the packaged imports, Windows Runtime notification types, page files, locales and tray rendering, and confirms that Python's bundle and temporary storage are inside the private runtime beside the public EXE. It does not post a notification. A failed or timed-out self-test fails the build.

The deliverable is **`dist/AIAgentsUsageMonitor.exe`**. Run `python build.py` for that complete artifact; invoking PyInstaller on the spec directly produces only the internal payload. The local screenshot pipeline must refresh its fingerprint whenever a popup input changes; the build does not bypass that guard.

## Running from source

```powershell
python build.py glass
python -m ai_agents_usage_monitor
```

The first command prepares the optional glass layer. Source execution uses the project root for settings lookup and event-command working directories and does not create the launcher's private runtime. Its temporary files follow the environment set for that Python session.
