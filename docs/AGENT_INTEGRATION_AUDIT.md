# Agent integration audit

Date: 2026-10-15. Installed application and P4 firmware: v1.19.1-rc2.

## Finding

The installation does **not** establish working live agent monitoring for all three
providers. Quota readiness, numeric token activity, observed lifecycle events, USB
acknowledgment and permission control are independent capabilities.

| Capability | Codex | Claude Code | ZCode |
| --- | --- | --- | --- |
| Currently selected in installed host | Yes | No | Yes |
| Account quota previously physically verified | Yes | No | Yes |
| Lifecycle adapter in current source | Yes | Yes | No |
| Installed lifecycle opt-in | Enabled | Disabled | Unavailable |
| Eligible live records during this audit | 0 | 0 | Unavailable |
| Genuine client event through to physical agent view | Unproven | Unproven | Unsupported by this version |
| Production P4 tool approval | Disabled | Disabled | Disabled |

## Codex: delivery remains the unresolved boundary

The installed official CLI identifies itself as `0.162.0-alpha.17.2`. A new,
read-only `hooks/list` request returned all ten expected lifecycle events, enabled
and trusted, with no warnings. This establishes inventory and trust for that
diagnostic process, not hook execution in the active desktop conversation.

All ten commands use an older development Python interpreter outside the installed
application, with the installed `tools/aim_events.py` script. They differ from the
current packaged setup command, which uses `AI-Monitor-Events.exe`. Both referenced
files still exist. The old interpreter successfully handled isolated synthetic
events in 109–187 ms; this mismatch is a portability/dependency risk, **not a proven
cause of the missing real events**. Installed observer modules match current source.

The active generation contains no stored Codex lifecycle records. The hook file's
modification time is October 13; the observed desktop app-server process started
October 15. Consequently the previous hypothesis that this process simply predates
the hook file is not supported by the current evidence. Its inherited environment
and loaded per-thread configuration have not been established.

Do not overwrite hook trust or force-restart an active client. A follow-up delivery
check must observe a genuine, explicitly initiated client action, a resulting
fixed-schema local record, a correlated USB acknowledgment and the physical agent
view. A synthetic record in a temporary directory cannot establish those steps.
Review changed definitions through the client's normal hook trust interface.
See the [official Codex hook contract](https://learn.chatgpt.com/docs/hooks).

## Claude: adapter works in isolation, installation is not enabled

The installed Claude marker is disabled and Claude is absent from the host's
selected-provider health. Its isolated observer correctly produced WORKING,
WRITING and COMPLETED, retaining no supplied prompt or tool input. This does not
verify a real Claude session, subscription quota or physical lifecycle display.
Activation remains explicit. Tool authorization remains a separate disabled domain.
See the [Claude Code hook reference](https://code.claude.com/docs/en/hooks).

## ZCode: a supported source exists, but the adapter is missing

The [official ZCode hook documentation](https://zcode.z.ai/en/docs/hooks) describes
SessionStart, UserPromptSubmit, PreToolUse, PermissionRequest, PostToolUse,
PostToolUseFailure and Stop. Inputs provide snake_case aliases compatible with the
observer's basic event fields. Thus lack of a documented source is not a valid
reason to treat this integration as impossible.

However, ZCode is excluded from `live_events.SOURCES` and `aim_events` options;
there is no ZCode link/unlink flow, consent generation or setup readiness check.
Selecting ZCode supplies numeric activity and optional account quota only. The
device correctly labels it ACTIVITY ONLY.

A future adapter must use explicit user-level or plugin setup, preserve unrelated
configuration and hook enablement, emit no decisions/context, and bound input and
storage. ZCode's documented events do not establish per-subagent start/stop coverage.
Do not simply reuse Claude's settings: ZCode documents that legacy settings are
displayed but require explicit import. Project hook configuration is ignored.

## Monitoring gaps in the monitor itself

- `setup_report()` uses a Codex opt-in marker to say the link is enabled. It does not
  verify the currently loaded hook definition, executable availability or trust.
- Its `reporting` status means eligible local metadata exists; it does not prove
  that a genuine client emitted it or that the physical display received it.
- `Panel.report_tokens()` validates correlated live replies, but exports no live
  acknowledgment/error status to `HostStatus`. Live errors trigger a 30-second
  backoff while quota monitoring continues. The PC's quota-ready label therefore
  cannot reveal a failed live channel.
- Live sampling shares the background numeric reader. A stalled numeric source can
  postpone event collection. USB stays responsive and stale device state expires,
  but lifecycle delivery has no independent latency guarantee.
- Task hook metadata describes requested create/complete actions. It does not
  establish completed work, test success, confirmed task counts or tool approvals.

## Verification performed

Five added synthetic integration tests exercise the actual observer, background
sampler and serial-owner method together, using temporary configuration and a
correlated serial fixture. They cover live delivery without numeric data, discarded
private fields, disabled/unselected sources, stale worker samples, optional-live
timeouts and old firmware. The fresh full run passed **505 Python tests** in
42.502 seconds; all **four native UI CTest targets** passed. The Python log is
`work/verification/deep-agent-python.log`. Existing lifecycle and USB tests also pass.

The isolated process replay used the same older interpreter referenced by the
installed hooks. No fixture entered the installed activity directory or real USB
connection. No model turn, credential access, provider activation, hook trust edit,
firmware flash or installed-application replacement was performed for this audit.
The existing rc2 binaries are unchanged; the new regression tests and this report
do not require a firmware rebuild.
