# Local live provider events

The USB live domain now has opt-in Codex and Claude Code lifecycle observers. This is source-level
integration with synthetic validation, not a claim of physical USB operation or complete provider
coverage. The [device agent view](LIVE_AGENT_VIEW.md) now exists with native validation; physical
integration remains pending. Quota/token sources remain independent.

## Setup in the PC program

Save the selected provider, then choose **Link Codex session events** or **Link Claude session events**
in AI setup. A private backup is kept and existing hooks are preserved. Removing the link removes only
this installation's exact hook commands and invalidates its observation generation.

Codex uses the effective CODEX_HOME/hooks.json file and documented lifecycle hooks. The hook definition
must be reviewed/trusted in Codex's hook browser (CLI `/hooks`) before it runs; changed definitions
require review again. Do not bypass hook trust. Restart the session after linking. Installed-client
compatibility and genuine hook delivery remain validation gates; a saved link is not proof of delivery.

Claude Code uses its existing explicit observational hook setup. These hooks never return an approval,
denial, rewritten input, model context or continuation instruction. The Codex shell wrapper returns
only neutral `{}` JSON, including on observer failure, because Stop/SubagentStop expect JSON output.
The helper itself emits no content. There are no provider API calls or new model turns.

## Honest state mapping

| Reported event | Display metadata |
| --- | --- |
| SessionStart | IDLE |
| UserPromptSubmit, unclassified tool use, PostToolUse | UNKNOWN |
| PermissionRequest, supported Claude attention notification | WAITING |
| Codex apply_patch; Claude Edit/Write/MultiEdit | EDITING |
| Claude Grep/Glob/WebSearch | SEARCHING |
| Stop/SubagentStop | DONE: a turn stopped, not proof that a task or test succeeded |
| Claude StopFailure | FAILED |
| Codex Interrupt | IDLE |
| SessionEnd | Remove the parent session entry |

Shell commands are never inspected to guess BUILDING or TESTING. THINKING is not inferred from
token increases or an absence of tool events. Subagent start/stop records use separately hashed
identities; detailed tool attribution is unavailable when a hook only identifies the parent session.
UNKNOWN means the phase is not reported. Other providers have no live event observer yet.

Only a SHA-256 session identity, fixed state, local observation timestamp, schema and setup generation
are stored. Raw prompts, commands, messages, tool results and transcript paths are discarded. Records
are the most recently received observation, not a provider heartbeat or authoritative execution log.
Closed/stale/future-dated/invalid records are excluded. Source freshness is 30 seconds; a long tool call
without another event becomes unknown rather than appearing active forever.

The background worker reads only selected, enabled sources, scans bounded records and sends at most
eight agents. Waiting/failure observations have priority; this is not a total-agent count. Metadata
does not enter token commands, history or status exports. Worker samples older than ten seconds are
cleared. The host's serial owner negotiates live support, correlates replies and continues quota
monitoring if live telemetry times out. Serial I/O errors still reach the existing reconnect handler.
If USB disappears, the device's separate 30-second lease bounds retained display state.

References: [official Codex hooks](https://learn.chatgpt.com/docs/hooks),
[Claude Code hooks](https://code.claude.com/docs/en/hooks), [USB domain](USB_LIVE_TRANSPORT.md).
