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
  Normal startup still leaves the runtime absent. An authenticated best-effort close cancels device
  authority on normal shutdown without awaiting/retrying a response; disconnect uses lease expiry.
- `src/interaction/permission_delivery.h` provides a bounded, one-shot UI/serial handoff. The actual
  PermissionView must commit its earned decision before admission. Final consumption checks both
  the current request and a local UI observation less than 100 ms old. Native LVGL tests exercise
  hold/deny through this gate; native cases cover changed request, hidden UI, trust loss, expiry,
  rollover and forged envelopes. Task synchronization and the final ESP serial write remain required.

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
2. Connect the bounded interaction USB adapter and tested delivery gate to ESP task synchronization,
   UI publication and the immediate serial write, with authenticated decisions
   and disconnect cancellation through the existing serial owner. Quota/live-agent state remains
   in separate structures.
3. Add explicit desktop/device opt-in and dedicated Claude PermissionRequest setup. Do not silently
   enable Claude or modify existing observational hooks.
4. Verify the actual packaged helper/server, physical hold/drag/touch failure, expiry and unplug
   behavior. Confirm the real Claude hook contract without synthetic approval presented as evidence.

No runtime interactive hook is installed by this development checkpoint. No real tool permission
has been approved. An unavailable host, invalid request or timeout produces empty stdout and exit 0
so Claude retains its normal permission flow; it never produces an automatic allow.

References: [Claude hook contract](https://code.claude.com/docs/en/hooks#permissionrequest),
[Windows pipe access control](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights).
