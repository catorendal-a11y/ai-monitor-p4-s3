# USB-only v2 transport

Product decision, 2026-10-13: Bluetooth is permanently excluded. No BLE advertising, pairing,
GATT server, Bluetooth host stack or Bluetooth-to-USB relay will be added. C6/controller measurements
are historical hardware evidence, not a product dependency or a reason to initialize the radio.

## Boundaries

The existing PC host remains the sole serial owner. Quota/activity snapshots continue over AIM1.
A new, capability-negotiated, versioned live-event domain will share that connection without adding
permissions or generic agent state to `aim::Snapshot`. Provider adapters, live state, companion
rendering, transport and hardware diagnostics remain separate modules.

Host adapters may report only events actually exposed by supported provider interfaces. Missing
metadata stays unknown. Numeric token increases do not identify editing, testing or completed tasks.
Existing observational Claude Code hooks do not authorize or execute provider tools.

## Incremental integration

1. Define and test bounded live metadata, provider/session identity and event lifecycle independently
   of serial, UI and provider credentials. Do not retain transcripts, commands or tool hints in history.
2. Define an independent USB envelope and capability negotiation, with strict types, sizes, deadlines,
   sequence/epoch correlation and bounded queues. Keep old firmware and host quota behavior working.
3. Add synchronized state publication and read-only UI consumers. All LVGL work stays on the UI task.
4. Validate fragmented/interleaved traffic, malformed input, backpressure, unplug/reconnect, reboot,
   wrong board identity and stale epochs before physical P4 integration.
5. Connect documented provider event sources and show unsupported capabilities honestly in setup.

## Implemented read-only wire foundation

`get_info` advertises `liveProtocol:1` and `livePermissions:false`. Old firmware is never sent live
commands. The existing serial owner sends ordinary bounded JSON command lines, interleaved with AIM1;
there is no second serial connection. The following commands have exact allowlisted fields:

```json
{"cmd":"live_open","schema":1,"requestId":1}
{"cmd":"live_state","schema":1,"bootId":17,"epoch":1,"sequence":1,"agents":[{"provider":"claude","id":"opaque_1","state":"TESTING"}]}
{"cmd":"live_close","schema":1,"bootId":17,"epoch":1}
```

Open returns a device-issued epoch and zero sequence. `live_reply` includes type, schema, cmd, ok,
bootId, epoch, sequence, permissions (always false) and requestId (zero for state/close).
The examples use synthetic IDs; producers must use opaque session identifiers, never paths or text.
Maximum eight agents, known provider keys, unique provider/ID pairs, ASCII identifier length 1–64,
and fixed state names: UNKNOWN, IDLE, THINKING, EDITING, SEARCHING, BUILDING, TESTING, WAITING,
FAILED and DONE. UNKNOWN/IDLE preserve honest incomplete data instead of inventing task activity.
No tool hints, transcript, provider command or permission fields are accepted.

### Summary and session names (`liveSummary:1`)

Firmware that also advertises `liveSummary:1` accepts three optional top-level fields on
`live_state`, always together: `total` (sessions observed on the PC, 0-255, at least the number
listed), `selectedMask` and `linkedMask` (bit per provider in catalog order: providers the user
selected, and providers whose lifecycle events are linked). They let the Agents screen say "8 of 11"
and explain an empty list ("Not linked: CODEX, CLAUDE") instead of showing nothing. Each row may
carry `label` (1-15 ASCII letters, digits, space, dash) and `hue` (0-11), a name and colour derived
from the opaque id by `tools/session_identity.py`, so the device and the PC terminal show the same
"Jolly Beaver" for the same session. A name is a recognition aid, not an identity; it carries no
content. Hosts send these fields only when `get_info` advertises `liveSummary:1`.

State is a complete replacement, including an empty list. Sequence must strictly increase;
duplicate/older sequences cannot renew freshness. Incorrect boot/epoch traffic is rejected without
renewing or replacing current state. Invalid current-session metadata clears display data atomically.
Thirty seconds without valid state closes the session and clears agents. Opening also has a 30-second
deadline. Rollover-safe device timing is used; sequence/epoch exhaustion requires reopening/reboot
rather than wrapping identifiers. New open resets sequence; old epochs are never replayed.

`src/live_agent/usb_live.h` owns the independent state. The existing receiver publishes synchronized
value copies through `live_agent::read_usb()`. It does not add fields to `aim::Snapshot` or renew the
quota host lease. `tools/usb_live.py` uses the existing Panel owner and verifies correlated replies;
ambiguous delivery invalidates its session without retry. Regular host polling now uses the client
only for capability-advertising firmware. Provider adapters are opt-in Codex/Claude lifecycle observers;
the [live agent screen](LIVE_AGENT_VIEW.md) reads synchronized copies on the UI task. Physical
integration remains pending. Old firmware keeps its normal quota/activity behavior.

Synthetic Python and strict native C++ tests cover metadata, correlation, stale epochs/sequences,
expiry, clock rollover and coexistence with normal info/quota protocol state. They do not establish
physical USB performance or provider compatibility. Measure serial latency, queue pressure and quota
coexistence before choosing production scheduling. No host trust mechanism is implemented yet.

## Permission integration gate

The native permission controller/dialog remain a disabled prototype. A USB cable establishes neither
provider authorization nor authenticated host identity. Never hardcode `secure=true` for USB.
Approval requires an independently verified host session, explicit local opt-in, a documented provider
decision interface, the exact current prompt, complete visible details and a continuous physical hold.
Reconnect, stale data or ambiguous delivery must fail closed without replay.

Preferred future path: Claude Code PermissionRequest -> dedicated AI-Monitor-Permission helper ->
same-user local IPC -> validated host -> USB -> existing physical permission UI -> one response along
the same route. AI-Monitor-Events remains observational. No network listener, arbitrary file requests,
shell execution, prompt persistence or configuration changes during helper operation.
Unavailable/expired requests use normal provider permission handling when the documented hook
contract allows it; never automatic allow. Generic interaction types replace the legacy live-snapshot
dependency. Host/device/nonce/revision, freshness, opt-in, visibility and final single-use commit must
all be checked. See phase 7 in [the updated plan](../plans/COMPANION_V2.md).

Reference: [Claude Code PermissionRequest contract](https://code.claude.com/docs/en/hooks#permissionrequest).

### Read-only metadata capability 2

`liveMetadata: 2` adds generic agent state names and optional `elapsedSeconds` (0..604800) and
`observedAgeSeconds` (0..900) per entry. Unknown fields, booleans and out-of-bounds values reject
the whole snapshot. Legacy three-field entries and FAILED/DONE aliases still work. The host
downgrades entries for panels without the capability. Permissions remain disabled.
