# Application updates, USB firmware updates and beginner setup

Research date: 2026-10-11. Status: design proposal, not an implemented automatic updater. This review does not authorize downloading or executing a new installer, changing repository permissions, or flashing a display.

The existing **Firmware > Install / update firmware** flow already writes bundled, verified firmware over USB. The proposed addition is discovery and verified delivery of a newer Windows application release. Installing the application and updating the display must remain separate, explicit actions. There is no Wi-Fi OTA updater in this design.

## Current implementation

| Area | What the reviewed source already does | Remaining boundary |
| --- | --- | --- |
| Windows package | Bundles the Python/Qt/serial runtime, console helper, flasher and both board images. The package and installer builder verify the packaged file hashes. | Local package hashes do not independently authenticate a downloaded publisher. The current installer configuration does not enable Authenticode signing. |
| Per-user upgrade | `scripts/windows_installer.iss` keeps a constant AppId, installs with `PrivilegesRequired=lowest`, and excludes private host configuration, status, logs and activity files from copied release files. | Application shutdown/restart and interrupted-upgrade recovery need explicit updater coordination. A portable folder is not automatically an installed application. |
| Firmware preparation | `tools/desktop_support.py` resolves the saved board/port, verifies the files through `tools/aim_control.py`, and asks the user to review the board, operation and port and type `FLASH`. | A remote firmware package would need the same release-authentication gate as the application. |
| Firmware write | Revalidates files and port after confirmation, stops only the owned host, verifies the existing project's board identity for an application update, and bounds/reaps the flasher process. | First installation resets display settings. A failed update that no longer boots cannot currently satisfy the normal application-update identity probe. |
| Provider setup | Fresh installations select no AI. Codex has an explicit installation/sign-in action; ZCode has an optional masked quota key; Claude has a confirmed quota-link action. | Selection does not install every provider, create an account, grant entitlements, or supply an external integration. |

Source references: [desktop UI](../tools/desktop_window.py), [validated firmware actions](../tools/desktop_support.py), [installer](../scripts/windows_installer.iss), [package verification](../scripts/build_windows_installer.py), [provider readiness](../tools/provider_setup.py), [provider guide](PROVIDERS.md).

## Recommended rollout

1. **Check and notify:** add a manual **Check for updates** action, then an opt-in background check. Show the current and offered version, a plain-text summary, and **Open official release**. No executable is launched by a check. An offline or rate-limited check must not stop the host.
2. **Verified application update:** after signing/provenance and upgrade-recovery prerequisites pass, offer **Download verified update** and then **Install and reopen**. Keep the Windows installer visible. A background check is not consent to install.
3. **USB display update:** after the PC upgrade, compare the connected display's version and compatibility to the newly installed, verified bundle. Offer a separate **Update display** action using the existing board/port review and `FLASH` confirmation. Never flash merely because the app updated or a USB device appeared.

The current unsigned releases should initially use stage 1. If the executable has no acceptable publisher/provenance evidence, leave installation to the explicit official-release download flow; do not silently lower a future verification requirement.

## Fixed release source and metadata

The updater's owner/repository must be compiled constants: `catorendal-a11y/limitbuddy`. The settings screen must not accept an arbitrary feed, executable URL, command, plugin or installation script.

Use the public GitHub REST latest-release endpoint without a GitHub token. Validate the returned release rather than assuming that the endpoint means a higher version: accept only a strict stable `vMAJOR.MINOR.PATCH`, reject draft/prerelease flags, and numerically compare against the running version and the highest previously accepted verified version. Reject downgrades and unexpected asset names. Do not interpret `target_commitish` as a verified commit SHA; it can identify a branch. [GitHub release REST API](https://docs.github.com/en/rest/releases/releases#get-the-latest-release).

Allow exactly one expected Windows installer asset, such as `AI-Monitor-Setup-v<version>-windows.exe`, plus a bounded manifest/checksum/provenance bundle. Require matching release tag, version, platform and asset ID. Display release notes as inert plain text, never as executable instructions or active HTML. Cache an ETag, use conditional requests, and respect rate-limit/backoff headers. Proposed defaults are one background check per day, a manual retry, bounded response sizes and explicit connection/read/total deadlines. These defaults are project design choices. [GitHub REST best practices](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api).

Start downloads from the validated API asset endpoint or exact repository/tag asset path. GitHub documents that binary downloads may return either a direct response or a redirect. Validate every redirect: HTTPS only, no URL credentials, no IP-literal/local target, bounded redirect count, and exact approved GitHub release-delivery hosts such as `release-assets.githubusercontent.com`. This CDN is delivery for the approved repository, not permission to accept arbitrary assets hosted there. Tie the file to its already validated asset ID, size and hash. A changed or newly required delivery host must cause an actionable failure until reviewed; do not broaden to `*.githubusercontent.com`. [GitHub release assets](https://docs.github.com/en/rest/releases/assets#get-a-release-asset).

Download to a fresh per-user staging directory with a fixed local filename, enforce a product-specific size cap, stream SHA-256 calculation, and atomically rename only after verification. Never derive filesystem paths from release descriptions or unvalidated asset names. The updater sends no provider keys, local configuration, token records, logs or machine identifiers to GitHub. It requires no inbound network listener.

## Integrity, provenance and publisher authentication

Three checks serve different purposes:

| Check | What it establishes | What it does not establish |
| --- | --- | --- |
| Asset SHA-256 and byte count | Downloaded bytes match the accepted expected bytes. | That the publisher or its release account has not been compromised. |
| Cryptographically verified release/build provenance | The artifact is bound to the expected repository, release/source identity and, for build attestations, allowed workflow identity. | That the source has been audited or that the artifact is malware-free. |
| Trusted Authenticode publisher signature | Windows validates the executable's signing chain and the updater can require the approved publisher identity. | Immediate SmartScreen reputation or immunity from malicious software signed by a compromised publisher. |

GitHub includes an asset `digest` field in release metadata. Compare a valid `sha256:<64 hexadecimal digits>` with the computed digest and the reviewed release manifest; missing or mismatched required data blocks the verified-install action. A `SHA256SUMS.txt` downloaded from the same mutable release is useful integrity evidence, not a separate trust anchor. [Release asset digest schema](https://docs.github.com/en/rest/releases/assets).

Prefer immutable releases. GitHub documents that these lock published assets and tags and generate a release attestation binding tag, commit and assets. Draft creation followed by attaching every reviewed asset and publishing is compatible with this project's delivery flow. Do not assume existing releases are immutable until that property is verified. [Immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases), [release integrity verification](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/verify-release-integrity).

For build attestations, require the exact repository and expected release workflow, source ref/tag and source digest, and reject self-hosted provenance. The official verifier supports those constraints. Do not accept any attestation merely because it is cryptographically valid, and do not trust arbitrary workflow-controlled predicate text as the signer identity. [GitHub attestation verification policy](https://cli.github.com/manual/gh_attestation_verify).

Beginner installations must not require GitHub CLI or a GitHub login just to update. Select and review a verifier bundled with the app, or a detached-signature verifier with a public key shipped in the app. Publish verification bundles with the allowlisted release assets; ship the required trust roots. The documented offline-verification route has root-rotation/revocation limitations that must be handled explicitly. Never download an unsigned new verifier and run it to decide whether a different download is safe. [Offline attestation verification](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/verify-attestations-offline).

Authenticode verification should use the Windows trust API with a reviewed publisher policy, timestamp/revocation handling, and an explicit key/certificate rotation plan. Accepting any trusted publisher would be too broad. Hash/publisher revalidation must happen immediately before launch, not only when downloading. [Microsoft WinVerifyTrust](https://learn.microsoft.com/en-us/windows/win32/api/wintrust/nf-wintrust-winverifytrust).

Windows certificate validation may contact OS-managed certificate/status services. These must never become update-feed or executable-download sources. If a deployment forbids those requests, define a cache-only trust policy and block verified installation when the required revocation evidence is unavailable; do not silently call an unknown trust result successful.

The v1.18.5 release workflow prepares build attestations in its isolated publisher, after checksum verification. Build jobs remain read-only; only the publisher receives dedicated OIDC/attestation permissions. Verify the actual published artifact's provenance before relying on it. This does not implement an in-app verifier or automatic updater. Follow [GITHUB_SECURITY.md](GITHUB_SECURITY.md), full-SHA action pins and exact artifact identity checks; never give normal builds repository content-write credentials. [GitHub build attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).

## Installation and interruption handling

Use the existing per-user Inno installer instead of teaching the GUI to replace its own running DLLs. Keep its AppId stable. A small bundled updater coordinator may wait outside the installation directory, but must accept only a validated installation identity and verified installer file; it must not provide a generic command/URL execution interface. Launch with a fixed argument list, never a shell command from remote metadata. [Inno AppId](https://jrsoftware.org/ishelp/topic_setup_appid.htm).

The **Install and reopen** dialog must explain that the GUI and its owned host will temporarily stop. Require no flash/action in progress and handle unsaved edits before shutdown. Preserve a private local configuration backup and schema compatibility, use the existing scoped process ownership checks, then exit the GUI normally. Never stop unrelated serial tools or another installation's host.

The current installer uses `CloseApplications=yes` and `RestartApplications=no`. Inno uses Windows Restart Manager, and automatic restart requires the application to register for restart. Therefore a successful installer exit alone is not evidence that this independent Python host resumed. Coordinate one explicit reopen and restart only if the same owned host was running before, with the saved user preferences and no simultaneous duplicate instance. Keep install UI and OS security prompts; do not use forced-close or silent flags as a shortcut. [Inno CloseApplications](https://jrsoftware.org/ishelp/topic_setup_closeapplications.htm), [RestartApplications](https://jrsoftware.org/ishelp/topic_setup_restartapplications.htm), [installer command-line options](https://jrsoftware.org/ishelp/topic_setupcmdline.htm).

After installation, verify the actual installed app version and packaged manifest, reopen it once through the existing single-instance path, and report connection/provider readiness separately. Cancellation must leave the old app available; interrupted/failed replacement needs a visible recovery path and validated last-known-good installer. Do not treat copying old executables over a partly updated runtime as a safe rollback. A rollback after configuration migration requires a reviewed compatibility/recovery procedure, not an automatic downgrade exception.

Treat portable installations separately. Do not redirect a portable user's update into the default installed-app folder or silently copy private settings between installations. The first updater can support installed copies only and show an explicit migration/download guide for portable copies. A later portable update path needs bounded extraction, path/symlink checks, an atomic version-directory switch and a reviewed private-state migration.

## USB firmware preservation and recovery

Application installation updates bundled firmware files on the PC; it does not touch device NVS. An application-only USB flash preserves the device settings only when the existing project identity and compatible partition layout have passed validation. A factory demo, different project or wrong board must not enter that path. Select the saved board, verify the responding board/chip and all image/manifest hashes, require a newer compatible firmware version, and show the exact COM port before confirmation. A newer PC app should clearly indicate when its features require a display upgrade.

First installation is intentionally different: it writes the required factory layout and resets display settings. Keep that consequence visible and never substitute it silently for a failed update. If an interrupted application flash prevents the firmware identity probe, offer the documented first-install recovery with explicit reset consent. A settings-preserving bootloader recovery option remains future work and would require reading and verifying the existing chip/partition layout first. S3 remains experimental until physically validated on the original supported CH422G board; B/C variants are not supported.

## Practical provider onboarding limits

The Windows monitor runtime is bundled. That does not mean every external AI client, account or subscription is included. No provider is preselected, and checking for software updates must not scan/login/poll additional providers.

| Provider | Supported beginner path in this program | What cannot be completed silently |
| --- | --- | --- |
| Codex | Select/save, then **Install / sign in Codex** offers the official standalone CLI route when missing. Existing compatible clients are reused. | Own account, browser sign-in and any vendor installation confirmation. Subscription quota requires suitable ChatGPT-backed access; API-key billing is distinct. |
| ZCode | Select/save; local supported token activity needs no monitor key. **Enter Z.AI key** opens the masked optional quota field. | User installs/signs into ZCode and creates the correct own coding-plan key. A present key is not proof of received quota; wrong/expired/plan-incompatible keys remain unavailable. |
| Claude Code | Local CLI activity reader; confirmed **Link Claude quota** action preserves unrelated settings/custom statuslines. | Official client sign-in, restarting Claude Code, and resolving an existing custom statusline. Rate-limit windows may be absent depending on account/session. |
| Gemini CLI | Local recorded-session activity reader after the official client is used. | Client installation/sign-in. This project has no remaining-account-quota adapter; do not fabricate a 5-hour/monthly choice. |
| OpenCode | Supported local SQLite numeric reader after the official client is used. | Client/provider account setup. No remaining-account-quota adapter is implemented here. |
| GitHub Copilot | Existing numeric ingestion bridge for an external integration. | Selection alone cannot import all editor activity. SDK usage events are a possible scoped adapter, not automatic editor-wide coverage. |
| Cursor | Existing numeric ingestion bridge. | No built-in personal-quota adapter; documented team Admin APIs are not equivalent to a personal monitor. |
| Antigravity | Existing numeric ingestion bridge. | Its interactive usage command does not by itself supply this project's automatic adapter. |

Primary provider references: [Codex authentication](https://learn.chatgpt.com/docs/auth), [official Codex CLI](https://learn.chatgpt.com/docs/codex/cli), [Z.AI coding-plan key setup](https://docs.z.ai/devpack/quick-start), [Claude statusline quota fields and availability](https://code.claude.com/docs/en/statusline), [Gemini session storage](https://geminicli.com/docs/cli/session-management/), [OpenCode CLI](https://docs.opencode.ai/docs/cli/), [Copilot SDK usage events](https://github.com/github/copilot-sdk/blob/main/docs/features/usage-and-billing.md), [Cursor team Admin API](https://prod.cursor.com/docs/account/teams/admin-api), [Antigravity usage command](https://www.antigravity.google/docs/cli/commands/usage/).

Device quota choices should list only available provider-reported windows. Codex can report 5-hour/7-day windows; ZCode labels depend on the supported plan reply. Local token counts, context occupancy, account remaining percentages and billing are different data. Keep **Not configured**, **Activity available**, **Quota pending**, **Quota received**, **Quota unavailable** and **Bridge required** distinct. An empty source or successful installer is not a successful quota test. See [CODEX_SETUP.md](CODEX_SETUP.md), [PROVIDERS.md](PROVIDERS.md) and [PROVIDER_ROADMAP.md](PROVIDER_ROADMAP.md).

## Windows warnings and signing decision

Authenticode signing is needed for a dependable verified publisher gate, but does not promise immediate SmartScreen approval. New signed binaries may still warn; EV certificates no longer provide an automatic reputation bypass. Consistent signing identity matters. Do not disable Defender/SmartScreen, remove security marks to bypass checks, ask users to install a project root certificate, or describe an unsigned file as Microsoft-approved. [Microsoft SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation).

Evaluate a qualifying open-source signing program, an appropriate CA certificate, or a supported Microsoft signing/Store route. Microsoft's current guidance notes geographic/identity eligibility restrictions for its signing service, so a Norwegian individual developer must verify eligibility rather than assume availability. Store MSIX is a separate packaging/distribution project; it does not automatically certify the current EXE installer. [Microsoft signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options).

## Acceptance before shipping an updater

- Synthetic tests reject wrong repository/identity, unexpected redirects, downgrade/replay, malformed metadata, duplicate assets, missing provenance, wrong publisher, digest/size mismatch and changed files immediately before launch. No failure starts an installer or flasher.
- Checks/downloads remain responsive and cancellable; one check coalesces repeated clicks. Offline/429/timeouts leave the existing host and private files unchanged. The updater has no inbound listener or remote-script interpreter.
- Disposable Windows tests cover fresh install and upgrade with realistic unrelated COM ports, unsaved edits, running/stopped host, hidden tray window, no tray, cancellation, failed replacement, and every documented reopen/recovery path. Compare private configuration bytes without printing them.
- Installer/signature/provenance tests cover the exact final distributed bytes after signing. The final signature cannot be invalidated by later modification.
- Firmware fixtures reject mismatched board/port/layout; physical P4 tests confirm post-flash version and NVS preservation. Physical S3 validation is separately outstanding. No successful PC update auto-flashes a board.
- Test each supported provider with synthetic records and no model calls. Optional real account checks require the user's own vendor flow. Keep bridge-only and activity-only limitations visible in onboarding and release notes.

Until these gates pass, keep automatic installation as planned work and use the existing reviewed installer plus explicit USB firmware workflow.
