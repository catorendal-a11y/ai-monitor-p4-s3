# Automatic Codex setup for new users

You do not need Codex CLI installed in advance. Choose **Codex**, save settings and click **AI setup > Install / sign in Codex**. The app offers the official standalone client installer when missing, reuses an existing client and offers official browser sign-in when needed. No provider is preselected.

## What the PC needs

| Item | Ready-to-run Windows release |
| --- | --- |
| Windows | Windows x64. Windows 11 is recommended for Codex; OpenAI documents updated Windows 10 as best effort, with version 1809 or later needed for modern console support. |
| Monitor runtime | Included: Python, PySide6/Qt, serial support, flasher, Visual C++ runtime DLLs and both boards' firmware. No separate Python, Qt, PlatformIO or Arduino IDE installation. |
| Codex CLI | Downloaded separately by the setup action after approval if missing. An existing compatible installation is reused. |
| Node.js / npm / Git | Not needed for the monitor or its standalone Codex installation route. An existing npm-based CLI still uses its own Node installation. |
| PowerShell | The Windows-provided PowerShell runs the official installer. Managed-PC policy can block this; consult the PC administrator if an error reports a restriction. |
| Internet and browser | Needed for the download and your official account sign-in. |
| Account | Your own ChatGPT account with Codex access. No OpenAI API key is pasted into AI Monitor for subscription quota. |
| USB | A data-capable cable and supported display. If no COM port appears, check the cable/connector and the manufacturer's driver. |

The Windows release is installed for your own user without administrator access. **Source ZIPs** need Python 3.10+; source setup installs the Python dependencies into `.venv`. Building firmware needs the [developer tools](DEVELOPMENT.md). Codex's requirements for actually coding/building another project depend on that project; AI Monitor only reads status and does not start coding tasks or provision a command sandbox. See [PC requirements](PC_REQUIREMENTS.md), [official CLI installation](https://learn.chatgpt.com/docs/cli) and [Windows support](https://learn.chatgpt.com/docs/windows/windows-sandbox).

## First installation

1. Run the **AI-Monitor-Setup** EXE, or extract the complete portable ZIP and open **AI-Monitor.exe**.
2. In **Setup**, explicitly select your board and USB port. In **AI setup**, select Codex alone or with other tools. Click **Save settings** and accept the offer to open provider setup, or use **AI setup > Install / sign in Codex** later.
3. A small setup console opens. You answer confirmation prompts; no installation command needs to be typed. If the official CLI is missing, accept **Install the official Codex CLI now?** and follow the vendor installer prompts. Setup then looks for the new executable even if Explorer still has an older PATH. You can decline and finish later; existing clients are reused.
4. Setup checks sign-in quietly. If needed, it offers **official Codex sign-in**. Accept and finish the vendor's browser/terminal flow with your own ChatGPT account. The monitor never asks for or copies your OpenAI password/access token.
5. Once the console finishes, click **Start host**. Read **Host settings > Live provider health** for received, pending or unavailable quota. A found CLI or started process alone does not prove quota is available. Your choices remain selected if installation or login was skipped or failed. Retry through the same setup button. AI-Monitor-Console.exe retains the numbered menu for advanced use.

The installer and first sign-in need internet access. Windows uses OpenAI's standalone PowerShell installer; Linux/macOS source installations use its documented shell installer. No personal OpenAI key, GitHub key or credentials are shipped with the release.

## Existing accounts and storage

The CLI keeps control of its existing credential store, including supported file/keyring modes. Setup does not rewrite global Codex configuration or silently switch storage to a plaintext file. `CODEX_HOME` and `CODEX_INSTALL_DIR` are respected for compatible custom installations. Login status output is not copied into monitor logs.

Plan quota is read through the official CLI app-server `account/rateLimits/read` method after initialization. No model turn, code-generation request, credit-reset redemption or notification email is started by the monitor. Local token activity still uses the numeric SQLite counter under `CODEX_HOME`. If the CLI is absent, an already-existing file-login quota adapter remains as a legacy fallback; setup never copies that file into project configuration.

Quota requires a ChatGPT-backed account. API-key-only mode does not become a subscription quota, and ephemeral credentials are not guaranteed to work across independent processes. Missing/unsupported account data is shown as unavailable rather than invented. Use the official CLI to change account/storage deliberately when needed.

## If setup is incomplete

| State | Action |
| --- | --- |
| CLI missing | Click **AI setup > Install / sign in Codex** and accept installation. Console users can use menu **7, Provider integration help**. |
| CLI not found after installation | Restart the app so updated paths are available, then retry. |
| Sign-in skipped/cancelled | Click **Install / sign in Codex** again and complete the official browser login. |
| Quota unavailable | Verify ChatGPT sign-in and update the official CLI if its account interface is unsupported. |
| Tokens unavailable | Use Codex sessions that update the supported local numeric database; token registration may lag requests. |
| Another provider selected | Codex setup is not run; use that provider's guide. |

Your display's USB settings, selected providers, Z.AI key, and robot/theme preferences remain independent of Codex login. No extra AI is enabled when a step fails.

## Installation verification

Synthetic tests cover missing-client installation/sign-in prompts, declined setup, existing-login reuse, discovery and read-only account requests. `scripts/test_codex_windows_install.py --disposable-ci` additionally installs the official client for real on a disposable GitHub Windows runner with isolated Codex state and no Node/Python commands on PATH. It checks native executable discovery and login status, then declines personal sign-in. Do not run this test on a personal PC: the vendor installer can update the user PATH. A CI installation test does not prove successful login for every account; each user completes their own browser authentication.

Official references: [CLI installation](https://learn.chatgpt.com/docs/cli), [authentication/storage](https://learn.chatgpt.com/docs/auth), [account rate-limit interface](https://learn.chatgpt.com/docs/app-server), [CODEX_HOME and installation directories](https://learn.chatgpt.com/docs/config-file/environment-variables).
