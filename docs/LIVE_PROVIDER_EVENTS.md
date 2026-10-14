# Local live provider events

The USB live domain now has opt-in Codex and Claude Code lifecycle observers. This is source-level
integration with synthetic validation, not a claim of physical USB operation or complete provider
coverage. The [device agent view](LIVE_AGENT_VIEW.md) now exists with native validation; normal P4 USB operation has been physically verified. Real client delivery remains a separate gate. Quota/token sources remain independent.

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
| UserPromptSubmit, unclassified tool use, PostToolUse | WORKING (reported lifecycle, no guessed detailed phase) |
| PermissionRequest, supported Claude attention notification | WAITING |
| Codex apply_patch; Claude Edit/MultiEdit | EDITING |
| Claude Write / Read / WebFetch | WRITING / READING |
| Claude Bash / PowerShell | RUNNING, without inspecting command text |
| Claude Grep/Glob/WebSearch | SEARCHING |
| Stop/SubagentStop | COMPLETED: response/agent ended, not proof that a build or task succeeded |
| Claude StopFailure / PostToolUseFailure | ERROR; interrupted tool failure becomes IDLE |
| Claude PermissionDenied | NEEDS_ATTENTION; auto-mode denial observation, never an approval/retry |
| Claude TeammateIdle | IDLE for the identified teammate, preserving the parent |
| Claude TaskCreated / TaskCompleted | Separate bounded create/complete-request metadata, not confirmed task success |
| Codex Interrupt | IDLE |
| SessionEnd | Remove the parent session entry |

Shell commands are never inspected to guess BUILDING or TESTING. THINKING is not inferred from
token increases or an absence of tool events. Subagent start/stop records use separately hashed
identities; detailed tool attribution is unavailable when a hook only identifies the parent session.
UNKNOWN means the phase is not reported. Other providers have no live event observer yet.

Only a SHA-256 actor identity, fixed state, observation timestamp, optional observed start/finish
timestamps, schema and setup generation are stored. Raw prompts, commands, messages, tool results and transcript paths are discarded. Records
are the most recently received observation, not a provider heartbeat or authoritative execution log.
Closed/stale/future-dated/invalid records are excluded. Ongoing observations expire after 15 minutes;
terminal/idle states expire after 30 seconds. The agent screen shows last-event age explicitly.
NOVA reacts only to source observations no older than 30 seconds. Sending a fresh USB packet never
renews the source timestamp or proves that a quiet client is alive.

The background worker reads only selected, enabled sources, scans bounded records and sends at most
eight agents. Waiting/failure observations have priority; this is not a total-agent count. Metadata
does not enter token commands, history or status exports. Worker samples older than ten seconds are
cleared. The host's serial owner negotiates live support, correlates replies and continues quota
monitoring if live telemetry times out. Serial I/O errors still reach the existing reconnect handler.
If USB disappears, the device's separate 30-second lease bounds retained display state.

References: [official Codex hooks](https://learn.chatgpt.com/docs/hooks),
[Claude Code hooks](https://code.claude.com/docs/en/hooks), [USB domain](USB_LIVE_TRANSPORT.md).

## Observed session timing

A UserPromptSubmit or SubagentStart event starts a timer. Tool events preserve that start.
Stop/SubagentStop/StopFailure/Interrupt/SessionEnd/TeammateIdle freeze a known timer; a new prompt
starts a new turn timer. Without an observed start, the UI says start unknown. No token-derived
start time or inferred task progress is used. Durations are bounded to seven days and wall-clock
rollback is rejected. Same-provider updates use a bounded local file lock so concurrent hook
processes cannot overwrite a newer event. No network listener or new dependency is introduced.

Claude task hooks run before other handlers can veto; their separate records therefore say
TASK_CREATE_REQUESTED / TASK_COMPLETE_REQUESTED. They never increment confirmed task-success
counts or replace the parent agent phase. Titles/descriptions are discarded.

Firmware advertises `liveMetadata: 2`. The host sends optional elapsed/last-observed seconds only
to that capability, and downgrades state names plus removes timing for older firmware. USB/AIM1
quota messages, permission authority and source records stay separate.

## Local Codex diagnostic checkpoint

The installed official client's read-only `hooks/list` RPC reported all ten current user hooks
trusted and enabled, without warnings. The observer's neutral no-op wrapper completed in 250 ms.
The running desktop app-server predates the hook installation. An old loaded configuration is a
possible explanation for missing events, not a confirmed root cause; a fresh inventory does not
prove that a running conversation delivers events. No hook trust, permission settings, transcripts
or model sessions were modified for this check. The monitor does not force-restart other agents.
