# AI Monitor v1.19.1-rc1

Local candidate; not an announcement of a published or physically qualified release.

- Add explicit PC/device permission setup with a separate Claude helper and a default-off preview.
  Production approval stays disabled until physical enrollment/hold/deny/unplug tests pass.
- Connect authenticated developer USB decisions to the existing permission UI and serial owner.
  Cancel stale/hidden/disconnected requests, never retry ambiguous writes, and require a new touch.
- Add opt-in fixed lifecycle history for Codex/Claude, observed session/active-time/turn summaries
  and bounded history protocol 2. Preserve numeric records and unknown values; record no transcripts.
- Add bounded animation format 2 and shared NOVA/ORBIT timing/loop playback through the verified
  renderer/cache. External companion-pack installation remains disabled.
- Add explicit real USB device-screen capture, including ordinary overlays, bounded image transfer,
  private temporary storage and STALE marking. No simulated images, virtual touch or approval.
- Add a read-only CI candidate installer job for clean Windows installation/upgrade/uninstall
  validation without publishing or overwriting a release.

# AI Monitor v1.19.0

This release adds clearer connection checks, optional numeric history and explicitly enabled Claude session events.

- AI connection checklist separates readable local records, last account quota, USB delivery and session reporting. A 60-second observation test follows normal client usage without requesting a model turn.
- Optional local history records observed token increases and quota snapshots for up to 30 days. Daily token/quota charts, numeric CSV export and reset-aware pace estimates are available in History. Collection starts off and uses a bounded background writer.
- Claude Code session-event linking preserves other hooks/statuslines and never makes permission decisions. NOVA/ORBIT and the desktop distinguish Working, Needs you, Turn complete and Session error. Removal invalidates old events; expired/unsupported events fall back to normal token behavior.
- Keep control positions stable, reject stale setup results, separate new baselines from observed increases and surface history storage failures.
- Crop transparent companion margins with a shared renderer, saving 1,046,664 bytes of frame data while retaining the original pose origins. Recover brightness after a transient initial NVS failure without overriding a user's later change.
- Report stalled local token readers and expose free PSRAM for device diagnostics. A permanently blocked reader still requires a host restart; long hardware soak and physical S3 testing remain separate work.
- Contain Windows quota helpers and Codex app-server subprocesses before they begin execution. Kill-on-close Job Objects clean up ordinary descendants on owner exit; failed cleanup prevents another quota worker from starting. Existing interactive client installation/sign-in remains separate.

Update existing displays using Application update to preserve preferences. Session events require the updated firmware; old firmware retains token/quota compatibility. Codex/ZCode and other providers still use recorded token activity, not live session hooks. S3 remains experimental without physical hardware validation. Windows executables remain unsigned; SmartScreen reputation is not guaranteed.

Setup: [Usage insights](USAGE_INSIGHTS.md), [Quick Start](QUICK_START.md), [Provider setup](PROVIDERS.md).

# AI Monitor v1.18.5

This release improves desktop and display interactions, setup failure handling and background-host isolation.

- Keep desktop action positions stable across long messages, busy states, USB scans and provider changes. Separate navigation to AI instructions and the masked Z.AI key; preserve readable scrolling at smaller windows and Windows scaling.
- Keep device button/card slots stable, preserve the provider visible at press start, cancel dragged or failed touch gestures, and restore cancelled setting previews. Align SET and DONE controls across screens and prevent overlapping settings overlays.
- Show healthy local activity accurately, preserve small quota percentages, wrap longer alerts, and distinguish missing host/source signals. Retain provider colors and graph legend colors across themes.
- Share guarded firmware installation between console and GUI. Scope host control to actual program entry points and return accurate setup/diagnostic exit codes.
- Bound quota helpers and their input/output pipes, reap timed-out children before retrying, and move numeric token reads away from the USB owner. Malformed usage cannot disrupt other selected AIs; replaced keys invalidate previous quota verification.
- Retry failed first settings loads and share brightness persistence between boards. Check P4 LVGL timer startup and refuse unverified executable reuse during release packaging.
- Retry bounded identity timeouts when opening USB reboots a slow-starting board. An unavailable or mismatched identity still prevents an application write.
- Require explicit acceptance before installing or signing in to Codex. Identify the legacy quota fallback honestly and clamp over-limit percentages without hiding usage.
- Validate brightness persistence as a boolean, replace complete UTF-8 characters safely, and release the unused Arduino loop task after startup. Pin LVGL and board platforms to immutable commits.
- Generate GitHub build provenance for verified release artifacts in the isolated publisher. This provides build-origin evidence; Windows executables remain unsigned.

Windows binaries remain unsigned. Original Waveshare S3 hardware remains experimental pending physical verification. Interrupted nonbooting applications require First installation, which resets display preferences; PC configuration is retained.

# AI Monitor v1.18.4

Desktop observations and USB scans run in the background so slow local records do not freeze the window. Status refreshes are coalesced; results from an older setup or tray state are discarded. NOVA images are scaled once and changed only when their state changes. Tray Start host now guides ambiguous USB selection through Display setup.

Firmware preparation also runs off the UI thread. The verified board/port confirmation remains mandatory, and the write revalidates files and configuration afterward. A hung flasher is stopped and reaped before retry is enabled, with an explicit warning that firmware may be incomplete. Normal flashing still requires an identified board and FLASH confirmation.

- Evicted historical token records establish a baseline when they reappear; they no longer produce a false burst of activity. The bounded cache accommodates the full local-file snapshot.
- Invalid ZCode key errors identify the environment variable or saved setting without printing the key. Legacy Codex authentication files have a size limit. Action output uses explicit callbacks rather than replacing global stdout.
- Fresh source setup checks an existing Python environment before installing dependencies. The batch launcher rechecks GUI components after setup and reports DLL/import failures instead of silently closing.
- Firmware rejects invalid quota-window/rotation fields and reports oversized input. Dashboard time follows the same 12-hour freshness policy as NOVA. Settings help wraps onto its second line. Snapshot publication follows completed state changes rather than serial chunks.
- Executable version resources are generated from the project version. Desktop, Codex handshake, firmware and release notes are checked for agreement. Installer parsing supports prerelease versions with separate numeric Windows metadata.
- Failed packaging removes its incomplete directory; ZIP publication is atomic. Missing firmware has a direct error. Release reruns preserve existing drafts/assets and verify the downloaded checksums before publication.
- README encoding artifacts are corrected and covered by a regression check.

Synthetic tests exercise real Qt workers, delayed reads/scans, stale results, fragmented local-window messages, child-process timeout/recovery and packaging failure/retry. A controlled 300 ms read-delay fixture reduced maximum visible event-loop delay from 284 ms to 2.5 ms; it does not measure real provider latency. See [performance evidence](DESKTOP_PERFORMANCE.md).

An application-only firmware update keeps existing display settings. Windows binaries remain unsigned, and SmartScreen may still warn. Physical S3 support remains experimental. No monitor test or quota check starts a model turn.

# AI Monitor v1.18.3

Codex onboarding explicitly explains the fresh-PC route: choose Codex, accept official standalone CLI installation if missing, complete your own browser sign-in and start the host. The app and guides list bundled runtime components and distinguish Windows releases from source/developer setup. No separate Python, Node.js or Git installation is needed for the Windows monitor route.

A disposable Windows CI check performs the official client installation with isolated Codex state and no Node/Python commands on PATH. It checks executable discovery and login status and declines personal sign-in. The release build runs this check before packaging; the test requests no model turn or USB write. Windows monitor binaries remain unsigned. Updated Windows 10 is best effort for Codex; Windows 11 is recommended.

This version includes the setup/status and bounded numeric-read improvements below. Existing displays remain compatible; no firmware update is required for these desktop changes.

# AI Monitor v1.18.2

AI setup diagnostics distinguish readable local activity, a configured key or CLI, and the running host's last quota result. Instructions point to the actual desktop actions and describe when a bridge is required. Claude link status is checked without changing client settings. No model request is generated by this check.

- A host waiting for USB now leads to live connection/provider status instead of suggesting another serial probe. The main host button says **Restart host** when it will restart an existing process.
- The first-run checklist waits for a board choice before calling USB selected.
- Codex and ZCode SQLite reads now have an execution budget, so a slow unindexed query can be interrupted. Interrupted reads report the source unavailable; they do not return partial usage or change the database. Normal reads and recovery are covered by synthetic tests.
- The setup guide uses the correct Codex action and explains activity-only providers and quota diagnostics.
- ZCode without a quota key now reports activity-only status, clears obsolete quota backoff and makes no quota request. Usage completion messages also cover activity-only providers without claiming quota was received. Console and source-setup instructions point to the current actions.

The host remains compatible with existing v1.17.2/v1.18.1 displays; no firmware update is required for these desktop changes. Windows binaries remain unsigned and S3 remains experimental. See docs/DESKTOP_PERFORMANCE.md for measured results and limits.

# AI Monitor v1.18.1

The Windows app can minimize to the original NOVA icon in the system tray. Click the icon or open the shortcut again to restore the existing window. Right-click the icon for Open, Start host, Stop host and Quit; the Quit label states whether the host will keep running or stop.

Setup now has a progress checklist and a Next button for board, USB, provider selection, saving and identity checking. Ambiguous USB selection is shown before starting. A failed identity check guides to firmware/USB help without writing anything automatically. Automatic start reuses an already running host rather than restarting it and issuing another quota request.

- **Host settings** saves Minimize to tray (on by default) and Close button hides in tray (optional, off by default). Normal close behavior is retained unless explicitly changed.
- Hiding retains unsaved selections/key input and preserves window size/maximized state. It never stops the independent host. UI token-database polling pauses while hidden; the tray shows lightweight USB/host status.
- A new launch restores the existing window instead of creating duplicate icons. The local handoff uses a per-installation lock and a user-restricted local pipe; only fixed window/page commands are accepted. No TCP listener, host control, credential reply or file request is exposed.
- Errors from a hidden background action reopen the app. Quit waits for ongoing work, confirms unsaved changes, and respects the saved host stop/keep setting. Ctrl+Q is an explicit Quit shortcut. If a tray is unavailable, normal window behavior remains available.

The Windows host works with existing v1.17.2 displays; a firmware update is not required for tray support. Windows binaries remain unsigned and S3 remains experimental.

# AI Monitor v1.17.2

Windows command discovery now ignores npm's extensionless POSIX shell launcher and selects a Windows `.exe` or supported `.cmd`/`.bat` wrapper instead. This fixes Codex quota reads from an Explorer-launched app when the development terminal had a different PATH. Existing Codex sign-in is reused; no new account or key is imported.

A full uninstall, flash erase and GUI first-installation test found a P4 bootloader defect that application-only updates did not expose: the factory image declared 4 MB flash while its board and partition table require 16 MB. The write/hash check succeeded, but the board then boot-looped. The build now explicitly sets the image header to 16 MB.

- Packaging and first-installation preflight validate the bootloader flash capacity, partition checksum, bounds, alignment, overlap and application fit. Valid file hashes alone are insufficient to approve an image.
- Factory validation runs before collecting firmware and before invoking a flasher. Existing application-only updates remain separate.
- Disabled primary buttons now look disabled during a firmware write. Closing the window during writing remains blocked.
- Firmware completion reports a started process and asks users to check USB/provider health, rather than claiming the display is already connected. It respects the saved stop-on-close preference.
- The multiple-port warning no longer incorrectly claims a previous host exists.

v1.17.0's P4 factory image must not be used for new installations. Published assets have not been overwritten. Windows binaries remain unsigned, and S3 still requires physical validation.

# AI Monitor v1.17.0

The Windows host now separates background-process status, verified USB connection and provider quota health. Two matching devices no longer produce a misleading successful start. Select the display port explicitly; the existing host is preserved when preflight fails.

- New **Host settings**: USB retry interval, local token read interval, terminal text size, opt-in start when opening the app, and keep/stop host when closing it. No Windows service or startup task is installed.
- **Check connection** reads the display identity without writing firmware or requesting AI quota. A busy host is left alone; wrong hardware and missing firmware get actionable instructions.
- Codex discovers its official per-user native installation even when an Explorer-launched app has an older PATH. Account quota uses read-only CLI RPC, with no model turn.
- **Check AI setup** checks each selected local token source from the app. Unsupported automatic editor integrations are explicitly labeled; no account quota is fabricated.
- A dedicated **AI setup** tab keeps provider choices, instructions and key entry separate from the display connection controls. **Provider setup** opens that tab; Codex has its own official install/sign-in action.
- Claude's optional subscription quota link can be installed and removed in Setup. Installation is idempotent, keeps a private backup, and preserves custom statuslines. The frozen GUI always targets the console helper.
- OpenCode has a built-in read-only numeric SQLite adapter for documented V1 message and V2 session usage. No integration script is needed for these schemas. NOVA/ORBIT Settings explains its activity-only support.
- USB selection shows device descriptions. Rescanning preserves the explicit port and no longer marks unchanged settings as unsaved.
- Saved USB changes interrupt disconnected retry waits promptly. Local token polling stays independent of quota refresh; provider backoff survives USB reconnects.
- Corrupt local configuration opens the app's recovery screen. Explicit recovery backs up the original private bytes locally before resetting; valid configurations cannot be reset this way.
- Unsaved changes are checked before closing. Firmware errors retain their specific instructions instead of a generic failure.
- Local health snapshots use fresh process IDs and bounded atomic files. Keys, prompts, account replies and telemetry databases are excluded from release exports.

The default remains: no board/provider preselection, no automatic host start, and the host keeps running after closing the app. Installer upgrades preserve private settings. The new Windows host also works with existing v1.16.1 displays; the firmware update adds revised provider guidance in Settings.

**Windows trust:** binaries remain unsigned. No Windows security controls are disabled. Trusted signing/reputation requires a real publisher certificate and cannot be replaced by version metadata.

# AI Monitor v1.16.1

- **SET > AI USAGE** explains each provider's quota windows and PC setup. Each choice shows remaining quota and REPORTED/NOT REPORTED/OFFLINE/ERROR/UPDATING/STALE status.
- Known windows can be selected while waiting for data, without fabricated percentages. Live values update in Settings without rebinding touch targets; REFRESH reloads choices explicitly.
- ZCode now includes the monthly MCP tool quota and correctly labels its model weekly quota as 7 DAYS. Monthly MCP is not a monthly model-token budget.
- Missing-data, live-update, quota selection, text layout and ZCode API fixtures are covered by regression tests.

# AI Monitor v1.16.0

The NOVA/ORBIT companion panel is narrower, leaving more room for readable AI status and usage on the right. The robot keeps its original size and is recentered by trimming transparent canvas margins.

- Companion card: 430 to 350 pixels wide. Provider area: 310 to 390 pixels wide.
- Percentages: 26 to 40 pixels. Provider names: 14 to 20 pixels. Quota-window/status text: 12 to 16 pixels.
- Larger activity headings, token messages and navigation captions, with checks for clipping and overlap across every provider and tiny/full/LOCAL values.
- Updated actual LVGL previews for NOVA, ORBIT and the four themes.
- 29 linked project badges in README, including live release/commit/build/star badges and accurate board, provider, feature and privacy information. Experimental/activity-only integrations remain explicitly labeled.

The previous per-provider **SET > QUOTA WINDOW** preferences, larger notifications and guided Windows installer remain available. Existing selections survive application updates; missing windows remain unavailable and alerts still watch all windows.

- Larger notifications: 136-pixel banner, 24-pixel heading, 20-pixel quota text and a 60-pixel-high DISMISS button.
- Visible instructions for all eight AI choices, including ZCode's Coding Plan key, official Codex/Claude setup and activity-only bridge requirements.
- **AI-Monitor-Setup-v1.16.0-windows.exe** installs the complete app for the current user and opens setup. No Python, PlatformIO or administrator rights are required. The portable ZIP remains available.
- Double-clicking the command-line firmware helper explains its purpose and offers to open the graphical Firmware tab. Writes retain progress/error messages; the app cannot close during a write and can start the host after success.
- Packaged Qt diagnostics invoke the exact flasher child on both images without USB writes. Installer checks cover clean setup, runtime startup, upgrade and settings-preserving uninstall.
- The independent host keeps running after closing the app, until stopped, sign-out or shutdown. Private keys/configuration are not distributed.

**Windows trust:** this release is unsigned. SmartScreen may warn; version metadata and an installer do not replace trusted signing/reputation. Windows protections remain enabled. See the Windows trust guide included in the package.

**Hardware:** P4 and the original Waveshare S3 have separate firmware. S3 remains experimental and unverified on physical S3 hardware; B/C variants are unsupported. Use an application update on an existing AI Monitor to retain settings; First installation resets them. Stop a portable host from its original folder before switching to the installer version.
