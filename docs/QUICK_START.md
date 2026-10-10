# Download, connect, run

## Recommended: Windows installer

Use Windows 10/11 x64, a **GUITION JC4880P433 ESP32-P4** or **original Waveshare ESP32-S3-Touch-LCD-4.3** display and a USB data cable. S3 support is experimental and unverified on physical hardware; use its **USB TO UART** connector. [Check your board](BOARDS.md). No Python, PlatformIO, Node.js or Git installation is needed for this package.

The release includes its runtime and prebuilt firmware. For Codex, Windows 11 is recommended; updated Windows 10 is best effort and needs version 1809 or later for console support. You do not need Codex CLI in advance: **AI setup > Install / sign in Codex** offers the standalone installer and browser sign-in. [Included components and PC requirements](PC_REQUIREMENTS.md) · [Codex without an existing CLI](CODEX_SETUP.md).

1. Open **Releases** and download **AI-Monitor-Setup-v1.18.3-windows.exe**. It installs the complete app for your user and opens setup. No administrator access or separate Python installation is required. The release is unsigned; [read the Windows trust notes](WINDOWS_TRUST.md) if SmartScreen warns.
2. For a portable installation instead, download **ai-monitor-p4-v1.18.3-windows.zip** and use **Extract All**. Keep the entire folder, including **_internal**, together. Do not run inside the ZIP. GitHub's **Source code (zip)** contains no ready-to-run programs.
3. Connect the screen's USB data port and double-click **AI-Monitor.exe**.
4. In **Setup**, choose your exact board and USB port. Open **AI setup** to choose your providers. Read the visible instructions for each AI. Codex offers official CLI setup/sign-in; ZCode quota needs your own Z.AI Coding Plan key in the masked field. Without that key, ZCode can still report local activity. Click **Save settings**. A blank key field preserves the saved key; **Clear saved key** removes it. Neither board nor AI is preselected on a fresh installation.
5. For a new board, open **Firmware > Install / update firmware** and choose **First installation**. Review the board/port and type `FLASH`. This resets display settings. For an existing AI Monitor, choose **Update this project's existing installation** to retain settings and enable the new quota selector/large alerts. A new S3 board needs its own factory installation. Progress and errors remain in **Activity**; keep the app and power connected until it finishes.
6. Leave **Start the host after a successful firmware installation** checked, or click **Start host** afterward. Once running, close the window and keep the display connected. By default the host stays invisible until Stop host, sign-out or shutdown. Host settings can change what closing the app does.

**Check AI setup** reports readable local token sources, the running host's last quota result and the next action for each selected AI. It does not generate model requests.

| Selected AI | What setup checks and explains |
| --- | --- |
| Codex | Whether the official CLI is available and whether the running host last received quota. Use **Install / sign in Codex** for official setup; detecting a CLI alone does not verify sign-in. |
| ZCode | Whether a key is saved or provided by `ZAI_API_KEY`, separately from quota the host last received. An empty environment override prevents use of a saved key. Check **Host log** for account errors. |
| Claude Code | Whether this installation's quota link is installed. **Link Claude quota** preserves custom statuslines; restart Claude Code afterward. Removal is also available. |
| Gemini CLI / OpenCode | This integration reports LOCAL activity; remaining account quota is unavailable here. OpenCode needs no monitor script or key for its supported local database. |
| Copilot / Cursor / Antigravity | A numeric bridge must forward counters with `AI-Monitor-Console.exe --ingest PROVIDER`. Selecting the AI alone does not import editor activity. See the [provider guide](PROVIDERS.md#external-numeric-bridge). |

When you choose Codex, setup offers the official CLI installer and its sign-in flow automatically when needed. Accept the offered steps with your own account; [Codex setup guide](CODEX_SETUP.md). Desktop-app login alone may not supply the CLI login file used by this companion. Setup never asks for your OpenAI password or copies login credentials. ZCode quota requires your own Z.AI coding-plan key; ZCode's encrypted login is not imported. See [provider configuration](../README.md#provider-setup).

**More than one USB board connected?** Choose the display's explicit COM port instead of `auto`, save settings, then start the host. Automatic detection deliberately refuses to guess between matching devices. A running background process alone does not mean USB is connected; check **Host log** for `connected to ...` and acknowledged frames. If no matching device is connected yet, the host can wait for it.

**Moving from a source or portable folder to the installer?** Each folder keeps its own private configuration. Choose your board, providers and port in the installed app, and add your own ZCode key there if you need quota. An existing key in another folder is not imported automatically.

## Personalize the display

Tap **SET**, then **APPEARANCE**. Select NOVA or ORBIT and a Forest/Ocean/Amethyst/Ember theme. Use DONE, then BACK. Choices are stored on the display and survive application updates/reboots. A first factory installation resets device settings. If SAVE FAILED appears, the selection is temporary; retry before restarting.

## Everyday use

For first-time setup, use the **SETUP PROGRESS** checklist and **Next** button. It leads to missing board/USB/AI choices, then saving and checking the display. Start is disabled while selections are missing, ambiguous or unsaved. If the display does not respond, the next step opens firmware/USB help; review the actual board and port before choosing First installation. The app never flashes automatically.

For NOVA/ORBIT percentages, open **SET > AI USAGE**. Select an AI with PREV/NEXT, then its window. Each option shows remaining quota and data status; the page includes provider setup instructions. Codex has **5 HOURS / 7 DAYS**. ZCode can report **5 HOURS / 7 DAYS** for models and **MONTHLY MCP** for tool calls. Monthly MCP is not a monthly token budget. Known missing windows can be selected, but show **NOT REPORTED** until real data arrives. **AUTO / MOST URGENT** follows the most urgent quota. **REFRESH** reloads available options and requests a host update. Each AI's choice is saved independently; activity-only providers keep LOCAL and alerts still monitor all windows.

Double-click **AI-Monitor.exe**, click **Start host**, then close the window. Use **Stop host** before flashing. The **Activity** and **Host log** tabs show connection messages. The NOVA caption reports readable local token sources; it does not invent activity.

Minimize the app to its **NOVA system tray icon** near the clock; Windows may put it under the **^** overflow arrow. Click the icon or open the shortcut again to restore the existing window. Right-click for **Open AI Monitor**, **Start host**, **Stop host** and **Quit**. The Quit label explains whether your host will keep running or stop. **Ctrl+Q** also quits.

In **Host settings**, **Minimize to tray** is on by default. **Close button hides the app in the system tray** is optional and off by default; otherwise X quits the app using your keep/stop-host preference. Hiding keeps unsaved fields intact and never stops the host. Without a working system tray the app retains normal window controls. No firmware update is needed for tray support on an existing v1.17.2 display.

For firmware upgrades, open **Firmware**, then select **Update this project's existing installation**. This writes the application and retains settings only when the board already uses this project's partition layout. For a different project's firmware, use First installation.

Copy the new package into a new folder, stop the old host, and run setup in the new folder. If desired, copy your private `tools/aim_host.json` from the old folder into the new one before setup. Do not share this file. The portable package cannot automatically stop hosts belonging to a different extracted folder.

## Downloaded the source ZIP instead?

Source code needs **Python 3.10+** and internet access for first setup. On Windows, install Python from [python.org](https://www.python.org/downloads/windows/), extract the source ZIP and double-click **AI-Monitor.bat**. It creates `.venv`, installs the host/Qt dependencies and opens the same graphical app. Existing local configuration is preserved. Source ZIPs contain no prebuilt firmware or portable executables; use the Windows release for firmware installation, or the [developer guide](DEVELOPMENT.md) to build it.

On Linux/macOS:

```sh
sh setup.sh
.venv/bin/python tools/aim_control.py
```

The source menu can configure and start/stop the companion. A Windows portable package runs on Windows only. Building firmware and setting serial permissions on Linux/macOS are covered in the [developer guide](DEVELOPMENT.md).

## If something does not work

| Symptom | What to do |
| --- | --- |
| Connected display does not match selected board | Open First-time setup and select the actual model. P4 and S3 use separate firmware. |
| S3 screen looks darker but LEDs stay bright | Intermediate brightness is visual attenuation; only zero switches the original S3 backlight off. |
| Desktop runtime could not load | Extract the complete ZIP into a new folder; keep _internal beside AI-Monitor.exe. Do not copy the EXE alone. |
| Flasher closes when double-clicked | Open AI-Monitor.exe > Firmware. The new helper explains this and offers to open the Firmware tab. |
| Windows says unknown publisher | This release is unsigned. Keep Windows protection enabled; see WINDOWS_TRUST.md. |
| No USB port | Use a data-capable cable, the board's USB data port, and reconnect. Close other serial tools. |
| Several COM ports | Unplug the display, reopen setup and compare the list after reconnecting. Select its numbered port explicitly. |
| Codex quota unavailable | Use **AI setup > Install / sign in Codex** (or sign in with the CLI), then start the host and read **Host settings > Live provider health**. Quota needs a ChatGPT-backed login; API-key-only mode has no plan quota. |
| ZCode quota unavailable | Save your Z.AI coding-plan key, start the host, then read **Host settings > Live provider health**. Check **Host log** for the error. Replace a wrong or expired key; for rate limiting, allow the host's automatic backoff to retry. Leave the key empty if you do not need ZCode quota. |
| NOVA does not react immediately | Counters may update when model requests finish. Status lists readable token sources. Quota polling is a separate signal. |
| Checksum or missing-flasher message | Extract the complete release ZIP again; keep the executables, firmware and manifest together. |
| Firmware connection fails | Stop the host, close serial monitors, check the chosen port, then retry. If normal upload cannot connect, follow the board's BOOT/RESET instructions. |
| Source setup cannot find Python | Use the portable Windows release, or install Python 3.10+ and retry AI-Monitor.bat. |

The host log is local at `tools/aim_host.log`. Never post keys, authentication files or unredacted private data in issues.

## Connection checks and host preferences

Use **Check connection** after saving the exact board and USB port. It reads the existing AI Monitor identity without flashing or requesting quota. A factory demo needs firmware installation first. With a running host, the app uses its fresh health report; stop the host to probe an unconfirmed connection.

The sidebar distinguishes **USB CONNECTED**, **USB RECONNECTING**, **WAITING FOR USB SELECTION**, and a running process with **USB STATUS UNCONFIRMED**. An ACK proves that the display received a frame; it does not prove that Codex or ZCode reported quota. **Host settings > Live provider health** shows this separately. Use Host log and Provider setup for account errors.

| Host setting | Range/default | Effect |
| --- | --- | --- |
| Retry USB connection | 2–60 seconds / 5 | How soon the host retries a missing or disconnected display. |
| Read local token activity | 2–15 seconds / 2 | Read-only numeric activity scanning, independent of quota polling. |
| Terminal text size | 10–18 pt / 10 | Larger desktop activity/log text. |
| Start host when app opens | Off | Opt-in background start after saved setup is validated; no Windows sign-in task. |
| Keep host when I quit | On | Turn off to stop this installation's host when you quit. Hiding in the tray keeps it running. |
| Minimize to the NOVA tray icon | On | Minimize hides the app near the clock; its shortcut restores the same window. |
| Close button hides in tray | Off | Turn on to make X hide the app. Use the tray's Quit action or Ctrl+Q to exit. |

Click **Save settings** to apply preferences. Quota refresh remains 15–240 seconds in AI setup, with separate provider backoff on failures/rate limiting. Reading status does not generate prompts or consume model tokens.

An invalid configuration no longer prevents opening the app. **Host settings > Recover invalid settings** offers an explicit reset and keeps a private `tools/aim_host.invalid-*.json` backup. Re-enter the board/providers/key after recovery; keep the backup private. Updating an installer preserves valid configuration and never imports credentials from an unrelated portable folder.
