# Windows installation and terminal trust

Download `nova-v1.19.1-rc18-windows-x64-terminal.zip` and `SHA256SUMS.txt` from this repository's Releases. Compare the ZIP's SHA-256, extract the complete archive into a permanent writable folder and double-click **Install-Nova.cmd**. It verifies the bundled runtime before registering `nova` for the current user. Open a new terminal and type `nova`.

The release includes NOVA Python source, the official CPython 3.13.16 embeddable runtime, hash-locked dependency wheels and both boards' firmware. It contains the upstream `python.exe` and `pythonw.exe` interpreters under `runtime/`, but no compiled NOVA application EXE, Qt frontend, PyInstaller package or Inno installer. Keep the complete extracted folder; the registered command points to it. No separate Python, pip, Node.js, PlatformIO or administrator access is required. Installing from the extracted ZIP works offline; provider requests and optional AI-client installation/sign-in still need internet.

## SmartScreen

**The command scripts and bundled upstream interpreter are not Authenticode-signed by this project's publisher. Windows or an organization policy can still warn or block them.** A checksum, version metadata or GitHub provenance does not establish a trusted Windows publisher. The project does not disable SmartScreen, Defender, Smart App Control or execution protections, and does not automatically unblock downloads.

Download only from the linked repository, compare SHA-256 with the release checksum, and retain Windows protection. Checksums detect corruption but do not independently authenticate a compromised release. If you do not trust the download or your organization blocks it, cancel and ask your administrator; do not weaken system policy.

For future distribution, a verified publisher could timestamp-sign eligible Windows artifacts or submit an MSIX package through the Microsoft Store. Signing outside the Store can still require reputation to build; it cannot guarantee that every new release is warning-free. Microsoft's current guidance: [SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation) and [code-signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options).

Microsoft Security Intelligence can review a specific submitted file for incorrect detections. A submission is not a publisher certificate, Store certification, or a guarantee that SmartScreen reputation warnings disappear. Record the exact file SHA-256 and the final Microsoft determination; do not label a pending submission as approved.

## What is tested

Release checks build both firmware targets and the exact Windows x64 terminal ZIP. They verify the pinned CPython archive and runtime wheel hashes, runtime manifest, retained licenses, absence of a NOVA EXE/Qt runtime, clean extraction, the real CMD installer and bare `nova` with external Python and package downloads unavailable. Native and Python tests use synthetic settings and do not flash hardware or sign into provider accounts. The isolated publisher only verifies and attests the completed ZIP/checksum before creating a draft; it does not execute repository code.

Real P4 flashing is checked separately when the board is connected. The original S3 remains experimental until tested on physical S3 hardware. Physical approvals, unplug/suspend behavior and long-duration stability remain separate validation gates.

These checks cannot guarantee every PC, USB cable, board variant, security policy or external provider version. Unsupported integrations stay visibly unavailable rather than report fabricated quotas.

Run `powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Nova.ps1 -Uninstall` from the extracted folder to remove only that installation's owned `nova` command and PATH entry. It retains the extracted application files, private `tools/aim_host.json`, logs and activity records. Stop the host and unlink this installation's observational integrations before deleting its folder. Remove private data yourself if you want to erase it; never upload it to GitHub.
