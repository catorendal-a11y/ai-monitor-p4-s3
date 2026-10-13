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

Claude Desktop's experimental Hardware Buddy reference currently documents a BLE NUS interface,
not a USB interface. Therefore direct Hardware Buddy integration is removed from this roadmap.
Do not claim that changing the board transport makes that desktop interface work over USB, or use
Bluetooth as an intermediate bridge. Find and validate a supported alternative provider adapter
before enabling real permissions. Read-only Claude Code activity remains a separate integration.

Reference: [official Hardware Buddy protocol](https://github.com/anthropics/claude-desktop-buddy/blob/main/REFERENCE.md).
