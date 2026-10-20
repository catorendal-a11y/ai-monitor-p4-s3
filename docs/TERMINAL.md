# NOVA terminal

NOVA is the PC application. Start it by typing `nova`; it runs in the current terminal.
The distribution contains Python source and board firmware, without a NOVA application EXE or Qt.

## Install on Windows

1. Download `nova-v1.19.1-rc18-windows-x64-terminal.zip` from [Releases](https://github.com/catorendal-a11y/limitbuddy/releases).
2. Extract it into a permanent writable folder. Keep that folder after installation.
3. Double-click **Install-Nova.cmd**. It verifies the included runtime and registers only this user's `nova` command. No administrator access is needed.
4. Open a new terminal, from any folder, and type:

```powershell
nova
```

One ZIP contains Python 3.13.16, hash-locked dependencies, NOVA source and both firmware
images. After downloading and extracting it, installation needs no extra package downloads,
pip commands, Python installation, Node.js or npm. The runtime stays inside this folder;
it does not replace other Python installations or change the global execution policy.
Provider requests and optional official AI-client setup still need their own internet access.

NOVA remains a terminal program without its own EXE or Qt frontend. The upstream Python
interpreter and dependency DLLs are vendor components under `runtime/`, with original
license files and a per-file manifest. The installer checks hashes before running Python.
Missing or changed files fail with a request to extract the complete release again.

Advanced source-only users can still run `Install-Nova.ps1` directly. A Git checkout or
GitHub's automatic source archive has no bundled runtime and requires Python 3.10+ plus
internet for setup. The normal Windows x64 release needs neither prerequisite. Setup does
not select providers, sign into an AI account, flash hardware or enable physical approvals.

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

Extract a new release to a new permanent folder and run `Install-Nova.cmd`, then stop the old
host before moving private settings/history. Keep the original folder until the new host,
USB connection and observational hooks have been checked. Re-run `Install-Nova.cmd` from the new
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
