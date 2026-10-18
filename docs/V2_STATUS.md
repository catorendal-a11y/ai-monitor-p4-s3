# Current distribution

rc18 ships `nova-v1.19.1-rc18-windows-x64-terminal.zip`: NOVA terminal source with a
verified private Python runtime and hash-locked dependencies for offline Windows setup.
It replaces the graphical app and NOVA EXE distribution; double-click `Install-Nova.cmd`, then
open a new terminal and type `nova`.
See TERMINAL.md and RELEASE_NOTES.md. Physical approval stays disabled.

## Historical development evidence

# v2 completion status — v1.19.1-rc14

This candidate continues the USB-only v2 foundation. It is not a claim that every physical/security
release gate has passed. Use the version shown by the installed app/device to distinguish it from
older downloads. Source, PC executables and normal firmware share v1.19.1-rc14.

Rc14 packages the interactive terminal with full-color quota bars, original NOVA
cell artwork, observed sessions, history trends and the shared desktop operations.
It fixes monochrome startup, short-window layouts and invalid draft handling.
See [terminal installation and startup](TERMINAL.md). Install once and type `nova`.
The full Windows package uses its existing console helper's bundled runtime;
source-only installs prepare a Python environment. No sixth executable is introduced.

The rc11 connected-runtime endurance measurement completed 28,800 seconds with
5,737 samples and zero failed samples. This is version-specific rc11 evidence,
not an rc14 soak or validation of physical permission approval, S3 touch or unplug/suspend.

Rc11 adds fixed primary navigation and separates observed agent sessions from selected
quota providers. Session rows expose a short ID; an empty acknowledged feed differs
from an unavailable feed.

Rc10 audits desktop and firmware UI action/state flows. It preserves quota errors
alongside session signals, expires old agent presentation, aligns daily history on
local calendar boundaries, explains unknown metrics, adds explicit history clearing
and bounded diagnostics, and scopes upgrade/uninstall cleanup to this installation.
Companion activation requires the saved board and port. Builds and source tests do
not establish physical approval, signing, clean-profile or long-endurance gates.

Rc9 fixes the three follow-up audit defects: alternate Claude profile paths,
transient configuration-read recovery and scalar NVS read/save confirmation.
Profile setup/removal/readers share one resolver; config reads retry with backoff;
scalar settings join the existing atomic NVS load gate.

Rc8 fixes eight further logic defects: stale history consent renewal, recovery-copy
ACLs, partial configuration saves after revocation failure, lease-renewal event loss,
task-list identity collisions, invented zero outcomes after cancellation, replacement
during pending companion adoption, and partial NVS reads. Old task rows remain;
mixed legacy/new identity metrics stay unknown where deduplication is impossible.
Release evidence remains version-specific.

Rc7 fixes the nine functional-audit defects: sensitive-file ACLs/backups, stop/crash
history consent, midnight outcomes, dormant-journal retention, elapsed agent and
token age, uncertain pack activation, quota fallback text and EVENTS back navigation.
Existing physical approval, clean-profile installer and signing gates stay separate.

Rc6 adds data-only companion import, a bounded persistent PC library and automatic
USB restoration into two preallocated P4 RAM banks. Only a complete, decoded/hash-
verified pack can be adopted by the UI owner. Interruptions retain the old pack.
Built-ins remain available; S3 does not advertise external pack support.

Claude client task counts now come from verified successful TaskCreate/TaskUpdate
post-tool results, separately from turns and pre-veto hooks. Unknown provider or
failure metrics remain unknown. The PC daily table/CSV and schema-3 P4 history
carry only counts. Old history schemas remain supported. The exact packaged
client/device tests and endurance result are recorded separately from source tests.

Rc5 fixes ZCode lifecycle events being silently omitted from opt-in history. The
desktop History tab now displays and exports daily observed sessions, active
seconds and completed/failed turns for seven/30 local days, with the latest day
first. Unknown values remain unknown and midnight outcomes belong to one day.
The suite passed 529 Python tests and all native checks. Coverage of the three
changed Python modules is 93% combined. This does not turn lifecycle hooks into
confirmed task outcomes, enable physical approvals or install external packs.

Rc4 fixes a failure found with the actual Windows Codex client: command hooks
need PowerShell's call operator before the quoted observer executable. The exact
older wrapper can be migrated without changing custom hooks or bypassing the
client's normal hook trust review. Actual local Codex and ZCode turns returned
OK and delivered WORKING/COMPLETED through the installed host's live USB channel.
A separately configured Claude Code client using Z.AI GLM also passed a real
reply and a Read-tool fixture round trip, including READING/COMPLETED events.
This establishes the tested client paths, not every tool, model or client surface.
GLM access does not provide native Anthropic Claude models or plan quotas.

Rc3 adds ZCode's documented lifecycle observer, an independent event reader, visible
agent USB acknowledgment/error status, actual hook-definition checks and exact legacy
Codex wrapper migration. Synthetic regression evidence and new build/deployment results
are separate from the historical rc1/rc2 physical checks below. Acknowledging a live
packet does not establish genuine client delivery. Existing provider selections and
physical-approval gates are preserved.

The rc2 audit fixes post-handshake USB cleanup, screen-capture response ownership,
persistent capture errors, malformed capture correlation and long dashboard status
visibility. Earlier physical results below describe rc1; rc2 build/deployment
results must be recorded separately rather than inherited from that candidate.

| Area | Implemented | Validation / remaining gate |
| --- | --- | --- |
| USB permissions | UI-to-serial final commit, authenticated developer adapter, explicit PC/display opt-in, separate Claude setup/removal | Native real-crypto/LVGL tests pass. Production remains disabled pending genuine physical enrollment/hold/deny/unplug/provider testing. |
| AI monitoring | Codex/ZCode quota and recorded token activity; documented Codex/Claude/ZCode observational integrations | Installed rc4 host reports Codex/ZCode quota ready on P4. Real local client turns and live USB delivery passed for all three observers; Claude Code with GLM remains activity-only for Claude quota. Local Codex command hooks do not cover cloud-orchestrated Work. |
| History | Opt-in bounded lifecycle/task journal, migration, observed sessions/active time/turns, confirmed Claude client task transitions, Today/24h/7d and desktop daily summary/CSV | Native/SQLite/USB and desktop tests pass. Waiting/gaps excluded, parallel activity unioned, no task text or invented results. Task completion is a client report, not proof that tests passed. Unsupported task metrics remain unknown. |
| Companions | Bounded animation schema 2, PC import/library, staged existing-owner USB transfer, UI activation and LZ4 cache | Native parsing/player/transfer/LVGL tests and both board builds pass. P4 owns preallocated active/staging banks; PC storage restores the selection after restart. No display filesystem formatting or microSD dependency. Physical validation is distinct from native evidence. |
| Device mirror | Real device RGB565 capture, normal overlays, existing USB owner, explicit PC viewer | Physical P4 capture: 3.094 s directly, 4.922 s through installed host. PSRAM returned to the same free value. Protected screens excluded; no touch/approval. |
| Packaging | Both board images, five rebuilt Windows executables, checksummed portable ZIP and per-user installer | Actual installer upgrade/startup passed on the existing PC, settings unchanged. A read-only CI workflow can verify clean-profile installation/upgrade/uninstall without release publication. |

The rc4 suite passed 521 Python tests and the complete native protocol/settings/history/USB/LVGL/mirror
checks. Both release firmware targets and all five Windows executables were rebuilt from source.
The rc4 P4 application-only update was backed up, written and independently digest-verified;
NVS, bootloader and partition table were preserved. Package contents, firmware manifests,
installer/ZIP SHA256 and ZIP CRC passed verification. The installed host reconnected to COM6 with
acknowledged live USB after its stale login task was updated to the installed executable and
invoked successfully. This tests the scheduled action, not a complete Windows reboot. S3 has no
physical hardware validation. A long-duration soak is not established by these shorter checks.

Windows binaries remain unsigned. No usable code-signing certificate was found on this PC; compiler
checksums and Microsoft file review are not a publisher signature. Do not disable SmartScreen,
install a fake trusted root or describe unsigned artifacts as signed.

Later v2 items remain deliberately separate: confirmed build/test results, additional providers'
task outcomes, Git status, audio and configurable layouts. Bluetooth remains permanently excluded.

Evidence and contracts: [validation log](V2_VALIDATION.md), [permissions](USB_PERMISSION_HELPER.md),
[history](DEVICE_HISTORY.md), [animations](COMPANION_ANIMATIONS.md), [mirror](DEVICE_MIRROR.md).
