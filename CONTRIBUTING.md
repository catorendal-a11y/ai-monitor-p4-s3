# Contributing

Use English for project code comments, UI, documentation, issues and pull requests. Keep changes focused and describe the concrete behavior.

## Development

1. Run `setup.ps1 -BuildTools` on Windows. Elsewhere run `sh setup.sh`, then install PlatformIO in the local .venv with `python -m pip install 'platformio>=6.1,<7'`.
2. Build with `python -m platformio run -e esp32p4-release` using this checkout's .venv.
3. Run `python -m unittest discover -s tests -p "test_*.py"`.
4. Run `python scripts/run_tests.py`; for UI changes also use `--ui` with GCC, CMake and Ninja installed.

Build first to download pinned ArduinoJson/LVGL. Native UI tests share firmware LVGL sources/configuration. Inspect screenshots for clipping, contrast and touch targets. State whether validation used mocks or physical hardware. Stop the companion before flashing and select an explicit port when multiple boards are present.

Keep LVGL/backlight mutations on the UI task. Preserve bounded parsing, frame correlation, partial writes, rollover-safe timing and compatibility. Test state transitions and avoid flash writes per render loop.

## Privacy and assets

Never include local configuration, auth files, keys, databases, conversations or runtime logs. Use synthetic provider responses and SQLite fixtures. Review screenshots/errors for private information.

Keep third-party copyright headers and licenses intact. Provider marks/fonts are not relicensed by MIT. Regenerate committed NOVA arrays only when assets change.

## Pull requests

Describe the problem, resulting behavior, tests and hardware-specific limits. Include screenshots for visual changes. Discuss broad protocol/hardware changes in an issue first. Use SECURITY.md for private vulnerability reports.
