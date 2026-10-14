# v2 completion status — v1.19.1-rc1

This candidate continues the USB-only v2 foundation. It is not a claim that every physical/security
release gate has passed. Use the version shown by the installed app/device to distinguish it from
the older v1.19.0 downloads. Source, PC executables and normal firmware share v1.19.1-rc1.

| Area | Implemented | Validation / remaining gate |
| --- | --- | --- |
| USB permissions | UI-to-serial final commit, authenticated developer adapter, explicit PC/display opt-in, separate Claude setup/removal | Native real-crypto/LVGL tests pass. Production remains disabled pending physical enrollment/hold/deny/unplug/provider testing postponed by the user. |
| AI monitoring | Codex/ZCode quota and recorded token activity; documented Codex/Claude observational integrations | Installed host reports both selected providers ready on real P4. CLI hooks are active; natural turn lifecycle delivery still needs a real-client observation. ZCode detailed phases are unavailable without a documented source. |
| History | Opt-in bounded lifecycle journal, migration, observed sessions/active time/turns, Today/24h/7d | Native/SQLite/USB tests pass. Waiting/gaps excluded, parallel activity unioned, no transcripts or invented task results. Existing user's preference stays off. |
| Companions | Bounded animation schema 2, mood timing/loops and built-in playback over LZ4/PSRAM cache | Native parsing/player/LVGL tests pass; normal P4 flashed. External pack installation remains a future storage/staging/recovery feature. |
| Device mirror | Real device RGB565 capture, normal overlays, existing USB owner, explicit PC viewer | Physical P4 capture: 3.094 s directly, 4.922 s through installed host. PSRAM returned to the same free value. Protected screens excluded; no touch/approval. |
| Packaging | Both board images, five rebuilt Windows executables, checksummed portable ZIP and per-user installer | Actual installer upgrade/startup passed on the existing PC, settings unchanged. A read-only CI workflow can verify clean-profile installation/upgrade/uninstall without release publication. |

493 Python tests and four native LVGL targets pass. P4 normal/developer and S3 firmware builds pass.
18 frozen modules were compared against tested source. The P4 application-only update was backed up,
written and digest-verified; NVS, bootloader and partition table were preserved. S3 has no physical
hardware validation. A long-duration soak is not established by these shorter checks.

Windows binaries remain unsigned. No usable code-signing certificate was found on this PC; compiler
checksums and Microsoft file review are not a publisher signature. Do not disable SmartScreen,
install a fake trusted root or describe unsigned artifacts as signed.

Later v2 items remain deliberately separate: confirmed build/test/task outcomes, Git status, audio,
public companion-pack installation and configurable layouts. Bluetooth remains permanently excluded.

Evidence and contracts: [validation log](V2_VALIDATION.md), [permissions](USB_PERMISSION_HELPER.md),
[history](DEVICE_HISTORY.md), [animations](COMPANION_ANIMATIONS.md), [mirror](DEVICE_MIRROR.md).
