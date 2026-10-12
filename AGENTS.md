# AI Monitor P4 development

## Architecture

- `src/main.cpp`: task startup and UI loop.
- `src/ai_monitor/`: bounded AIM1/JSON protocol, snapshots and USB receiver.
- Hardware initialization: inspect display/touch sources before changing board pins.
- `src/dashboard.cpp`, `src/ui_nova.cpp`, `src/ui_usage_details.cpp`, `src/ui_settings.cpp`, `src/ui_notifications.cpp`: LVGL screens/interactions.
- `src/ui/`: state/format/history helpers, theme and generated assets.
- `src/app_settings.*`: validated NVS settings/save feedback.
- `tools/aim_host.py`: polling, retries, config and USB companion.
- `tools/token_activity.py`: read-only numeric token activity.
- `tools/aim_control.py`: console setup, scoped host controls and verified firmware installation.
- `tools/aim_events.py`: small, silent, explicitly enabled Claude event observer; no model, host or serial control.
- `tools/aim_desktop.py`, `tools/desktop_window.py`, `tools/desktop_support.py`: graphical NOVA control panel and validated actions. Qt mutations stay on the main thread; blocking actions use one worker.
- Desktop tests use an offscreen Qt window with synthetic configuration, without provider requests or hardware writes.
- `scripts/build_windows_release.py`: portable executables, source/notice export and release ZIP.
- `assets/nova/`, `assets/orbit/`: original companion SVGs and logo attribution; generated transparent RGB565+A8 frames.
- `src/ui/theme.h`: four runtime palettes, applied to registered screens and overlays on the UI task.
- `tests/`: synthetic Python/protocol/settings/native UI regressions.

## Commands

Use `.venv\Scripts\python.exe` on Windows or `.venv/bin/python` elsewhere.

Read `docs/PROVIDER_ROADMAP.md` before adding providers. `tools/codex_support.py` prepares the official client only when a user explicitly selects Codex and accepts installation/sign-in. Its account RPC path reads quota without starting model turns. Test onboarding using subprocess fixtures; never log into a real account during development.

Install `scripts/requirements-test.txt` for the workflow permission regression tests. Read `docs/GITHUB_SECURITY.md` before changing workflow permissions or release publishing; build jobs must never receive repository write access.

```text
python -m platformio run -e esp32p4-release
python -m unittest discover -s tests -p "test_*.py"
python scripts/run_tests.py
python scripts/run_tests.py --ui --screenshots work/ui-previews
```

Build first to install pinned ArduinoJson/LVGL. Native tests need C++17; UI also needs C compiler, CMake and Ninja. Use `--cxx`/`--cc` for paths. Flash only when requested, after stopping the companion, using the identified upload port.
Use `setup.ps1 -BuildTools` for development; default setup installs host dependencies only. Source and portable release archives serve different users. Never copy private configurations or recursively export a live project into a release.

## Rules

- English in project-owned code, documentation and UI.
- UI-task ownership for LVGL/backlight mutations; safe snapshot publication.
- Bounded buffers, strict JSON type validation, frame correlation and partial writes.
- Rollover-safe timing; no repeated NVS writes/redraws for unchanged state.
- Local token increases are activity, not billing or streaming. Dimming does not prove inactivity.
- Test transitions and inspect UI output. Mocks do not establish physical hardware validation.
- Do not read/print real credentials or conversations for debugging; use synthetic fixtures.
- Never add keys, local configs, databases, logs, shortcuts or binaries to Git.
- Preserve bundled license texts byte-for-byte and attribution. MIT grants no trademark rights.
- Check this project is the Git root before mutations; never stage/commit from a parent/global repository.
