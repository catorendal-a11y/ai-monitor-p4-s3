# v2 completion status — v1.19.1-rc5

This candidate continues the USB-only v2 foundation. It is not a claim that every physical/security
release gate has passed. Use the version shown by the installed app/device to distinguish it from
the older v1.19.0 downloads. Source, PC executables and normal firmware share v1.19.1-rc5.

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
| History | Opt-in bounded lifecycle journal, migration, observed sessions/active time/turns, Today/24h/7d and desktop daily summary/CSV | Native/SQLite/USB and desktop tests pass. Waiting/gaps excluded, parallel activity unioned, no transcripts or invented task results. Collection requires opt-in; saved numeric history can be read without restarting collection. |
| Companions | Bounded animation schema 2, mood timing/loops and built-in playback over LZ4/PSRAM cache | Native parsing/player/LVGL tests pass; normal P4 flashed. External pack installation remains a future storage/staging/recovery feature. |
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

Later v2 items remain deliberately separate: confirmed build/test/task outcomes, Git status, audio,
public companion-pack installation and configurable layouts. Bluetooth remains permanently excluded.

Evidence and contracts: [validation log](V2_VALIDATION.md), [permissions](USB_PERMISSION_HELPER.md),
[history](DEVICE_HISTORY.md), [animations](COMPANION_ANIMATIONS.md), [mirror](DEVICE_MIRROR.md).
