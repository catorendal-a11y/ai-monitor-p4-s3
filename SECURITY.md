# Security

Firmware needs no provider credentials. The Python companion reads local credentials at runtime and sends quota/activity over USB. Token activity uses read-only queries of numeric counters and identifiers.

Do not commit `tools/aim_host.json`, environment files, CLI auth, keys, databases or logs. The example key stays empty. `.env.example` is documentation only; the companion does not automatically load it. Keep logs private even when error messages are sanitized.

Tests must use synthetic credentials/responses. Do not mix debug serial logging with a production companion on the same port. Provider responses and USB messages are untrusted; retain size limits, type validation and bounded buffers.

## Host protections in v1.12.1

- The companion has no listening network service. It uses outbound HTTPS and a local USB serial device. The optional official CLI runs through local standard input/output.
- Direct quota requests use two fixed HTTPS endpoints, verified certificates and a 20-second timeout. All HTTP redirects are rejected so authentication headers cannot follow a redirect to another origin or HTTP.
- Codex discovery ignores relative PATH entries, the current directory and the monitor project tree. Windows PowerShell uses its absolute system path. Installation and sign-in still require explicit user choices and trust the official client and installer.
- USB ports are restricted to COM or /dev/ serial device paths, with traversal and network URLs rejected. Untrusted panel errors are generic; terminal control characters and oversized log entries are removed. Local configuration reads are limited to 64 KiB.
- GitHub Actions use pinned commit identities and read-only permissions for CI. Dependency vulnerability auditing runs in CI, and Dependabot proposes updates for review. Source setup upgrades pip inside this project's virtual environment before installing dependencies.

These protections do not protect against malware already running as your Windows user, a modified local executable, or a compromised provider account. The optional Z.AI key is stored in local configuration as plaintext: keep it in a private user folder, never upload it, and use a separate provider key that can be revoked. A checksum detects corruption; it does not authenticate a package when both the ZIP and checksum come from an untrusted source. Download from this repository's Releases. Windows executables are currently unsigned.

[Review evidence and limits](docs/SECURITY_REVIEW.md)

[GitHub permissions, external contributions and release safeguards](docs/GITHUB_SECURITY.md)

## Reporting

If the published GitHub repository enables private reporting, use **Security → Report a vulnerability**. Otherwise contact the repository owner privately through a channel listed on their GitHub profile. Do not post exploit details, credentials or account data in public issues. This source package contains no maintainer email or promised response deadline.

Include version, impact and a minimal synthetic reproduction. Revoke exposed keys through their provider before sharing a report. Deleting a file does not remove it from Git history.

Fixes target the current release; older forks may need backports.
