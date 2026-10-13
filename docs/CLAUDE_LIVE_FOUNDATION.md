# Claude live protocol foundation

`src/live_agent/` is independent of USB/AIM1 quota snapshots, provider readers, companion rendering,
LVGL and BLE. Its current implementation is synthetic/native only. It cannot execute commands,
approve an actual tool call, open a model session or modify Claude configuration.

## Input and freshness

`ClaudeLiveProto` accepts bounded UTF-8 JSON lines of at most 4,095 bytes. Fragment accumulation
has a five-second deadline; overflow discards the rest of that line. Disconnect clears buffered data,
and reconnect creates a new epoch. Only a valid snapshot renews the 30-second lease.

Snapshots retain total/running/waiting counts (up to 1,024) and independently optional unsigned
64-bit output-token counters. These are output activity metrics, not input tokens, quota or billing.
Summary, transcript entries, owner information and completed-turn content are not retained in the
snapshot or logged. Commands/turn events do not extend its lease or dispatch operations.

An active permission prompt has exactly three fields: bounded ID (96 ASCII identifier characters),
tool (64 UTF-8 bytes) and hint (512 UTF-8 bytes). No truncation is accepted. Embedded NUL, unsupported
control characters, malformed input, missing fields and extra prompt fields fail closed. Hints may
contain explicit newlines. Valid unsupported glyphs remain nonapprovable; the future UI must also
verify that complete details are visible before enabling approval.

Prompt identity includes the complete original ID/tool/hint bytes. Changed details, an omitted prompt,
expiry, invalid input or disconnect invalidate previous approval context. The state machine compares
the actual bounded prompt as well as epoch/revision; sanitization cannot collapse two requests into one.

## Permission state

`PermissionMachine` defines NONE, RECEIVED, DISPLAYED, HOLDING, SENT, ACKNOWLEDGED, DENIED,
EXPIRED, CANCELLED and ERROR. Display confirmation requires the matching epoch/revision and an
explicit `completeDetailsVisible` assertion from the future UI. A continuous hold must last at least
1,800 milliseconds. Early release/drag-out/touch failure must call `cancel_gesture`; navigation cancels
the request. The final decision checks the current prompt, lease, local opt-in and secure link again.

A decision is returned once. The future transport adapter must revalidate immediately before TX;
failed or ambiguous transmission must not be retried as an approval. Security/opt-in parameters are
trusted local state, never fields supplied by remote JSON.

The Desktop reference does not specify permission acknowledgements. Therefore the implementation
does not treat successful notification delivery or disappearance of the prompt as ACKNOWLEDGED.
A correlated acknowledgement hook exists for an adapter with a documented acknowledgement source;
it has no current protocol integration.

## Tests and next integration gates

`scripts/run_tests.py` compiles and runs `tests/test_claude_live.cpp` with strict C++ warnings.
Tests cover fragmented lines, oversized/stalled input, malformed snapshots, changed prompt details,
disconnect/reconnect, clock rollover, stale leases, unsupported text, complete visibility, early release,
single-use decisions and final opt-in/security/identity checks.

Real native LVGL permission controls, pointer cancellation, queued/final commit checks and a persistent
interaction authority are now implemented; see [the permission UI contract](PERMISSION_UI.md).
Physical touch testing, synchronized firmware publication and a verified USB/provider adapter
remain gates. Bluetooth is permanently excluded. Direct Hardware Buddy integration is removed
because its documented transport is BLE; a USB cable cannot replace that desktop API.
No permission sender is enabled in production. See [USB-only integration](USB_LIVE_TRANSPORT.md).

The [official Hardware Buddy protocol](https://github.com/anthropics/claude-desktop-buddy/blob/main/REFERENCE.md)
is an experimental Claude Desktop developer-mode interface, not a generally supported product feature.
