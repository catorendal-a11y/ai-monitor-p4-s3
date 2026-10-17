# AI Monitor terminal application

An interactive Textual application using the same validated operations as the
desktop app. It runs inside an existing terminal; no separate executable is required.

## Install on Windows

1. Download the complete **ai-monitor-p4-v1.19.1-rc12-windows.zip** from the
   [rc12 release](https://github.com/catorendal-a11y/ai-monitor-p4-s3/releases/tag/v1.19.1-rc12).
   Use **Extract All** into a writable folder. Keep all files together; do not run
   inside the ZIP. The source checkout also works, with firmware limits below.
2. Install **Python 3.12 x64** from [python.org](https://www.python.org/downloads/windows/).
   Python 3.10+ is supported; 3.12 is tested in CI. Python is required for this
   source-based terminal, even when the graphical app is already installed.
3. Open PowerShell in the extracted folder and run the setup once:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
   ```

   This creates `.venv`, downloads pinned dependencies and initializes an empty
   configuration only if none exists. Existing settings are preserved. Initial
   setup needs internet; it does not install firmware or sign into AI accounts.
4. Double-click **AI-Monitor-Terminal.bat**, or run:

   ```powershell
   .\AI-Monitor-Terminal.bat
   ```

For later starts, only step 4 is needed. Use Windows Terminal with a monospace
font and a window of at least **120 columns x 30 rows** for the full dashboard.
Smaller windows scroll or stack panels. No terminal EXE is required. The installer
and graphical EXE remain available separately and do not need Python.

## First use

Press **5** for Settings, choose **Edit settings**, select your board, USB port and
providers, then save. No board or provider is chosen automatically for a fresh
installation. Use **Start host** to begin monitoring. If the graphical app's host
is already running, the terminal uses that owner instead of opening a second USB
connection. Press **2** for integration checks and explicit observer setup.
Missing quota is shown as unknown or activity-only; linking observers does not
create account quota or approve provider tools.

## Source and existing installations

Or run `.venv\Scripts\python.exe tools/aim_terminal.py` directly. The terminal
uses the existing per-user installation when present, otherwise this source project.
Use `--root "C:\path\to\AI Monitor"` for an explicit project or package. A complete
source checkout/package with host tools is required; firmware operations also need
its verified board images and flasher. Missing components are errors, not downloads.
The GitHub **Source code** ZIP has no firmware or compiled flasher. Use the full
Windows package for firmware installation, or build/collect both images following
[Development](DEVELOPMENT.md). A normal terminal setup does not need BuildTools
or FlashTools.

| Page | Functions |
| --- | --- |
| Overview | Reference-style provider table, recorded quota, device/NOVA panels and observed-agent table |
| Agents | State/age/elapsed time, AI setup report, event hooks, Claude quota bridge, official Codex setup/sign-in |
| History | Daily metrics, 7/30 day report with quota windows and forecasts, CSV, confirmed clearing, diagnostic export |
| Device | Port scan, selected-board check, firmware preparation/write, real device pixels as terminal cells, companion library/import/selection/removal, physical PC enrollment |
| Settings | Start/Stop host, board/port/providers, quota interval, masked optional key, key removal, history and shared preferences, redacted log, invalid-settings recovery |

Keys: **1–5** change page, **Tab** moves focus, **Enter** activates controls,
arrows and **PageUp/PageDown** scroll, **R** reloads metadata, **?** toggles help,
**Esc** cancels/closes forms and **Q** exits. Shortcuts do not steal text typed in
forms. Narrow windows stack panels vertically. Terminal fonts/window management
belong to the terminal emulator; tray/minimize settings apply to the desktop app.
Wide windows also adapt to height: the quota rows become denser and the NOVA
panel shrinks to keep the observed-agent table visible at 120 × 30 characters.
Additional provider rows remain scrollable. NOVA uses original artwork drawn
with colored terminal cells, with poses selected only from observed agent states.

The Windows launcher explicitly enables true color in its own environment. This
prevents inherited `NO_COLOR=1` / `TERM=dumb` values from a coding runner turning
the app monochrome; no global Windows or terminal profile settings are changed.

The dashboard uses filled quota bars with amber/red low-remaining indicators,
colored agent status dots and separate device/companion panels. Labels accompany
colors. History shows daily token sparklines, scaled separately per provider;
dots mark unknown gaps and the lowest block represents zero/minimum. These are
recorded observations, not live token streams. Unknown agent phases remain unknown.

Canceling a form runs no action. Saves reuse desktop validation and protected
storage, preserving keys unless explicitly replaced/cleared. One action worker
runs at a time. Invalid settings keep the draft open, focus the affected field
and show a fixed error above the buttons; numeric limits, board, port and provider
selection are checked before submission. Draft keys stay masked and are cleared
when the form is submitted or canceled. Read results predating a mutation are discarded.
Quit waits for an active operation. Saved auto-start and keep-host-on-close
policies are honored.
Navigating does not save settings. Export files are published exclusively: existing
or concurrently created files are never overwritten.

Firmware preparation shows the exact board/port/operation before typed **FLASH**
confirmation. The shared writer revalidates selection/files, stops the owned host
and verifies device identity. Writes are never retried automatically. Clearing
requires **CLEAR** and reuses consent revocation, transactional deletion and prior
host restoration. Provider links/removal and invalid-settings recovery also have
explicit confirmations.

Monitoring uses metadata and numeric history without provider requests or model
turns. Quota is labeled **Recorded** with age/window; missing or disabled history
means unknown percentages. Selecting a provider creates no agent row. Observer
states older than 30 seconds say **Last**. Elapsed run time includes waiting and
is not active time. Unknown metrics/gaps remain unknown. Device facts show age.
Credentials and conversations are never displayed or exported.

Pixels and companion transfers use the existing host owner. Protected screens and
virtual touch stay excluded. Enrollment retains physical comparison, timeout and
hold requirements. Production AI approval remains disabled. Terminal tests do not
establish physical touch/approval or S3 hardware validation.

`python tools/aim_terminal.py --check` runs a headless synthetic smoke check without
private settings/hardware. `tests/test_terminal*.py` cover keyboard, resizing,
cancellation, privacy and the shared action guards.
