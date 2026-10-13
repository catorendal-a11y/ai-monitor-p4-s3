# Companion v2 construction plan

## Current transport decision

The user explicitly removed Bluetooth from the product on 2026-10-13: USB only, now and in future
phases. Do not implement BLE, Bluetooth pairing, advertising, GATT, HCI bring-up or a radio bridge.
Historical C6 measurements remain evidence only; the standalone probe now checks identity/version only.
USB live-domain work replaces phase H below. Existing native permission code is a disabled prototype;
USB attachment alone must never set its trusted `secure` flag or authorize a tool call.
See [the USB architecture and integration gates](../docs/USB_LIVE_TRANSPORT.md).

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
- Existing observational Claude hooks remain independent of live permission authority.
- New live text/tool hints are transient display data: bounded, sanitized, never saved in history/logs/exports.
- No permission is approved through hooks, automatic rules, a tap, a reconnect or an asset command.
- Permission transmission requires explicit opt-in, a verified trusted USB-host session, a current prompt and
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
LVGL format. Report complete delivered-pack size including its manifest; choose USB transfer limits
from measured memory/storage budgets. The former Desktop BLE folder limit no longer applies.
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
host trust revocation cancels. No approval while booting, sleeping, in demo mode or before verified host trust.
Revalidate after queueing and immediately before TX; test changed/expired requests between hold and send,
repeated holds, identical displayed prefixes and control-character changes in details.
Validation: real LVGL synthetic touch/state sequences plus physical P4 gestures; S3 stays unverified
until physically tested. Exit: approval fails closed in every cancellation path. Dependencies: F.
Rollback: read-only live state; approval controls absent/disabled, never auto-approve.

## H - USB live-domain transport

Context: the existing PC host owns the board's USB connection. Bluetooth is excluded permanently.
Files: independent bounded live-event protocol/host adapter, synchronized firmware publication,
capability negotiation and native/synthetic tests. See `docs/USB_LIVE_TRANSPORT.md`.
Tasks: carry live metadata in a separate versioned domain over the same serial owner; preserve AIM1
quota snapshots unchanged. Reconnect/reboot creates a new epoch, clears partial frames and cancels
permissions. Reject unknown versions, invalid fields and oversized input; bound queues and deadlines.
Start with read-only, documented provider events. Do not infer detailed agent states from quota usage.
Permission transmission remains disabled until a supported provider decision interface and independently
verified USB-host trust mechanism exist. Never mark USB trusted merely because a cable is connected.
Validation: synthetic fragmented/interleaved traffic, backpressure, unplug/reconnect, changed board
identity, stale epochs and no permission dispatch. Then validate read-only events on the physical P4.
Exit: measured USB live activity while normal quota monitoring remains functional. Permission approval
has a separate integration gate; it is not replaced by fabricated responses or transcript scraping.
Dependencies: F and existing USB baseline; G applies only to future verified permission integration.
Rollback: disable the live-domain adapter and retain normal USB quota/activity monitoring.

## I - Companion packs and microSD

Context: renderer/schema are established in E; future verified USB transfer uses H. SD wiring/storage
availability must be verified on the actual board. Desktop BLE folder push is excluded.
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

The current product direction is USB only; no Bluetooth bring-up continues. Historical C6 detection
does not create a radio dependency. Verified provider permission integration follows F/G and USB H;
SD packs remain later. Synthetic fixture authoring may
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
controller init/enable RPC before Bluetooth was permanently excluded. No HCI/BLE work continues.
Results and limits are documented in `docs/C6_BRINGUP.md` and `docs/P4_HARDWARE_BENCHMARKS.md`.
C now has physical CPU/PPA rotation and normal flush-counter measurements. PPA matched every
pixel in eight trials and was 1.625x faster for isolated full-frame rotation. Production remains on
CPU pending partial-region, DMA/cache/scanout/soak checks. Bandwidth/buffer comparisons remain pending.
D now has physical P4 measurements for all twelve poses/four codecs, five hash-verified trials each.
LZ4 is selected for the experimental P4 cache; S3 and working-UI measurements remain pending.
E has actual PSRAM allocation/hash/decode validation on P4 plus native LVGL lifetime/fallback tests
and a generic renderer view. Production source selection, physical cached rendering and SD binding
remain pending. See `docs/COMPANION_RUNTIME_FORMAT.md`. F has a tested bounded parser and permission state machine; firmware publication and
transport binding are pending. G now has native-tested fixed permission controls, fail-closed visibility,
pointer cancellation and one-shot final commit validation; production integration/physical gestures
remain pending. H now has a bounded read-only USB metadata core, capability handshake, synchronized
publication and an integration client using the existing serial owner. Native/Python tests cover
sequencing, expiry and normal protocol coexistence. Regular polling now includes opted-in Codex/Claude
lifecycle adapters, with setup/removal and neutral observer-output tests. The device now has a
native-tested read-only agent view with fixed controls. Actual client compatibility and physical USB
measurements remain pending. I and additional notification/timeline/history features
are not implemented. See `docs/LIVE_PROVIDER_EVENTS.md` for honest state mappings and setup limits.
No permission sender or Bluetooth transport is enabled.
Physical touch/soak/fresh-PC checks from A remain explicit validation gates, not claimed successes.

Primary references: [Claude Desktop Hardware Buddy](https://github.com/anthropics/claude-desktop-buddy/blob/main/REFERENCE.md),
[ESP-Hosted](https://github.com/espressif/esp-hosted-mcu),
[PPA driver](https://docs.espressif.com/projects/esp-idf/en/v5.5.2/esp32p4/api-reference/peripherals/ppa.html).
