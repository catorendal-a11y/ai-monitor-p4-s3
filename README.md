# NOVA — AI Monitor

A full-color terminal dashboard and USB companion for an ESP32 display. Start it with:

```powershell
nova
```

![NOVA terminal with synthetic sample data](docs/media/terminal-preview.png)

[Download the terminal package](https://github.com/catorendal-a11y/ai-monitor-p4-s3/releases/tag/v1.19.1-rc15)
· [Install and start](docs/TERMINAL.md) · [Provider setup](docs/PROVIDERS.md)
· [Development](docs/DEVELOPMENT.md)

## Install

Windows 10/11, Python 3.10+ (3.12 recommended), an internet connection for initial setup,
and a USB data cable for the display. Extract the terminal ZIP into a permanent writable
folder, open PowerShell there, and run once:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Nova.ps1
```

Open a new terminal and type `nova`. It works from any folder. The script installs pinned
Python dependencies in an isolated environment and registers the per-user command. No
application EXE, graphical Windows app, Qt, npm or Node.js is needed. Setup does not select
providers, sign into accounts or flash hardware. Keep the extracted folder.

The terminal replaces the former EXE/graphical distribution. For an existing EXE installation,
see [migration guidance](docs/TERMINAL.md#upgrade-and-migrate) before removing its runtime.
The ZIP includes both board-specific application/factory images, source and notices.

## What NOVA shows and controls

- Overview: recorded quota, its age/window, USB status, NOVA artwork and observed agents.
- Agents: actual observed sessions, provider setup, explicit event links and sign-in help.
- History: local numeric usage, lifecycle reports and private exports; unknown gaps stay unknown.
- Device: selected board/port, verified firmware updates, companion packs and USB screen capture.
- Settings: saved provider/board settings and scoped background host controls.

Use 1–5 to change pages, Tab/Enter for controls, R to reload local metadata, ? for help,
Escape to cancel, and Q to quit. The host can keep running after the terminal closes.
`nova --version`, `nova --help` and `nova --check` are available. The check uses synthetic data.

Provider quotas depend on supported account/key/bridge access. Codex, Z Code and Claude have
separate quota/activity/event capabilities. Selected providers never count as active agents.
See [provider capabilities](docs/PROVIDER_ROADMAP.md) and [privacy](docs/GITHUB_SECURITY.md).
No model prompts, conversations or tool arguments are sent to the display. USB only; no Bluetooth.

## Displays

| Board | Status | USB |
| --- | --- | --- |
| GUITION JC4880P433 ESP32-P4 | Production target | Espressif data port |
| Waveshare ESP32-S3 Touch LCD 4.3 | Experimental; physical touch/hardware unverified | USB TO UART |

The display has NOVA/ORBIT animation, quota cards, observed agents, history and four saved
palettes. Firmware writes require explicit confirmation. Physical permission approval stays
disabled. Source tests are not physical validation; no new eight-hour endurance pass is claimed.

![NOVA display rendered with synthetic data](docs/nova-preview.png)

## Build and contribute

Read [AGENTS.md](AGENTS.md) and [DEVELOPMENT.md](docs/DEVELOPMENT.md). Git stores source,
assets and tests, without credentials, logs, databases, generated firmware or EXEs.
[Releasing](docs/RELEASING.md) describes source/firmware ZIP creation and reviewed publication.

Project-owned code/artwork is MIT; preserve [third-party notices](THIRD_PARTY_NOTICES.md).
