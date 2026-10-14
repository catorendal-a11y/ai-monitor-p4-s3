# Security review — 2026-10-09

Scope: the PC companion, official-client setup, USB input, local configuration, provider HTTP requests, build dependencies and GitHub workflows. This is a source and dependency review with synthetic regression tests, not a full penetration test of the owner's PC or a guarantee against compromise.

| Finding | Impact and resolution |
| --- | --- |
| Provider requests followed default HTTP redirects | A redirect from the authenticated endpoint could forward Authorization. All redirects are now rejected, including HTTPS-to-HTTP and same-origin redirects. Only the two fixed quota URLs can be opened. Tests exercise the real opener using a synthetic HTTPS handler and verify that no second request occurs. |
| Implicit current-directory executable discovery | A planted Codex executable could be selected from a working/project folder. Discovery now scans only absolute PATH directories, rejects the current directory and the monitor tree, and uses an absolute system PowerShell path. The official CLI remains a trusted local dependency. |
| Serial paths and terminal text were insufficiently constrained | Serial settings now reject network URLs and /dev/ traversal. Panel rejection details are not copied into host exceptions. Displayed log lines remove terminal controls and have a length bound. Configuration reads are limited to 64 KiB. |
| Mutable workflow references and old package installer | Actions are pinned to verified upstream commits, dependency audit is added to CI and Dependabot proposes reviewed updates. The isolated build environment and source setup use pip 26.2.1; the older builder pip had known advisories. |

101 synthetic Python tests passed locally after these fixes. Resolved runtime/release requirements and the actual isolated Windows build environment were checked with pip-audit. No known dependency advisories remained after updating pip. Static analysis warnings about subprocess use were reviewed: provider replies and telemetry are not executed, subprocess arguments are structured, and the optional installer runs only after user selection. No remote command execution path was found in the reviewed monitor code.

On the owner's machine, Defender real-time, behavior and downloaded-file protection were enabled; all three firewall profiles were enabled. The two running monitor processes had zero listening network sockets. These are point-in-time observations, not a scan of every other installed application. Provider login and cloud API requests were not exercised with real credentials in the security tests. Hardware USB attacks and exploitation of dependencies or the official CLI are outside the verified test scope.

The optional Z.AI key remains plaintext in local configuration. A process with the same Windows account can read it; the monitor cannot isolate credentials from already installed malware. The public Git history and release archive exclude local keys, authentication files, databases and logs. The portable program is unsigned. See [Security](../SECURITY.md) for the remaining trust assumptions and private reporting procedure.

Implementation references: [Python HTTP redirect handling](https://docs.python.org/3/library/urllib.request.html#urllib.request.HTTPRedirectHandler), [Python executable search behavior](https://docs.python.org/3/library/shutil.html#shutil.which).
