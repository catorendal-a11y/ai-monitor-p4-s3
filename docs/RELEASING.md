# Release the NOVA terminal

The distributed product is Python source plus verified board firmware. No application EXE,
Qt runtime, PyInstaller or Inno installer is built or uploaded. Python dependencies are installed
from the pinned tools/requirements.txt by setup.ps1 / Install-Nova.ps1.

Synchronize src/config.h, tools/project_version.py and the top RELEASE_NOTES.md heading.
Build both boards sequentially locally and collect matching images (see DEVELOPMENT.md), then:

```powershell
.\.venv\Scripts\python.exe scripts/build_terminal_release.py --firmware-dir work/prebuilt
```

Use a fresh output directory for each attempt. The builder exports only tracked reviewed source,
rejects private/generated files and linked paths, verifies both application/factory pairs, keeps
source/license notices and produces nova-vVERSION-terminal.zip with internal file hashes.

A v* tag starts the GitHub release workflow: both firmware targets, native UI tests, Windows
regressions, source ZIP and clean terminal installation without Qt/packaged EXEs. The isolated
publisher verifies archive checksums, attests the archive/checksums and creates a draft without
executing source. Review the downloaded draft and publish it explicitly. Maintainers must not
replace immutable published assets. Retirement of old EXE releases is a separate explicit owner
action; retain source tags/history and local verification evidence.

On a disposable Windows directory, test the exact extracted package with:

```powershell
.\.venv\Scripts\python.exe scripts/test_terminal_package.py --package PATH_TO_CLEAN_PACKAGE
```

This installs an isolated environment, tests bare nova under normal PowerShell policy from
another folder, verifies no Qt/freezer runtime, and tests idempotent registration/unregistration.
It does not read credentials, link provider hooks or flash hardware. The resulting test directory
contains dependencies; do not republish it. Publish the original clean ZIP only.
