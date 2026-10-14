# Developer guide

A USB desk display for AI usage limits and locally observed token activity, built for the **GUITION JC4880P433 ESP32-P4** and an experimental **original Waveshare ESP32-S3-Touch-LCD-4.3** target. [Board compatibility](BOARDS.md). A Python companion reads Codex and optional Z.AI coding-plan usage; the firmware displays it without storing cloud credentials.

The current development candidate is shown by `FW_VERSION` in `src/config.h`; see [v2 status](V2_STATUS.md) for validation boundaries. The interface, code comments and documentation are in English.

## Features

- NOVA, an animated robot with working, ready, celebration, low-quota, resting and connection states.
- Dashboard, provider details, reset countdowns and manual refresh.
- Session-local history with data gaps, time labels and 1 / 6 / 24-hour views.
- Configurable quota warnings, critical alerts and dismiss/rearm behavior.
- Backlight presets, gradual idle dimming, night scheduling with hour/minute controls, and persistent settings with save feedback.
- USB heartbeat, reconnect handling, last-valid data during API errors, and rate-limit backoff.
- Visible token-source tracking, signal-loss feedback and time since the last registered increase.

## Hardware and toolchain

The target has a ST7701S 480 x 800 MIPI-DSI panel, GT911 touch, 16 MB flash and 32 MB PSRAM. LVGL presents an 800 x 480 landscape interface. Touch uses GPIO 7/8; backlight PWM uses GPIO 23. Other boards require review of their display initialization and pin assignments.

[platformio.ini](../platformio.ini) pins pioarduino P4 `55.03.312-1` to commit `2959e98a2750832bca32fd2f849c0c274a4cdd63`, LVGL `v9.6.0` to commit `80ca777e37a2b176770726a02e07a6fb79ef0b39`, and ArduinoJson to `7.4.3`. Use Python 3.10 or later. Initial builds need internet access to download dependencies.

S3 uses its own `esp32s3-waveshare-43-release` environment, pioarduino `54.03.20` pinned to commit `c6f1f4164d16dae8fda13221eb0f2722429175c6`, Arduino 3.2.0 and Espressif's matching high-performance SDK. It requires 8 MB OPI PSRAM and PSRAM XIP, uses native RGB/GT911/CH422G drivers and UART0 on GPIO44/43. Build it with `python -m platformio run -e esp32s3-waveshare-43-release`. Replace the environment in upload commands when working on S3, and use USB TO UART. Native tests run protocol/UI checks under both board profiles; hardware drivers still need a physical board test.

PlatformIO keeps its core, Python environment and board SDKs inside this project's ignored `.pio/core` directory. This avoids loading native Python modules or SDKs from another project's global installation. Build P4 and S3 sequentially, collecting each image pair before switching boards: their pinned platforms use different shared Arduino SDK versions. The first build downloads a fresh toolchain; see [local release builds](RELEASING.md#local-build-on-windows).

The 32 KiB Arduino startup stack still covers display/touch/USB initialization. After setup completes, loop() unregisters its own loop-task watchdog and deletes that unused task, releasing its stack. UI and USB continue in their dedicated tasks; no watchdog for those tasks is disabled. Do not reduce the startup allocation without measuring its high-water mark on both physical targets.

## Windows quick start

From the project directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -BuildTools
.\.venv\Scripts\python.exe -m platformio run -e esp32p4-release
```

Setup creates an isolated `.venv`; `-BuildTools` installs PlatformIO alongside host dependencies, and copies the credential-free example to `tools/aim_host.json` only if no local configuration exists. It does not flash hardware or start the host.

Stop the companion before flashing. List ports, then replace `COM6` with your device's port:

```powershell
.\.venv\Scripts\python.exe -m platformio device list
.\.venv\Scripts\python.exe -m platformio run -e esp32p4-release -t upload --upload-port COM6
```

Build output is in `.pio/build-fw/esp32p4-release/`: `fw_*.bin` is the application; `fw_*.factory.bin` includes the bootloader and partitions. PlatformIO upload selects the appropriate output automatically.

Start interactively:

```powershell
.\.venv\Scripts\python.exe tools/aim_host.py
```

Or run `tools/start-aim-host.bat` for the Windows background launcher. It briefly opens a console, starts the companion with `pythonw.exe` when available, then closes the console. A desktop shortcut can target this batch file. The launcher prefers this checkout's `.venv`, then PlatformIO's Python, then Python on PATH; it checks pyserial and restarts only hosts using this exact script path. Logs remain in `tools/aim_host.log`. Personal desktop shortcuts are not included.

To stop the background host, use Task Manager and identify its Python process by the command line pointing to this checkout's `tools/aim_host.py`.

## Linux / macOS

```sh
sh setup.sh
.venv/bin/python -m pip install "platformio>=6.1,<7"
.venv/bin/python -m platformio run -e esp32p4-release
.venv/bin/python -m platformio device list
# Replace the example with your actual serial device:
.venv/bin/python -m platformio run -e esp32p4-release -t upload --upload-port /dev/ttyACM0
.venv/bin/python tools/aim_host.py
```

Serial permissions depend on the operating system. The hidden desktop launcher is Windows-specific.

## Configuration and credentials

Use [tools/aim_host.example.json](../tools/aim_host.example.json) as the shareable template. The companion loads `tools/aim_host.json` and creates defaults if absent.

| Setting | Meaning |
| --- | --- |
| `board` | `guition-p4` or `waveshare-s3-43`; empty until first-time setup. Older configurations without this field retain P4. |
| `port` | `auto` connects only when exactly one candidate port for the selected board is found. With multiple boards, set an explicit port; the host logs the candidates and waits. |
| `interval_s` | API interval from 15 to 240 seconds; default 240. Valid configuration edits are applied while running. |
| `zai_provider` | Keep `zcode`. |
| `zai_key` | Optional local coding-plan credential; empty in the example. Prefer environment variable `ZAI_API_KEY`, which takes precedence. |

Codex quota is read through the official CLI's account RPC when the CLI is available. This read does not start model turns. If no CLI is found, the host has a legacy read-only `auth.json` fallback under `CODEX_HOME` or `~/.codex`. It does not copy, embed or modify that login. Sign in through the official client when needed. Z.AI requires your own coding-plan credential. The host does **not** load `.env` files automatically; `.env.example` documents the optional variable only.

No credentials are needed to build or test. Local configuration, auth files, environment files, databases, logs and build output are excluded by `.gitignore`. Never put real credentials in examples, issue reports or screenshots. Provider endpoints and local database schemas can change; unsupported responses produce an error instead of invented values. This is an independent project, not an official integration.

## What NOVA measures

NOVA follows **increases in local numeric token counters**, independently of keyboard, mouse and touchscreen activity:

- Codex: `threads.tokens_used` in `~/.codex/state_5.sqlite`.
- ZCode: `model_usage.computed_total_tokens` in `~/.zcode/cli/db/db.sqlite`.

The companion uses read-only SQLite queries for Codex/ZCode. Claude/Gemini log adapters parse selected local records to retain usage counters and record IDs; conversation text is not retained, logged or exported. It checks approximately every two seconds, including during API requests. Existing totals establish a baseline and do not count as new activity. See [provider support](PROVIDERS.md) for configuration and limitations.

NOVA's TRACKING line names the currently readable sources, not which application generated the last increase. The robot caption shows elapsed time since the last increase. Large increments use compact units (K/M/B and higher, truncated to one decimal); the USB info response retains the exact count. Unavailable or stale signals are shown explicitly. Quota cards distinguish updates in progress from stale measurements.

The host retains up to 16,384 recently observed IDs per source. A bounded conservative tombstone filter baselines retired IDs when they reappear, preventing historical totals from becoming invented new consumption. A filter collision can omit a first increment rather than invent one. Both caches are session-local. Changes to local database schemas may require adapter updates.

Quota requests run in an allowlisted helper process with a 25-second request budget and a 45-second total-cycle budget. Credentials travel through stdin, never command arguments. Timeout cleanup must reap the helper and its descendants before another request starts; USB heartbeats continue while it is working. Local token polling permits 2–15 seconds, and firmware allows 35 seconds of signal age to accommodate scheduling and I/O delay. Loss of the USB host immediately invalidates the signal.

One coalesced local-count worker performs database/file reads independently of the USB owner. A blocked read cannot delay heartbeats or create replacement threads; its old signal expires. Changing providers discards results from the previous configuration. The worker retains only numeric records and never sends USB frames itself.

Observed token consumption takes priority over NOVA's low-quota expression; quota bars and warning banners still report low/critical limits. After 90 seconds without a new registered increase, NOVA briefly celebrates the pause and becomes ready; after five minutes it may rest. Dimming does not prove inactivity. Missing or stale activity signals do not prove rest.

**Registration can lag generation until a request reports usage.** This is not per-token streaming, billing measurement, proof of completed work, or an account-wide usage total. Missing/incompatible databases cannot establish activity. Numeric activity diagnostics in the USB info response help distinguish counter detection from quota polling.

## Screen behavior

NOVA is the default view. Use **MENU > HOME / USAGE** to switch, tap provider cards for details, or open **MENU > SETTINGS**. Details support previous/next and swipe navigation. **REFRESH on the home screen** requests an API round and reports waiting, progress and result; minimum intervals and provider backoff still apply. **MENU > HISTORY** opens the compact Today/24h/7d summaries from the existing PC database. See [device navigation](DEVICE_NAVIGATION.md) for the simplified controls and larger typography.

History stores valid samples in five-minute buckets for up to 24 hours since firmware startup and clears on restart. Failed/stale measurements do not fabricate samples. Dismissed LOW/CRITICAL alerts rearm after recovery with hysteresis. Night scheduling uses time from the host. Settings are stored locally in NVS.

## Verification

Python tests use fake responses and temporary databases; no device or credentials are required:

```powershell
.\.venv\Scripts\python.exe -m pip install -r scripts/requirements-test.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

After a firmware build downloads ArduinoJson/LVGL, use a C++17 compiler on PATH for protocol/settings regressions. UI tests also need GCC, CMake and Ninja:

```powershell
.\.venv\Scripts\python.exe scripts/run_tests.py
.\.venv\Scripts\python.exe scripts/run_tests.py --ui --screenshots work/ui-previews
```

Use `--cxx` / `--cc` for explicit compiler paths. On Linux/macOS use `.venv/bin/python`. Native UI tests generate PPM screenshots and mock hardware; physical touch and flashing require the board. CI runs Python, release firmware and native regressions without credentials.

## Troubleshooting

- **No connection:** close serial monitors, choose the correct port and use a USB data cable. Multiple Espressif devices need an explicit port.
- **No token reaction:** check whether the application updates the supported database and allow time for request usage registration. Inspect numeric activity diagnostics. Quota fetching alone does not establish consumption.
- **API errors:** check CLI login/local Z.AI credential; share only redacted status messages, never authentication files.
- **Upload cannot open port:** stop the companion and other serial clients first.
- **Unexpected brightness:** SET shows selected/actual brightness and NORMAL / NIGHT / IDLE. Check the schedule and idle timeout.

## Assets, licensing and contributions

Project-owned code and original NOVA artwork use [MIT](../LICENSE). Drivers, dependencies, fonts and provider marks retain their own terms: see [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) and [asset sources](../assets/nova/SOURCES.md). Logos identify providers and do not imply endorsement.

Generated firmware assets are committed, so Node.js is unnecessary for ordinary builds. To regenerate, install Node.js and `sharp` in an isolated development environment, then run `node scripts/generate_nova_assets.cjs`. Preserve logo source geometry and notices.

See [CONTRIBUTING.md](../CONTRIBUTING.md) and [SECURITY.md](../SECURITY.md).
