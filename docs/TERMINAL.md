# AI Monitor terminal application

An interactive Textual application using the same validated operations as the
desktop app. It runs inside an existing terminal; no separate executable is required.

```powershell
.\.venv\Scripts\python.exe -m pip install -r tools/requirements.txt
.\AI-Monitor-Terminal.bat
```

Or run `.venv\Scripts\python.exe tools/aim_terminal.py` directly. The terminal
uses the existing per-user installation when present, otherwise this source project.
Use `--root "C:\path\to\AI Monitor"` for an explicit project or package. A complete
source checkout/package with host tools is required; firmware operations also need
its verified board images and flasher. Missing components are errors, not downloads.

| Page | Functions |
| --- | --- |
| Overview | Provider health, recorded quota, agents, Start host and Stop host |
| Agents | State/age/elapsed time, AI setup report, event hooks, Claude quota bridge, official Codex setup/sign-in |
| History | Daily metrics, 7/30 day report with quota windows and forecasts, CSV, confirmed clearing, diagnostic export |
| Device | Port scan, selected-board check, firmware preparation/write, real device pixels as terminal cells, companion library/import/selection/removal, physical PC enrollment |
| Settings | Board/port/providers, quota interval, masked optional key, key removal, history and shared preferences, redacted log, invalid-settings recovery |

Keys: **1–5** change page, **Tab** moves focus, **Enter** activates controls,
arrows and **PageUp/PageDown** scroll, **R** reloads metadata, **?** toggles help,
**Esc** cancels/closes forms and **Q** exits. Shortcuts do not steal text typed in
forms. Narrow windows stack panels vertically. Terminal fonts/window management
belong to the terminal emulator; tray/minimize settings apply to the desktop app.

Canceling a form runs no action. Saves reuse desktop validation and protected
storage, preserving keys unless explicitly replaced/cleared. One action worker
runs at a time; read results predating a mutation are discarded. Quit waits for
an active operation. Saved auto-start and keep-host-on-close policies are honored.
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
