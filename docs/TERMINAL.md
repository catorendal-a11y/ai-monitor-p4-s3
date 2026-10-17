# NOVA terminal

NOVA is the PC application. Start it by typing `nova`; it runs in the current terminal.
The distribution contains Python source and board firmware, without application EXEs or Qt.

## Install on Windows

1. Install Python 3.10 or later (3.12 recommended) from https://www.python.org/downloads/windows/.
   Enable its Python launcher/PATH option. Windows Terminal is recommended for full color.
2. Download the terminal ZIP from [Releases](https://github.com/catorendal-a11y/ai-monitor-p4-s3/releases).
3. Extract it into a permanent, writable folder. Keep this folder after installation.
4. Open PowerShell in that folder and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Nova.ps1
```

This creates `.venv`, installs the pinned requirements, and registers only this user's
`nova` command. Internet is required for initial dependency installation. No administrator
access, AI sign-in, automatic provider selection or hardware flash is performed.
Open a **new terminal**, from any folder:

```powershell
nova
```

There is no separate NOVA EXE and no npm/Node.js requirement. Python and installed Python
packages may themselves contain upstream executables; they are dependencies, not bundled
AI Monitor application binaries. Windows PowerShell is used for the command shim.

## Commands and navigation

```powershell
nova --version
nova --help
nova --check
```

`--check` renders synthetic data; it does not establish a real USB/provider connection.
Use Overview and Device / Check USB for live connection status. In Settings, choose and save
your board, USB port and providers, then Start host. Keys: 1–5 pages, Tab/Enter controls,
R reload local metadata, ? help, Escape cancel forms, Q quit. Source launcher:
`AI-Monitor-Terminal.bat`. `AI-Monitor.bat` is a compatibility alias for the same terminal.

Quota, observed sessions and USB connection are separate signals. Unknown quota remains
unknown. Claude may report activity only. Stale agent events show Last rather than current
work. Opening and refreshing the dashboard never starts a model request or a second USB owner.
Invalid settings stay in the form. Secret fields are masked and unchanged keys are preserved.

Firmware / Update writes only the application partition after exact board identification and
confirmation. First installation resets display settings. Source-only Git downloads contain
no firmware: use the terminal release ZIP with both images, or build and collect them as
explained in DEVELOPMENT.md. Physical permissions remain disabled; S3 is experimental.

## Upgrade and migrate

Extract a new release to a new permanent folder, install its dependencies, then stop the old
host before moving private settings/history. Keep the original folder until the new host,
USB connection and observational hooks have been checked. Re-run Install-Nova.ps1 from the new
folder to retarget the owned command. Re-link only previously opted-in provider integrations
from Agents; provider selection alone is not permission to install hooks. An old EXE installation
must be migrated before uninstalling it because its host/hooks use the old runtime paths.

## Remove the command

From the installed folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Nova.ps1 -Uninstall
```

This removes only the owned shim and its PATH entry. It retains settings, history and the
folder, and does not stop the host. Stop the host and unlink this installation's integrations
before deleting its folder. Other users' PATH and unrelated `nova` commands are preserved.

## Development and Linux/macOS

Run `setup.ps1 -BuildTools` for development on Windows. No graphical runtime is installed.
Optional SVG artwork regeneration alone uses scripts/requirements-artwork.txt.
Linux/macOS: `./setup.sh`, then `.venv/bin/python tools/aim_terminal.py` (USB access rules may
require OS-specific setup). Windows is the tested command-registration platform.
