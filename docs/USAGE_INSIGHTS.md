# Connection checklist, history and session states

## Check that your selected AI works

Save your board, USB port and providers in **Settings > Edit settings**, then open
**Agents > Check AI setup**.
The checklist separates local activity, account quota, USB delivery and optional session events.
Readable records establish a baseline; they do not prove that a new turn was observed.
Quota received means the running host last reported success, not that every account supports quota.

Perform a normal turn in your selected client, wait for its local numeric record, then press **R**
and run **Check AI setup** again. The monitor sends no model request. It reports new counter increases
and, with compatible firmware, whether the display acknowledged that activity source. USB connection
alone does not prove token delivery. If the first record establishes its baseline, perform another
normal turn to test an increase. Provider instructions remain visible on the Agents page.

Codex uses the official client/account setup. ZCode quota requires your own Z.AI Coding Plan key.
Gemini and OpenCode report local activity without remaining account quota. Copilot, Cursor and
Antigravity require an external numeric bridge. These limitations remain visible in the checklist.

## Optional local history

Open **Settings > Edit settings**, enable **Usage History**, save and start the host.
Collection is off on new installations. **History > 7 / 30 day report** lets you choose the
date range and shows available provider, token, quota and observed-agent metrics together;
**Export CSV** writes the selected date range.
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

Save Claude Code as a selected provider. Open **Agents > Provider events**, choose Claude Code,
leave Remove off, review the confirmation and type `LINK`, then restart Claude Code.
This explicitly adds observational command hooks while preserving other hooks and custom statuslines.
It is separate from **Link Claude quota**, which handles subscription windows.

The terminal and updated display can show **Working**, **Needs you**, **Turn complete** and
**Session error** from documented Claude events. NOVA and ORBIT both use these states.
**Turn complete** means a response ended; it does not assert the entire task is finished.
Only selected providers contribute. Without fresh events, normal token/quota behavior resumes.
Running/waiting records expire after 15 minutes; terminal states after 30 seconds.
Events report the latest session state, not a complete inventory of concurrently running tools.

The owned hook invokes the packaged Python event adapter from the extracted NOVA folder. Keep the
complete installation together. It retains only an allowed state, receipt time and hashed session ID
from hook input. It suppresses output, always exits successfully, never approves permissions, and opens no network
listener. Claude's global `disableAllHooks` setting is preserved and reported instead of bypassed.
Run **Agents > Provider events** with Remove enabled to remove this installation's own hooks and
invalidate previous events.
Local numeric records remain private under `tools/activity`; they are never release assets.

Observed session events support Claude Code, Codex and ZCode through separate opt-in adapters.
Provider support differs, and missing/stale events remain unknown. Other providers continue to use
recorded token activity until a documented compatible event integration is added.

Primary references: [Claude hooks](https://code.claude.com/docs/en/hooks) and
[hooks guide](https://code.claude.com/docs/en/hooks-guide).
