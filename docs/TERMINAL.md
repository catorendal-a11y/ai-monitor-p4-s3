# AI Monitor Terminal

A real Windows terminal companion with Overview, Agents, History, Device and
Settings pages. It reuses existing local metadata without provider requests,
model turns, history writes, extra serial ownership or host lifecycle changes.

Run `AI-Monitor-Terminal.exe` in Windows Terminal or double-click it. Keep the
normal AI Monitor host running. The standalone program automatically finds the
existing per-user installation. Use `--root "C:\path\to\AI Monitor"` to select
another installation explicitly. The terminal does not configure or start a host.

From source, install `tools/requirements.txt`, then run `AI-Monitor-Terminal.bat`
or `.venv\Scripts\python.exe tools/aim_terminal.py --root "C:\path\to\AI Monitor"`.
The source launcher uses its own configured project when present, then the existing
per-user installation. No configuration or credentials are copied into a release.

Keys: **1–5** change page, **Tab** moves focus, arrows and **PageUp/PageDown**
scroll, **R** reloads local metadata, **?** toggles help, **Esc** closes help and
**Q** exits. Mouse selection works on the tabs. Narrow windows stack the overview
panels vertically; content remains scrollable.

Quota percentages come from the optional local numeric history and are always
labeled **Recorded**, with their age and window. They are not fresh API receipts.
When history is off or a quota was not recorded today, the value is unknown.
Provider health is separate from a recorded percentage. Agents contains only
observer metadata: a short opaque ID, reported state, elapsed time and event age.
States older than 30 seconds say **Last**. Selecting a provider creates no agent.
Elapsed run time includes waiting and is not active time. Unknown history gaps
stay unknown. Device identity is the last observation held by the existing host;
its observation age is displayed. Credentials and conversations are never shown.

Settings is a read-only summary. Use the existing desktop app to change settings,
credentials, consent, integrations or host lifecycle. Closing this terminal leaves
the host and firmware untouched. No firmware update is required for this companion.

Build a standalone executable and ZIP using:

```powershell
.\.venv\Scripts\python.exe scripts/build_terminal.py --output outputs/terminal-v1.19.1-rc11
```

Use a new output directory for a subsequent build. The bundle includes source,
license notices and hashes. `AI-Monitor-Terminal.exe --check` runs a synthetic
headless smoke test without accessing the user's configuration or device.
The normal Windows release builder also includes this terminal in future builds.
