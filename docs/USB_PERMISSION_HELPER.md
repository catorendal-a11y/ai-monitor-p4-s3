# USB permission implementation status

Permissions are not enabled in production. The normal Claude permission dialog remains the
fallback. USB attachment and a local pipe do not authenticate a device approval.

## Implemented and tested

- `src/interaction/` owns the generic request, state machine and controller independently of
  ClaudeLiveSnapshot. The existing native LVGL dialog uses this domain. Its continuous 1.8-second
  hold, complete visible details, cancellation and one-time final commit gates are preserved.
- `tools/aim_permission.py` is a separate PermissionRequest helper. It extracts the tool and all
  canonical arguments, bounded to 320 printable ASCII characters. Requests that cannot be fully
  reviewed use the normal Claude dialog. It never truncates arguments before approving.
- Each request has a random 128-bit ID and 256-bit nonce, revision 1 and a maximum 25-second
  lifetime. Exact response correlation is required. The output contains only Claude's documented
  allow/deny behavior; it cannot modify tool input or persistent permission rules.
- `tools/permission_ipc.py` uses local Windows named pipes with an explicit current-user DACL,
  remote-client rejection and bounded JSON bytes. No TCP listener, pickle or shell dispatch.
  Kernel-reported peer PIDs are checked against installed host/helper executable paths.
- `tools/permission_broker.py` holds one request and checks local opt-in, authenticated device,
  host instance, session, nonce, revision and deadline. Disconnect, context change and ambiguous
  decisions consume/cancel authority. Its bounded replay ledger stores IDs/nonces, never arguments;
  exhaustion rejects further requests until a new host instance rather than forgetting old requests.
- `tools/permission_service.py` implements the optional local IPC service and rechecks authority
  immediately before returning a decision. Its endpoint contains only PID and instance ID. Endpoint
  removal is scoped to its owner; prompt arguments are not written to disk or logs.
- The Windows package builder creates a separate AI-Monitor-Permission.exe and smoke-checks it.
- `tools/permission_runtime.py` now manages explicit attachment to the existing Panel owner,
  authenticated client/service shutdown and host-instance replay protection across reconnections.
  User opt-in and a separate locally constructed validation gate are both required. Disabled
  attachment never reads a trust file or opens IPC. Failed/ambiguous startup is not retried on the
  same connection; an incomplete service shutdown blocks replacement until host restart.
- `Panel.attach_permission_runtime`, event routing, periodic pumping and close hooks are connected.
  Normal startup creates an inactive coordinator; the local release gate remains false, so it cannot
  read trust records, start IPC or authorize approvals. An authenticated best-effort close cancels device
  authority on normal shutdown without awaiting/retrying a response; disconnect uses lease expiry.
- `src/interaction/permission_delivery.h` provides a bounded, one-shot UI/serial handoff. The actual
  PermissionView must commit its earned decision before admission. Final consumption checks both
  the current request and a local UI observation less than 100 ms old. Native LVGL tests exercise
  hold/deny through this gate; native cases cover changed request, hidden UI, trust loss, expiry,
  rollover and forged envelopes. The developer adapter now connects task synchronization and final
  ESP serial transmission; real hardware validation remains required.

## Device runtime integration checkpoint

`src/interaction/permission_serial.h` now joins the authenticated request domain to the earned
UI handoff. It signs only when normal USB output is empty and there is capacity for a whole bounded
decision packet. Connection, request lifetime and UI freshness are checked again after signing and
after capacity checks. No signed decision is queued behind ordinary output. Short/ambiguous writes
consume authority and invalidate the session; they are never retried.

`permission_runtime_esp.*` connects this core to the existing serial task and a recursive task mutex,
without running LVGL on that task. Local cancellation uses an atomic revocation latch before waiting
for the mutex. Local opt-in is a versioned atomic latest-value request; an older enable cannot replace
a newer disable because an action queue is full. Consent starts off, is not saved, cannot be set by a
USB field, and cannot wrap its generation. Trust is loaded on the serial task only after local opt-in.

`src/ui_permission.cpp` owns the existing PermissionView on the UI task, rechecks awake/visible state,
and offers only an earned and committed envelope. Failed publication reads revoke before hiding.
Actual LVGL wrapper tests cover a continuous hold and immediate cancellation on publication failure;
the lower-level pointer/visibility/drag/touch-read tests remain in place.

The `esp32p4-permission-integration` environment compiles this developer path. Its TX buffer is bounded
to 2,048 bytes and HWCDC writes use a zero timeout. It starts with device opt-in off, has no wire opt-in
command, and is not a production flash/release target. Normal P4/S3 builds keep interactionProtocol 0
and do not create a permission overlay. Explicit opt-in UI/provider setup is implemented as described
below; compile/native tests do not establish physical approval safety.

## Explicit setup and removal

The Windows app has a separate, default-off USB permission preference in Host settings. It is
available only with P4 and explicitly selected Claude Code. Save that preference before using
**Link Claude permission helper**. The confirmation explains the preview gate and normal-dialog
fallback. Setup uses Claude's documented executable form (`args: []`), not a shell command.
It backs up settings before an atomic update and preserves other hooks and permission rules.
**Remove permission helper** removes only the matching helper for this installation.

On the display, open **MENU > SETTINGS > CONNECT PC**, then tap **CONNECT PC** on that page
to open the physical comparison screen. Use **Connect this PC to the display** in the Windows app,
compare every code group, hold **HOLD TO CONFIRM** on the display and choose **Codes match** on PC.
This enrolls a key only; it does not enable permissions.

The same display page has a separate permission toggle in the developer firmware. Consent resets
on every reboot. Normal firmware shows a disabled preview control until physical release validation.
Every permission still requires a new 1.8-second hold; an already-held finger cannot start approval
when a dialog appears. PC preferences cannot enable the local production validation gate.

The IPC service is deliberately not started by normal host startup. Synthetic locally constructed
trust contexts establish state-machine behavior only; they do not establish actual USB trust.
Observational AI-Monitor-Events hooks remain unchanged and have no approval capability.

## Remaining production gates

The authenticated session, bounded request transport, PC enrollment/DPAPI and serial-owner
broker adapter foundations now have real-crypto native interoperability tests. ESP primitives
were physically measured on P4. This does not enable production approvals; see
[authenticated USB foundation](USB_INTERACTION_AUTH.md).

1. Physically validate the now-connected enrollment-only path, explicit PC/device code comparison,
   fixed NVS record/readback and current-user DPAPI storage. Authenticated permission sessions
   remain separate and disabled; enrollment alone must never enable them.
   Never obtain trustedChannel from an incoming JSON boolean or merely matching a board model.
2. Physically validate the now-connected developer adapter, ESP task synchronization,
   UI publication and immediate serial write, with authenticated decisions
   and disconnect cancellation through the existing serial owner. Quota/live-agent state remains
   in separate structures.
3. Validate the implemented explicit desktop/device opt-in and dedicated Claude PermissionRequest
   setup using the packaged programs. No real hook was installed during synthetic testing.
4. Verify the actual packaged helper/server, physical hold/drag/touch failure, expiry and unplug
   behavior. Confirm the real Claude hook contract without synthetic approval presented as evidence.

No runtime interactive hook is installed by this development checkpoint. No real tool permission
has been approved. An unavailable host, invalid request or timeout produces empty stdout and exit 0
so Claude retains its normal permission flow; it never produces an automatic allow.

References: [Claude hook contract](https://code.claude.com/docs/en/hooks#permissionrequest),
[Windows pipe access control](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights).
