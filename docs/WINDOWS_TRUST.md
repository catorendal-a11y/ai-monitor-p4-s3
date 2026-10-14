# Windows installation and app trust

Download **AI-Monitor-Setup-v1.17.0-windows.exe** from this repository's Releases. It installs the complete Windows x64 app, runtime, flasher, firmware, notices and corresponding third-party source into your own user profile. Python, PlatformIO and administrator rights are unnecessary. It opens the graphical setup after installation; choose your board/providers and follow their instructions. Firmware writing still requires reviewing the target and typing FLASH.

The portable ZIP remains available. Keep the complete folder together, including `_internal`. `firmware-flasher.exe` is a command-line helper; double-clicking it explains how to open the graphical Firmware tab. Normal installation shows progress and errors in the app instead of disappearing.

## SmartScreen

**This release is unsigned. Windows can show "Windows protected your PC" or "Unknown publisher".** The maintainer does not currently have a trusted code-signing identity. A checksum, application icon, version metadata or an ordinary installer does not establish a trusted publisher. The project does not disable SmartScreen, Defender, Smart App Control or execution protections, and does not automatically unblock downloads.

Download only from the linked repository, compare SHA-256 with the release checksum, and retain Windows protection. Checksums detect corruption but do not independently authenticate a compromised release. If you do not trust the download or your organization blocks it, cancel and ask your administrator; do not weaken system policy.

For future distribution, use a verified publisher with timestamped Authenticode signing, or submit an MSIX package through the Microsoft Store. Signing outside the Store can still require reputation to build; it cannot guarantee that every new binary is warning-free. Microsoft's current guidance: [SmartScreen reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation) and [code-signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options).

Microsoft Security Intelligence can review a specific submitted file for incorrect detections. A submission is not a publisher certificate, Store certification, or a guarantee that SmartScreen reputation warnings disappear. Record the exact file SHA-256 and the final Microsoft determination; do not label a pending submission as approved.

## What is tested

Release checks build the exact GUI and CLI helpers, open an offscreen native window with synthetic settings, validate both firmware images, and invoke the flasher from the packaged Qt process without USB writes. Installer smoke tests cover clean per-user installation, runtime startup, settings-preserving upgrade and uninstall. Local numeric-bridge fixtures verify the independent host survives its menu closing and can be stopped only within its own folder. Real P4 flashing is checked separately when the board is connected. The original S3 remains experimental until tested on physical S3 hardware.

These checks cannot guarantee every PC, USB cable, board variant, security policy or external provider version. Unsupported integrations stay visibly unavailable rather than report fabricated quotas.

Uninstall removes installed application files but leaves your private `tools/aim_host.json`, logs and activity records. Remove these yourself if you want to erase local settings; never upload them to GitHub. Stop a portable host from its original folder before switching to the installer version.
