# AI Monitor P4 development

## Architecture

- `src/main.cpp`: task startup and UI loop.
- `src/ai_monitor/`: bounded AIM1/JSON protocol, snapshots and USB receiver.
- `src/agent/`: independent session/activity domain. Counts, phases, tasks and timers never belong
  in aim::Snapshot. Existing session_activity packets remain a compatibility transport adapter.
- `src/interaction/`: generic permission model/controller. Never depend on ClaudeLiveSnapshot;
  opt-in and trustedChannel are local authority, not JSON flags. Preserve every fail-closed UI gate.
- `src/interaction/auth_session.h`, `usb_interaction.h`: bounded authenticated transport/request
  domain. Empty keys and absent opt-in fail closed; no wire flag establishes trust. The serial
  adapter cannot earn UI authorization. Keep production integration disabled until enrollment,
  persistence, UI final gates and real provider/hardware tests pass.
- `src/interaction/enrollment.h`, `enrollment_esp.*`: local-only arming and revision-bound physical
  comparison. Preserve deadlines, explicit PC proof, successful storage before acknowledgment,
  ephemeral-key cleanup and separate permission opt-in. Never confirm from a wire boolean.
- `tools/interaction_auth.py`, `interaction_trust.py`, `usb_interaction.py`: ECDH/HMAC sessions,
  current-user DPAPI and the existing serial-owner adapter. Never start a second serial owner,
  retry ambiguous approvals, log hints/keys or auto-select/enable Claude.
- `tools/aim_permission.py`, `tools/permission_ipc.py`: separate interactive helper, bounded bytes
  over same-user Windows named pipes; no TCP/pickle/shell or changes to observational hooks.
- `tools/permission_runtime.py`: explicit existing-serial-owner lifecycle. Preserve the host-instance
  replay ledger across USB/service replacement. No automatic activation, approval retry or service
  replacement after unconfirmed shutdown; user opt-in cannot substitute for local validation.
- `src/interaction/permission_delivery.h`: only a real UI-owner commit admits a decision. Preserve
  one-shot consumption, current-request matching and fresh local visibility at the serial gate;
  queued envelopes do not authorize delayed transmission.
- `src/interaction/permission_serial.h`, `permission_runtime_esp.*`, `src/ui_permission.cpp`: developer
  runtime only until physical validation. Keep ordinary USB output separate from immediate decision
  writes, recheck after signing/capacity, never retry partial writes, and revoke atomically before
  mutex waits. Failed UI publication reads are cancellation, not an empty-request dismissal. Local
  consent must supersede older actions and remain off at boot; no wire/config flag creates it.
- Hardware initialization: inspect display/touch sources before changing board pins.
- `src/dashboard.cpp`, `src/ui_nova.cpp`, `src/ui_usage_details.cpp`, `src/ui_settings.cpp`, `src/ui_notifications.cpp`: LVGL screens/interactions.
- `src/ui/`: state/format/history helpers, theme and generated assets.
- `src/ui_agents.cpp`: UI-owner read-only live metadata view; never add agent state or permissions
  to quota snapshots, infer tool phases from counters or move navigation controls with incoming data.
- `src/ui_menu.cpp`: shared UI-owner navigation; refresh remains directly on the home screen. Keep MENU targets
  fixed, return to the calling screen, and show provider paging only when necessary. Normal usage
  always uses two full-size provider cards rather than shrinking to a four-card grid.
- `src/history/`, `src/ui_history.cpp`, `tools/device_history.py`, `usb_history.py`: separate bounded
  history domain from the existing SQLite backend. Unknown gaps are null, not zero. No inferred
  sessions/active time/tasks, transcripts or database transfer. Read SQLite off the serial owner;
  publish complete transactions only and preserve dropdown identities until touch release.
- `tools/agent_history.py`: opt-in fixed lifecycle journal in the existing SQLite store. Preserve
  numeric migration, consent epochs, bounded hook writes and disable/shutdown revocation. Waiting
  and unobserved gaps are not active time; concurrent intervals are unioned. Turns are not tasks.
- `src/companions/animation_types.h`, `animation.h`, `builtin_animation.h`: bounded versioned mood
  sequences and UI-owned playback. No allocation per frame, inferred phases or cache lifetime changes.
- `src/companions/pack_store.h`, `runtime_esp.*`, `tools/companion_packages.py`, `companion_service.py`:
  data-only external P4 packs. Preserve bounded PC storage and both preallocated RAM banks, complete
  encoded/decoded validation, exact boot/nonce/offset receipts and UI-only bank activation. Never
  extract/execute archives, format display storage, reuse active-bank bytes or add a serial owner.
  Read-only library checks cannot create directories. Failed transfers retain the previous pack.
- `src/mirror/`, `tools/usb_mirror.py`, `mirror_service.py`, `desktop_mirror.py`: real read-only USB
  pixels through the existing serial owner. Bound coverage/RLE/nonce/leases and scrub/free buffers.
  Never expose protected screens, virtual touch or approval authority. Captures are not history.
- `src/ui/companion_renderer.h`: preserve cropped frame origins across poses and companions;
  allocate the P4 LZ4 cache once at startup, verify encoded/decoded bytes, pin live LVGL sources,
  and retain raw work-pose fallback per companion. No allocation per render.
- `src/app_settings.*`: validated NVS settings/save feedback.
- `tools/aim_host.py`: polling, retries, config and USB companion.
- `tools/process_runtime.py`, `tools/windows_job.py`: scoped background worker startup and verified cleanup; never target unrelated processes by name.
- `tools/token_activity.py`: read-only numeric token activity.
- `tools/aim_control.py`: console setup, scoped host controls and verified firmware installation.
- `tools/aim_events.py`, `tools/live_events.py`: explicitly enabled Codex/Claude state observers;
  no model, host or serial control, transcripts or tool decisions. Codex's wrapper emits only neutral JSON.
- `tools/usb_live.py`: read-only live metadata through the existing serial owner, separate from quota.
- `tools/aim_desktop.py`, `tools/desktop_window.py`, `tools/desktop_support.py`: graphical NOVA control panel and validated actions. Qt mutations stay on the main thread; blocking actions use one worker.
- Desktop tests use an offscreen Qt window with synthetic configuration, without provider requests or hardware writes.
- `scripts/build_windows_release.py`: portable executables, source/notice export and release ZIP.
- `assets/nova/`, `assets/orbit/`: original companion SVGs and logo attribution; generated transparent RGB565+A8 frames.
- `src/ui/theme.h`: four runtime palettes, applied to registered screens and overlays on the UI task.
- `tests/`: synthetic Python/protocol/settings/native UI regressions.

## Commands

Use `.venv\Scripts\python.exe` on Windows or `.venv/bin/python` elsewhere.

Read `docs/PROVIDER_ROADMAP.md` before adding providers. `tools/codex_support.py` prepares the official client only when a user explicitly selects Codex and accepts installation/sign-in. Its account RPC path reads quota without starting model turns. Test onboarding using subprocess fixtures; never log into a real account during development.

Install `scripts/requirements-test.txt` for the workflow permission regression tests. Read `docs/GITHUB_SECURITY.md` before changing workflow permissions or release publishing; build jobs must never receive repository write access.

```text
python -m platformio run -e esp32p4-release
python -m unittest discover -s tests -p "test_*.py"
python scripts/run_tests.py
python scripts/run_tests.py --ui --screenshots work/ui-previews
```

Build first to install pinned ArduinoJson/LVGL. Native tests need C++17; UI also needs C compiler, CMake and Ninja. Use `--cxx`/`--cc` for paths. Flash only when requested, after stopping the companion, using the identified upload port.
Use `setup.ps1 -BuildTools` for development; default setup installs host dependencies only. Source and portable release archives serve different users. Never copy private configurations or recursively export a live project into a release.

## Rules

- USB-only product: never add Bluetooth/BLE, pairing, advertising, GATT or a radio bridge.
- USB attachment alone must not mark a permission transport trusted. Keep real permissions disabled
  until host trust and a supported provider decision interface are independently validated.
- English in project-owned code, documentation and UI.
- UI-task ownership for LVGL/backlight mutations; safe snapshot publication.
- Bounded buffers, strict JSON type validation, frame correlation and partial writes.
- Rollover-safe timing; no repeated NVS writes/redraws for unchanged state.
- Local token increases are activity, not billing or streaming. Dimming does not prove inactivity.
- Test transitions and inspect UI output. Mocks do not establish physical hardware validation.
- Do not read/print real credentials or conversations for debugging; use synthetic fixtures.
- Never add keys, local configs, databases, logs, shortcuts or binaries to Git.
- Preserve bundled license texts byte-for-byte and attribution. MIT grants no trademark rights.
- Check this project is the Git root before mutations; never stage/commit from a parent/global repository.
