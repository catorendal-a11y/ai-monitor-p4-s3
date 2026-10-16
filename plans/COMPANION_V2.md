# AI Monitor v2: physical AI agent companion and monitor

The user's updated repository review supersedes the earlier construction order. Inspect current
main and the working tree before changes; preserve existing verified work and the mature USB/AIM1
system. Keep English code, UI and documentation. Push/release readiness is not established by
a local build or mock. Do not claim complete integration without its physical exit gates.

## Product and architecture invariants

Production transport is the existing PC host's USB/AIM1 connection to the device. No second
production transport or C6 runtime dependency is planned. Do not add wireless transport, network
listeners, cloud accounts, a web dashboard, camera, voice assistant, transcripts or remote shell.
Historical C6 measurements remain optional developer diagnostics: detected chip, host/slave versions,
the earlier controller RPC test and compatibility information. C6 failure cannot affect product features.

Keep quota/provider views, token activity, live agents, permissions, companion rendering, history
and USB transport separate. Carrying them over USB does not merge their state structures.
aim::Snapshot keeps quota/views, token activity, host health and refresh state. Existing session
counts must move to agent::Snapshot before further agent features grow. The legacy ClaudeLiveProto
remains tested reference code; do not expand it or make new production systems depend on it.

Use only documented/reviewed sources. Tokens do not establish a phase or start time. Unsupported
states, source gaps and missing metrics stay unknown. No invented percentages or billing.
LVGL/backlight/NVS remain UI-task owned. Buffers, queues, messages, parsers, manifests and transfers
have strict type, size and timeout limits. No credentials, prompts or transcripts in Git/history/logs.
Every major new subsystem gets synthetic/native tests before physical integration.

## Verified foundations: reuse these

USB/AIM1, quota/token tracking and PC history already exist. Claude observational hooks exist;
the new local Codex/Claude lifecycle adapters, read-only USB metadata channel and agent/provider
screen have synthetic/native validation. The correct AI Monitor Windows app is now locally rebuilt;
real client compatibility remains a separate gate. Provider-status rows are not fabricated agents.

NOVA/ORBIT union-alpha cropping saved 23.8%. P4 physically validated LZ4 across twelve poses
(about 520 KB encoded payload), verified PSRAM cache allocation/decode/hash behavior and physically
benchmarked PPA rotation. The generic renderer and cache ownership/fallback foundation exist.
Do not repeat codec research. Built-ins remain safe fallback.

The permission controller/UI have native-tested fixed controls, 1.8-second continuous hold,
drag/read-failure cancellation, full visibility/prompt identity checks, single-use decisions and final
commit gates. Preserve these. Real permission transmission remains disabled until phase 7 is validated.
See docs/V2_VALIDATION.md for dated evidence and limits; previous main CI success does not prove
the current local changes have passed CI.

## Phase 1: roadmap cleanup

Replace the earlier transport/dependency assumptions with USB-only architecture, including
permission control, packs, release planning and UI notes. Keep historical radio test results as
developer evidence only. Do not spend new v2 effort on radio bring-up. Remove obsolete active
integration plans rather than retaining them behind a misleading current checkpoint.

## Phase 2: agent domain cleanup

Move all session counts/status out of aim::Snapshot into agent::Snapshot with independent
publication/revision/expiry. Preserve the existing session_activity wire command as compatibility
where needed without retaining its state in the quota object. Add a generic AgentActivity/event model.

Supported semantic states: IDLE, WORKING, THINKING, READING, SEARCHING, EDITING, WRITING, RUNNING,
BUILDING, TESTING, WAITING, NEEDS_ATTENTION, ERROR and COMPLETED, plus UNKNOWN when information
is missing. Detailed phases require explicit trusted-source events. Legacy wire names must be mapped
explicitly, not silently relabeled as evidence. Test native transitions, leases, reconnect and
compatibility before updating UI consumers. Preserve quota/token functionality throughout.

## Phase 3: production LZ4 companions

Move normal NOVA/ORBIT rendering toward verified compressed LZ4 assets, PSRAM cache,
CompanionRenderer and LVGL. Retain a safe built-in fallback chain; allocate bounded pools at boot
and respect image lifetime/fencing. Measure actual built firmware/app size, free application space,
boot time, PSRAM/internal heap and largest blocks, frame-switch latency and UI responsiveness.
A codec payload estimate is not a built-firmware saving. Do not prioritize microSD; first measure
internal storage and real pack requirements. External storage stays optional future work.

## Phase 4: documented Claude events and timers

Expand observational hook support where documented: PostToolUseFailure, SubagentStart/Stop,
TaskCreated/Completed, PermissionDenied and TeammateIdle, alongside current lifecycle events.
Normalize fixed events without retaining their text/arguments/results. No observational hook may
authorize a tool, modify inputs, execute a command or return model context.

Track session start/active duration only from reliable events; gaps remain unknown. A stopped
turn is not proof of task/test success. Add bounded task lifecycle events (created, started, progress,
completed, failed, cancelled); only show structured source milestones, never guessed percentages.

## Phase 5: multi-agent UX and companion reactions

Expand the current screen to reliable per-agent/session state and timers, with fixed navigation and
honest source readiness. The current provider-status fallback is distinct from live sessions.
React to actual agent start/wait/attention, tests, task success/error and quota warnings.
Home is event-driven: normal companion/usage/activity, permission priority, temporary success,
error/attention and a clean idle state. Avoid permanent card clutter and unsupported classifications.

## Phase 6: notifications and timeline

Create bounded, deduplicated, expiring events for attention, completion, failures, quota warnings,
host disconnect, pack and storage errors. Notifications carry type, source/provider, timestamp,
severity, short safe text and read/unread. Timeline is structured event history, never conversation
history. Do not persist sensitive permission hints. Keep existing quota notifications working.

## Phase 7: explicit Claude permission control over USB

Checkpoint: generic interaction/UI dependency cleanup, dedicated helper, current-user Windows
IPC and bounded host broker/service are implemented with synthetic/native tests. The service
now has explicit Panel-owner lifecycle hooks, persistent host-instance replay protection and
safe shutdown, but is not enabled by production startup. A tested bounded UI-to-serial handoff
requires an actual PermissionView commit and fresh local visibility. ESP task synchronization,
UI publication and immediate final transmission are connected in a developer-only P4 target,
with atomic cancellation and no opt-in at boot. Normal production builds remain disabled.
Physical authenticated USB enrollment,
permission protocol integration,
explicit setup is implemented; physical provider validation remains required. See
[implementation status](../docs/USB_PERMISSION_HELPER.md).

Authenticated session/request transport, PC ECDH enrollment/DPAPI storage and the existing
serial-owner broker adapter now have real-crypto Python/native interoperability tests. ESP
primitives compile on P4/S3 and were physically measured on P4. Device enrollment, key persistence
and explicit PC/device setup are connected. Physical enrollment validation, permission-specific
UI publication/final TX gates and opt-in remain required; no real approval is enabled.
See [authentication evidence](../docs/USB_INTERACTION_AUTH.md).

Claude Code PermissionRequest -> AI-Monitor-Permission -> same-user local IPC ->
validated AI Monitor host -> USB -> existing permission UI -> one decision back along the same path.
AI-Monitor-Events stays observational. Create a separate permission helper/executable and explicit
setup; do not give the event observer interactive authority.

The helper accepts one strictly bounded request, extracts only required transient ID/tool/hint fields,
creates a random request nonce, sends to the running host, waits for one exact matching decision,
returns the documented hook allow/deny response and exits. No network sockets, arbitrary file access,
shell execution, configuration changes, persistence, automatic approval or ambiguous approval retry.
If unavailable/expired, prefer normal Claude permission handling when its contract permits that
fallback; never auto-allow. Verify the actual hook contract before implementing fallback/output.

Use generic PermissionRequest, InteractionSnapshot, PermissionContext and PermissionDecision,
independent of ClaudeLiveSnapshot. Trusted context includes connection, opt-in, trustedChannel,
visibility, awake and demo state. USB attachment alone does not establish host trust.

Local IPC: per-user restriction, correct host instance, bounded fixed messages, nonce correlation,
deadline, one response, no TCP listener or arbitrary operations. Reuse proven local desktop IPC
patterns where appropriate. At actual transmission recheck correct device/session, opt-in, current
request ID/revision, freshness, visible complete details, earned continuous hold and single-use
commit. Disconnect, request change, stale state, hidden UI or trust loss cancels. Test synthetically
before harmless real physical approval/denial and unplug-during-hold integration.

## Phase 8: device history and daily summary

Checkpoint: compact Today/24h/7d token and reliable quota summaries are implemented, tested natively
and installed on P4. Atomic synthetic USB history delivery passed without changing activity counters.
The new candidate adds a bounded lifecycle journal and observed session/active-time/turn summaries.
It migrates the existing numeric backend, excludes waiting/gaps and unions overlapping agent activity.
Task success is not inferred from pre-veto hooks. Rc6 adds successful Claude post-tool task
transitions; unsupported metrics remain unavailable. History is opt-in and never transfers
the SQLite database. Current local preferences are kept outside public source.
See [device history](../docs/DEVICE_HISTORY.md) and [validation](../docs/V2_VALIDATION.md).

Reuse the existing PC SQLite history backend. Aggregate compact today/24-hour/7-day summaries;
never transmit the full database. Show per-provider tokens, sessions, reliable active time, quota
trends and structured completed/failed task counts only when backed by observed data.
Add small graphs and a daily AI summary; unsupported values remain unavailable.

## Phase 9: versioned animation packs

Checkpoint: bounded schema 2 and allocation-free playback are implemented in the candidate.
Built-in NOVA/ORBIT now use multi-pose mood sequences through the existing renderer/cache.
See [animation format](../docs/COMPANION_ANIMATIONS.md). Rc6 implements bounded PC import/storage
and verified dual-bank P4 RAM staging/activation with automatic host restoration. Interrupted
replacement retains the old pack. Native validation and actual device evidence remain separate;
microSD is not required and no device filesystem is formatted.

Separate mood from animation before public runtime packs. Support bounded multi-frame states,
frame duration, loops/nonloops, idle/blink/work/testing/attention/success/error sequences and runtime
selection. Keep strict schema/hash/dimension/decoded-size limits and fallback. Storage/staging,
atomic activation and recovery stay required if runtime packs are enabled. MicroSD is optional,
not a dependency of this phase or permission transport.

## Phase 10: later developer integrations

Structured build/test results and lightweight project/branch/changed-files/last-commit status.
Safe refresh, deny/approve, stop/retry/acknowledge actions only with explicit supported integrations.
No arbitrary terminal scraping, device Git client, remote shell or inferred test results.
PPA remains lower priority: revisit measured end-to-end performance after runtime rendering and
more animations/higher redraw frequency. Keep the proven CPU path meanwhile.

## Validation and hardware gates

P4 is JC4880P443C_I_W_Y on COM6; COM4 belongs to another project and must not be accessed.
No physical S3 is available. Production diagnostics retain firmware/app/free partition, heap/largest
block, PSRAM/largest block, display buffers, uptime, touch/host and future cache health.
Preserve private settings, NVS and firmware rollback backups. Fresh executable packaging, correct
installed-app/shortcut identity, real provider events, physical touch/USB tests, memory/latency and
soak/fresh-PC checks are release gates. Windows signing remains unresolved; do not bypass protection.

## Current next work

The corrected home UI is deployed on P4, and phase 2 domain separation is implemented.
The device enrollment core now interoperates with PC enrollment using actual native crypto;
it requires local arming, a matching physical UI revision, PC proof and successful storage before
acknowledging enrollment. Its real ESP crypto adapter is registered for enrollment only.
Device key storage/readback, physical hold-to-compare UI and explicit PC connection setup are now
connected for enrollment only. Separate permission opt-in and developer publication/transmission
gates are now implemented. Physically validate enrollment and the final exchange. Keep production permissions
disabled until exact packaged programs and physical provider/unplug tests pass.
The user confirmed Codex hook review/trust, but real hook delivery still requires observation.
Do not treat that confirmation or a saved marker as proof of lifecycle exchange.

References: docs/USB_LIVE_TRANSPORT.md, docs/LIVE_PROVIDER_EVENTS.md, docs/LIVE_AGENT_VIEW.md,
docs/COMPANION_RUNTIME_FORMAT.md, docs/P4_HARDWARE_BENCHMARKS.md and docs/PERMISSION_UI.md.
