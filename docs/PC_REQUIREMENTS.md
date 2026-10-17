# PC requirements and included components

Download the **AI-Monitor-Setup** EXE from [Releases](https://github.com/catorendal-a11y/ai-monitor-p4-s3/releases/latest) for normal Windows setup. It includes Python/Qt, serial support, the flasher, runtime DLLs and prebuilt firmware for both supported boards. Choose your board, USB port and AIs in the app.

| Installation route | What you prepare |
| --- | --- |
| Windows installer | Windows x64, a USB data cable and display. No separate Python, Node.js, Git, PlatformIO or Arduino IDE setup. |
| Windows portable ZIP | Same requirements; extract the entire folder and keep `_internal`, firmware and executables together. |
| Terminal dashboard | Python 3.12 x64 (3.10+ supported), internet for initial pinned dependencies, then `setup.ps1` and `AI-Monitor-Terminal.bat` in the complete extracted package. [Install/start guide](TERMINAL.md#install-on-windows). No terminal EXE or firmware rebuild is needed. |
| Source code | Python 3.10+. The source script installs host/GUI dependencies into `.venv`. A source ZIP has no prebuilt firmware; use the release or build it. |
| Firmware development | Additional tools in [Development](DEVELOPMENT.md); normal Windows-release users do not need them. |

Use updated Windows 10/11 for the monitor. Windows 11 is recommended for Codex; OpenAI documents updated Windows 10 as best effort with version 1809 or later for console support. See [Codex Windows support](https://learn.chatgpt.com/docs/windows/windows-sandbox).

## AI choices

| AI | Setup for this integration |
| --- | --- |
| Codex | The app offers official standalone CLI installation if missing and your own browser sign-in. No monitor API key. [Fresh-PC guide](CODEX_SETUP.md). |
| ZCode | Use its client for local activity. Add your own Z.AI coding-plan key in the masked field for quota; the key is optional for activity-only use. |
| Claude Code | Use the official client. The app offers an optional quota statusline link and preserves custom statuslines. |
| Gemini CLI / OpenCode | Their clients produce local numeric activity. Remaining account quota is unavailable in these monitor integrations. |
| Copilot / Cursor / Antigravity | Advanced numeric bridge required. Selecting a name alone does not install/connect the editor. [Bridge guide](PROVIDERS.md#external-numeric-bridge). |

Internet is needed for initial downloads, sign-in and account quota endpoints. Token records are local to the PC. A USB display connection does not make account quota an offline service. No provider/account/key is included or preselected.

## USB and Windows trust

Use a data-capable cable and the correct connector: P4 USB data; original Waveshare S3 USB TO UART. If no COM port appears, check the cable/connector and the manufacturer's driver. With several matching devices, choose the explicit display port; automatic mode does not guess.

S3 remains experimental and unverified on physical hardware. The monitor EXEs are currently unsigned, so SmartScreen can warn about an unknown publisher. Keep protection enabled; see [Windows trust](WINDOWS_TRUST.md).
