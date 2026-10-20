# Release the LimitBuddy terminal

The distributed product is Python source plus verified board firmware. No NOVA application EXE, Qt runtime, PyInstaller or Inno installer is built.
Windows releases include the official hash-verified Python embeddable runtime and hash-locked
Python dependency wheels, with retained original license files, under runtime/. The consumer
installs offline by double-clicking Install-LimitBuddy.cmd; source-only setup still uses pip.

Synchronize src/config.h, tools/project_version.py and the top RELEASE_NOTES.md heading.
Build both boards sequentially locally and collect matching images (see DEVELOPMENT.md), then:

```powershell
.\.venv\Scripts\python.exe scripts/build_terminal_release.py --firmware-dir work/prebuilt --windows-runtime
```

Use a fresh output directory for each attempt. The builder exports only tracked reviewed source,
rejects private/generated files and linked paths, verifies both application/factory pairs, keeps
source/license notices and produces `nova-vVERSION-windows-x64-terminal.zip` with internal file hashes.

A v* tag starts the GitHub release workflow: both firmware targets, native UI tests, Windows
regressions, the Windows x64 terminal ZIP and a clean installation without a NOVA EXE or Qt. The isolated
publisher verifies archive checksums, attests the archive/checksums and creates a draft without
executing source. Review the downloaded draft and publish it explicitly. Maintainers must not
replace immutable published assets. Retirement of old EXE releases is a separate explicit owner
action; retain source tags/history and local verification evidence.

On a disposable Windows directory, test the exact extracted package with:

```powershell
.\.venv\Scripts\python.exe scripts/test_terminal_package.py --package PATH_TO_CLEAN_PACKAGE
```

This tests the real CMD installer without external Python or package downloads, then bare limitbuddy and nova from
another folder, verifies no Qt/freezer runtime, and tests idempotent registration/unregistration.
It does not read credentials, link provider hooks or flash hardware. The resulting test directory
contains generated private setup data; do not republish it. Publish the original clean ZIP only.
