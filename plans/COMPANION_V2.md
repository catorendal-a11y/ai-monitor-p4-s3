# Companion v2 construction plan

User-authorized sequence: finish the analysis fixes, then v2. The user subsequently authorized
push. Release/tag/forum publication remains a separate action. Keep English source, documentation and product UI.
Each phase produces a local reviewable commit and evidence; synthetic tests never establish hardware success.
The user identified the PCB as JC4880P443C_I_W_Y; microSD presence is still unconfirmed.
Continue incremental implementation; verify this revision's wiring before active C6/SD initialization.
Runtime detection and physical exit gates remain pending actual measurements.

## Historical starting point

Canonical Git root is this project directory, branch `codex/usage-insights`. Local HEAD `22c5790`
contains the initial brightness recovery fix, transparent global crops, origin-preserving renderer,
coalesced desktop/host token readers and Windows Job Objects. 298 Python tests pass. Both firmware
targets and actual native LVGL interfaces were built/tested previously. The installed PC app and
physical P4 still run v1.18.5; latest candidates have not been physically flashed. COM6 is the
identified P4; COM4 belongs to another project and must not be accessed. No physical S3 available.

Use `AGENTS.md`, `docs/BOARDS.md`, `docs/PROVIDER_ROADMAP.md` and this file for cold-start execution.
Never read personal conversations/auth for development, copy private configs into a package or
replace the working drivers/platform pin merely because another board's example uses different versions.

## Invariants

- P4 and S3 retain normal USB quota/activity monitoring with no default AI selection.
- All LVGL/backlight/NVS work belongs to the UI task. Parsing and transport cannot mutate widgets.
- Existing observational Claude hooks remain independent of the new Desktop BLE permission path.
- New live text/tool hints are transient display data: bounded, sanitized, never saved in history/logs/exports.
- No permission is approved through hooks, automatic rules, a tap, a reconnect or an asset command.
- Permission transmission requires explicit opt-in, encrypted bonded transport, a current prompt and
  a completed physical hold on the exact displayed request. Unsupported/security state is closed.
- Built-in companions always remain available without SD, PSRAM cache or a valid pack.
- At the instant of transmission recheck opt-in, negotiated security, link epoch, prompt ID,
  complete-detail revision and lease; consume an approval once. Never replay ambiguous delivery.
- C6 firmware is not overwritten as a probe. Active hosted initialization must use verified wiring
  and record compatibility failures without turning an unprobed chip into a detected device.
- Every buffer, decoder, queue, manifest and transfer has strict type/size/time limits.

## A - Finish current analysis fixes

Context: source fixes are local; process containment now has real synthetic Windows process tests.
Files: `tools/process_runtime.py`, `tools/windows_job.py`, settings/touch helpers and existing tests.
Tasks: preserve the passing baseline, record remaining physical touch/soak/fresh-PC checks explicitly;
verify packaged modules and workers; do not relabel missing hardware tests as completed fixes.
Validation: `python -m unittest discover -s tests -p "test_*.py"`; package checks with fake provider/home.
Exit: source defects fixed, tests pass, unresolved physical checks listed and carried into B/C/H.
Rollback: previous local commit; no external publication and no private config overwrite.

## B - Hardware baseline

Context: firmware currently reports board/chip identity, free heap and free PSRAM. P4 has separate
logical draw buffers, rotation scratch and DPI framebuffers. C6/hosted are not initialized by this app.
Files: `src/diagnostics/`, `src/ai_monitor/`, board/display/HAL interfaces, Python diagnostic reader.
Tasks: add a bounded read-only hardware reply with actual chip revision, flash/app partition, PSRAM
totals/free/largest block, heap, SDK version and allocated display buffer sizes. Distinguish compiled
hosted/PPA support from runtime detection. Collect serial identity on the exact board; verify PCB/module
revision and hosted wiring before an active, bounded coprocessor/version probe. Preserve NVS/config.
Validation: strict protocol fixture tests, both firmware builds, chip/board mismatch and legacy replies.
Exit: baseline artifact records measured values and explicit unknown/not-probed values; C6 chip and
firmware version are only marked detected after successful runtime communication.
Dependencies: A implementation. Rollback: omit new diagnostic command; retain normal info/USB behavior.

## C - Graphics benchmark

Context: P4 rotates partial RGB565 regions on CPU; PPA driver exists in the SDK. S3 has no PPA path.
Files: diagnostic counters/bench harness, `src/ui/lvgl_hal*.cpp`, `src/ui/display*.cpp`, benchmark docs.
Tasks: measure render/rotate/copy/present timing separately, frame/update rate, buffer allocation,
internal/PSRAM bandwidth and memory high-water data. Use an explicit benchmark mode, off by default.
Compare CPU with PPA on aligned scratch buffers before touching production display presentation.
Validate orientation, buffer lifetime, completion/cache ownership and display scan behavior on hardware.
Validation: deterministic test patterns/checksums, native rotation correctness, hardware timings;
PPA timeout/failure must retain the CPU fallback. Never report PC native timing as P4 throughput.
Exit: benchmark report and measured choice of buffer/rotation approach. Dependencies: B.
Rollback: original CPU rotation and proven buffer sizes; benchmark instrumentation disabled.

## D - Asset benchmark and runtime format

Context: cropped RGB565+A8 payload is 3,349,656 bytes; origins are fixed per companion family.
Files: asset generators, benchmark scripts, reproducible results, proposed frame/manifest format.
Tasks: compare raw, RLE, LZ4 and suitable lossless alternatives with identical cropped pixels. Measure
compressed size, real target decode latency, peak memory and visual equality, not size alone.
Choose a versioned format compatible with constrained S3 and P4; separate delivery format from decoded
LVGL format. Report complete delivered-folder size including manifest against Desktop's under-1.8-MB
folder limit; use individual-companion packs or an explicitly supported alternative when it cannot fit.
Reject malformed/truncated/oversized compressed frames before exposing them to LVGL.
Validation: round-trip pixel hashes, fuzz/limit fixtures, both target decode tests/measurements.
Exit: documented runtime-format decision with evidence and safe raw/built-in fallback. Dependencies: C.
Rollback: current generated RGB565+A8 arrays; no compulsory compression or extra decoder on boot.

## E - CompanionRenderer, manifest and PSRAM cache

Context: the initial renderer preserves cropped origins; it has no runtime pack/cache support yet.
Files: `src/ui/companion_renderer.h`, new bounded companion manifest/cache/provider modules, native UI tests.
Tasks: versioned schema, dimensions/origins/pose enum/format/decoded and encoded sizes/SHA-256;
fallback chain requested pose -> pack fallback -> built-in same pose -> built-in work.
Allocate a bounded PSRAM pool during initialization within the measured budget; rendering and cache
swaps allocate nothing. Retain/pin image storage until LVGL no longer reads it.
Stable pose origins and fixed controls survive cache eviction, decoder failure, SD loss and pack changes.
Validation: invalid versions/paths/overflow/missing frames/allocation failures, cache lifetime tests,
actual LVGL screenshots and both targets. Exit: safe runtime selection without losing built-ins.
Dependencies: D. Rollback: built-ins only; cache/pack selection remains disabled by default.

## F - ClaudeLiveProto and state machines

Context: official Claude Desktop Hardware Buddy uses NUS JSON lines; this is separate from quota
and Claude Code hooks. The reference includes snapshots, turn events, permission requests and commands.
Files: independent `src/claude_live/` pure protocol/state core and synthetic fixtures/tests.
Tasks: bounded incremental UTF-8 framing, strict schema/counts/IDs, 30-second lease, transport epochs;
session states and permission states with revisions. Reject/restrict file/name/owner commands until their
specific handlers exist. Drop transcript storage; expose only bounded transient text needed for the UI.
Permission invalidation on replacement, changed request details, expiry, disconnect, unpair and reboot.
Valid authoritative snapshots omitting prompt revoke it. Only valid snapshots renew their lease;
malformed/oversized prompt-bearing input disables approval. Turn events and commands cannot renew it.
Truncated, unsupported or incompletely reviewable details are not locally approvable; use Desktop.
Compute revisions from complete accepted request fields before presentation sanitization.
Validation: partial/multiple/oversized/invalid frames, rollover, repeats, stale IDs, queue limits,
synthetic permission events and no transmission before validated authorization.
Exit: pure tested core with no BLE/LVGL/PC execution side effects. Dependencies: E.
Rollback: no live protocol dispatch; existing observational/activity/quota code remains intact.

## G - Permission UI

Context: existing touch-target ownership/failed-read cancellation provide the starting interaction layer.
Files: new permission screen/overlay, touch interaction helpers, UI/core event queues and native tests.
Tasks: show request identity/tool/hint clearly; fixed HOLD TO APPROVE and deny controls; complete
one continuous timed hold with progress. Gesture captures request revision and transport epoch.
Drag-out, touch read failure, release early, stale data, changed prompt, navigation, disconnect or
unpair cancels. No approval while booting, sleeping, in demo mode or before encrypted connection.
Revalidate after queueing and immediately before TX; test changed/expired requests between hold and send,
repeated holds, identical displayed prefixes and control-character changes in details.
Validation: real LVGL synthetic touch/state sequences plus physical P4 gestures; S3 stays unverified
until physically tested. Exit: approval fails closed in every cancellation path. Dependencies: F.
Rollback: read-only live state; approval controls absent/disabled, never auto-approve.

## H - C6 BLE transport and real Desktop test

Context: P4 has no integrated BLE radio; actual C6/hosted capability/version must be established in B.
Files: transport adapter, explicit pairing/settings UI, hosted/NimBLE integration and compatibility docs.
Tasks: verified hosted BT-controller path and version compatibility; encrypted-only NUS RX/TX/CCCD,
LE Secure Connections bonding with displayed passkey, explicit pair/unpair mode, bounded RX/TX queues
and MTU fragmentation. No unencrypted fallback. Reconnect starts a new epoch and needs a new current
snapshot; no stale permission resend. Preserve normal USB quota/activity functionality.
Validation: real C6 link, wrong/absent bond, unauthorized write/CCCD, reconnect/expiry, pairing removal;
official Claude Desktop developer-mode connection and a harmless test permission in an isolated folder.
Exit: real authenticated Desktop/P4 flow proved, including disconnect during hold. Required external
inputs: supported board/C6 firmware, installed compatible Desktop app, user's sign-in and pairing.
Dependencies: G plus B C6 proof. Rollback: disable BLE; retain USB and read-only normal companions.

## I - Companion packs and microSD

Context: renderer/schema are established in E; authenticated transfer uses H. SD wiring/storage availability
must be verified on the actual board. Desktop folder push has its own delivery size/ack constraints.
Files: pack staging/validation/activation modules, SD adapter, manifest/pack tooling and tests.
Tasks: strictly contained flat filenames, per-file and total limits, bounded chunk/base64 decode,
SHA-256 verification, version/decoded-size validation, inactive staging and atomic activation marker.
Use immutable staged generations, flush completed files before a generation completion marker, and
validate the manifest/file hashes on boot before choosing a generation. Reserve staging space separately.
Power loss, full/missing/removed SD, checksum mismatch or invalid manifests fall back to the previous
valid generation or built-ins. Reject firmware/config/executable uploads; no arbitrary path writes or code execution.
Validation: traversal, symlink-like/path confusion, duplicates, bad hashes, malformed chunks,
interrupted transfers and physical SD removal/reboot. Exit: verified selectable packs and recovery.
Dependencies: E and H. Rollback: built-ins; ignore invalid staging; no activation before verification.

## Execution and review

The latest product direction moves standalone C6/ESP-Hosted bring-up early, alongside B/C, once
the board revision's wiring is verified. It does not depend on Claude or permission UI. Secure
Claude transport integration still follows F/G; SD packs remain later. Synthetic fixture authoring may
proceed while hardware is unavailable, but phases retain their physical exit gates. Reviewer checks
dependency correctness, missing hardware assumptions, privacy, cancellation, bounds and rollback.
If a probe exposes incompatible hardware/SDK, amend this plan with the evidence rather than silently
flashing C6 or substituting a different radio path. Push is authorized; releases remain a separate step.

## Additional v2 product domains

After the foundations, implement live activity (THINKING, EDITING, SEARCHING, BUILDING, TESTING,
WAITING, FAILED, DONE) in a distinct bounded domain, with synthetic lifecycle tests. Do not infer
these states from quota decreases or invent tool detail absent from a provider's events.
Multi-Agent View consumes live session/provider identity and state without adding it to `aim::Snapshot`.
Permission states are NONE, RECEIVED, DISPLAYED, HOLDING, SENT, ACKNOWLEDGED, DENIED, EXPIRED,
CANCELLED and ERROR; security and prompt revision/epoch checks govern every transition.

Task-finished/needs-attention events, session timer, bounded activity timeline and notification center
must deduplicate and expire events; companion reactions consume these events independently of renderer
and transport. Numeric usage history already exists locally; extend it with reliable session/active-time
metrics only when source events establish them, preserving explicit opt-in and transcript exclusion.

Build/test status, Git/project status, daily summary, audio, microSD packs and configurable layouts
follow later. No Wi-Fi host, web dashboard, camera, voice assistant, cloud account or full transcripts.

## Current implementation checkpoint

Source fixes and regression validation are recorded in `docs/V2_VALIDATION.md`. B exposes read-only
metrics and initialization checkpoints; P4 physical collection and application flash succeeded.
PC diagnostics reads a capability-negotiated snapshot through the existing host. Production SD/C6
initialization remains disabled; standalone runtime C6 detection has now succeeded.
The standalone C6 test physically detected the coprocessor, read host/slave versions and confirmed
controller init/enable RPC; production radio initialization, HCI and secure BLE remain pending.
Results and limits are documented in `docs/C6_BRINGUP.md` and `docs/P4_HARDWARE_BENCHMARKS.md`.
C now has physical CPU/PPA rotation and normal flush-counter measurements. PPA matched every
pixel in eight trials and was 1.625x faster for isolated full-frame rotation. Production remains on
CPU pending partial-region, DMA/cache/scanout/soak checks. Bandwidth/buffer comparisons remain pending.
D has exact host compression sizes; target decode timing and final runtime format remain pending.
E has tested manifest/cache scaffolding and built-in rendering; runtime PSRAM/LVGL/SD binding remains
pending. F now has a tested bounded parser and permission state machine; firmware publication and
transport binding are pending. G/H/I and the additional live product domains are not implemented.
Physical touch/soak/fresh-PC checks from A remain explicit validation gates, not claimed successes.

Primary references: [Claude Desktop Hardware Buddy](https://github.com/anthropics/claude-desktop-buddy/blob/main/REFERENCE.md),
[ESP-Hosted](https://github.com/espressif/esp-hosted-mcu),
[PPA driver](https://docs.espressif.com/projects/esp-idf/en/v5.5.2/esp32p4/api-reference/peripherals/ppa.html).
