# Connection checklist, history and session states

## Check that your selected AI works

Save your board, USB port and providers, then open **AI setup > Check AI setup**.
The checklist separates local activity, account quota, USB delivery and optional session events.
Readable records establish a baseline; they do not prove that a new turn was observed.
Quota received means the running host last reported success, not that every account supports quota.

Use **Observe for 60 seconds**, then perform a normal turn in your selected client.
The monitor sends no model request. It reports new counter increases and, with compatible firmware,
whether the display echoed that activity source. USB connection alone does not prove token delivery.
If the first record establishes its baseline, perform another normal turn to test an increase.
**Open selected guide** takes you to that provider's instructions in the app.

Codex uses the official client/account setup. ZCode quota requires your own Z.AI Coding Plan key.
Gemini and OpenCode report local activity without remaining account quota. Copilot, Cursor and
Antigravity require an external numeric bridge. These limitations remain visible in the checklist.

## Optional local history

Open **Host settings**, enable **Keep local numeric usage history**, save and start the host.
Collection is off on new installations. **History** lets you choose an AI and a 7- or 30-day view,
switch between daily observed token increases and quota observations, and export numeric CSV.
Turning collection off preserves existing history but stops queuing new observations.

The host stores observed counter increases and numeric quota snapshots in `tools/activity/history.db`
for up to 30 days. No prompts, conversations, account IDs or credentials are stored there.
Missing periods mean no observations, not zero usage. Imported records and the initial baseline
are not counted as new work. The quota view/export includes the latest 256 observations per AI.
The host can collect readable local token increases while the display is disconnected; account
quota collection still follows the normal connected polling cycle.

An estimate needs at least three fresh increasing quota samples over two minutes in the same
window, collection epoch and reset cycle. A decrease, long gap, restart/configuration change or
reset invalidates the previous pace. If the window resets before its estimated limit, the app
says so. Estimates are not billing totals or promises about when a provider blocks access.
Storage/queue failures are reported; the app never replaces an unfamiliar database.

## Claude Code session events

Save Claude Code as a selected provider. In **AI setup**, choose its guide and click
**Link Claude session events**. Review the confirmation, then restart Claude Code.
This explicitly adds observational command hooks while preserving other hooks and custom statuslines.
It is separate from **Link Claude quota**, which handles subscription windows.

The desktop and updated display can show **Working**, **Needs you**, **Turn complete** and
**Session error** from documented Claude events. NOVA and ORBIT both use these states.
**Turn complete** means a response ended; it does not assert the entire task is finished.
Only selected providers contribute. Without fresh events, normal token/quota behavior resumes.
Running/waiting records expire after 15 minutes; terminal states after 30 seconds.
Events report the latest session state, not a complete inventory of concurrently running tools.

The bundled `AI-Monitor-Events.exe` helper starts directly from its small `event-runtime` folder;
keep the complete installation together. It retains only an allowed state, receipt time and hashed session ID from hook input.
It suppresses output, always exits successfully, never approves permissions, and opens no network
listener. Claude's global `disableAllHooks` setting is preserved and reported instead of bypassed.
**Remove session events** removes this installation's own hooks and invalidates previous events.
Local numeric records remain private under `tools/activity`; they are never release assets.

Session events support **Claude Code only**. Codex, ZCode and the other providers continue to use
recorded token activity until a documented compatible event integration is added.

Primary references: [Claude hooks](https://code.claude.com/docs/en/hooks) and
[hooks guide](https://code.claude.com/docs/en/hooks-guide).
