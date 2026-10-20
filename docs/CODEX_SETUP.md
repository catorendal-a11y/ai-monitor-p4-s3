# Automatic Codex setup for new users

You do not need Codex CLI installed in advance. In NOVA, choose **Settings > Edit settings**, select Codex and save, then open **Agents > Codex sign-in**. NOVA offers the official standalone client installer when missing, reuses an existing client and offers official browser sign-in when needed. No provider is preselected.

## What the PC needs

| Item | Ready-to-run Windows release |
| --- | --- |
| Windows | Windows x64. Windows 11 is recommended for Codex; OpenAI documents updated Windows 10 as best effort, with version 1809 or later needed for modern console support. |
| Monitor runtime | Included: verified Python runtime, pinned terminal/serial/flasher libraries and both boards' firmware. No separate Python, Qt, PlatformIO or Arduino IDE installation. |
| Codex CLI | Downloaded separately by the setup action after approval if missing. An existing compatible installation is reused. |
| Node.js / npm / Git | Not needed for the monitor or its standalone Codex installation route. An existing npm-based CLI still uses its own Node installation. |
| PowerShell | The Windows-provided PowerShell runs the official installer. Managed-PC policy can block this; consult the PC administrator if an error reports a restriction. |
| Internet and browser | Needed for the download and your official account sign-in. |
| Account | Your own ChatGPT account with Codex access. No OpenAI API key is pasted into LimitBuddy for subscription quota. |
| USB | A data-capable cable and supported display. If no COM port appears, check the cable/connector and the manufacturer's driver. |

The Windows x64 release is installed for your own user without administrator access. GitHub's automatic source archives need Python 3.10+; source setup installs dependencies into `.venv`. Building firmware needs the [developer tools](DEVELOPMENT.md). Codex's requirements for actually coding/building another project depend on that project; LimitBuddy only reads status and does not start coding tasks or provision a command sandbox. See [PC requirements](PC_REQUIREMENTS.md), [official CLI installation](https://learn.chatgpt.com/docs/cli) and [Windows support](https://learn.chatgpt.com/docs/windows/windows-sandbox).

## First installation

1. Extract the complete Windows x64 terminal ZIP and double-click **Install-Nova.cmd**. Open a new terminal and type `nova`.
2. In **Settings > Edit settings**, explicitly select your board, USB port and Codex, then save.
3. Open **Agents**, select the Codex setup action and review the prompts. If the official CLI is missing, accept **Install the official Codex CLI now?** and follow the vendor installer prompts. You can decline and finish later; existing clients are reused.
4. Setup checks sign-in quietly. If needed, it offers **official Codex sign-in**. Accept and finish the vendor's browser/terminal flow with your own ChatGPT account. The monitor never asks for or copies your OpenAI password/access token.
5. Return to **Settings** and start the host. Use **Overview** for quota status and **Agents** for observational links. A found CLI or started process alone does not prove quota is available. Your selection remains saved if installation or login was skipped or failed; retry through the same Agents action.

Installing NOVA from the extracted release works offline. Downloading or installing Codex and completing its first sign-in need internet access. Windows uses OpenAI's standalone PowerShell installer; Linux/macOS source installations use its documented shell installer. No personal OpenAI key, GitHub key or credentials are shipped with the release.

## Existing accounts and storage

The CLI keeps control of its existing credential store, including supported file/keyring modes. Setup does not rewrite global Codex configuration or silently switch storage to a plaintext file. `CODEX_HOME` and `CODEX_INSTALL_DIR` are respected for compatible custom installations. Login status output is not copied into monitor logs.

Plan quota is read through the official CLI app-server `account/rateLimits/read` method after initialization. No model turn, code-generation request, credit-reset redemption or notification email is started by the monitor. Local token activity still uses the numeric SQLite counter under `CODEX_HOME`. If the CLI is absent, an already-existing file-login quota adapter remains as a legacy fallback; setup never copies that file into project configuration.

Quota requires a ChatGPT-backed account. API-key-only mode does not become a subscription quota, and ephemeral credentials are not guaranteed to work across independent processes. Missing/unsupported account data is shown as unavailable rather than invented. Use the official CLI to change account/storage deliberately when needed.

## If setup is incomplete

| State | Action |
| --- | --- |
| CLI missing | Open **Agents**, use the Codex setup action and accept installation. |
| CLI not found after installation | Restart the app so updated paths are available, then retry. |
| Sign-in skipped/cancelled | Run the Codex setup action again from **Agents** and complete the official browser login. |
| Quota unavailable | Verify ChatGPT sign-in and update the official CLI if its account interface is unsupported. |
| Tokens unavailable | Use Codex sessions that update the supported local numeric database; token registration may lag requests. |
| Another provider selected | Codex setup is not run; use that provider's guide. |

Your display's USB settings, selected providers, Z.AI key, and robot/theme preferences remain independent of Codex login. No extra AI is enabled when a step fails.

## Installation verification

Optional v2 lifecycle metadata: open **Agents > Provider events**, choose Codex, leave Remove off
and type `LINK`. Review/trust the exact hooks using Codex's `/hooks` browser and restart the session.
Running the same action with Remove enabled preserves other
hooks. This does not change authentication or start a model turn. Hook support is client-version
dependent; a saved configuration is not proof that events are delivered. Use the Agents page and
Device status to distinguish observed client events from confirmed USB delivery. See
[event semantics and validation limits](LIVE_PROVIDER_EVENTS.md).

Synthetic tests cover missing-client installation/sign-in prompts, declined setup, existing-login reuse, discovery and read-only account requests. `scripts/test_codex_windows_install.py --disposable-ci` installs the official client for real on a disposable GitHub Windows runner with isolated Codex state and no Node/Python commands on PATH. It checks native executable discovery and login status, then declines personal sign-in. Do not run this test on a personal PC: the vendor installer can update the user PATH. A CI installation test does not prove successful login for every account; each user completes their own browser authentication.

Official references: [CLI installation](https://learn.chatgpt.com/docs/cli), [authentication/storage](https://learn.chatgpt.com/docs/auth), [account rate-limit interface](https://learn.chatgpt.com/docs/app-server), [CODEX_HOME and installation directories](https://learn.chatgpt.com/docs/config-file/environment-variables).
