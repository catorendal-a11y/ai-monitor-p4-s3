# Create a downloadable release

The portable Windows archive lets users run the companion and flash the display without installing Python or PlatformIO. Git stores the source; generated firmware and executables are release assets, not committed binaries.

## GitHub

1. Push the reviewed, credential-free repository to your GitHub repository. Do not copy local configurations, logs or unrelated output files.
2. Ensure Actions is enabled. Set `FW_VERSION` to the intended version and pass CI. Commit before tagging.
3. Create and push a tag matching `FW_VERSION`, such as `v1.16.1`. This explicitly starts the Portable Windows release workflow.
4. The workflow builds/tests firmware on Linux, builds/tests the Windows executables, verifies the pinned Inno Setup compiler, and tests clean installation, upgrade and uninstall. It creates a **draft release** containing the Windows installer, portable ZIP and SHA-256 checksums. Drafts are invisible to ordinary downloaders.
5. Download the draft ZIP, extract it on Windows, test the menu, setup and firmware on the target board, and verify no private files are included. Review license notices and the corresponding upstream source.
6. Publish the reviewed draft using GitHub's Releases UI. README's recommended download is available after publication.

The workflow needs `contents: write` only in its draft-release job, uses GitHub's provided token, and contains no project API keys. A normal branch push runs CI but does not create a release. Failed or existing-tag releases must be resolved by the maintainer rather than silently replacing a published asset.

The build jobs have read-only repository permission and do not retain checkout credentials. A separate publisher downloads the same run's package and creates the draft without checking out or executing source or generated programs. Version tags must already exist and are administrator-created. The owner reviews the draft before publishing. Future published releases are immutable: finish all asset uploads in the draft, then publish; subsequent fixes require a new version. See [GitHub security](GITHUB_SECURITY.md).

## Local build on Windows

Use Python 3.12 x64 and a clean checkout. Install host dependencies plus the pinned release tools in an isolated virtual environment:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -BuildTools
.\.venv\Scripts\python.exe -m pip install -r scripts/requirements-release.txt
.\.venv\Scripts\python.exe -m platformio run -e esp32p4-release
.\.venv\Scripts\python.exe -m platformio run -e esp32s3-waveshare-43-release
```

Collect both board-specific matching pairs. Each build creates its own application and factory image:

```powershell
.\.venv\Scripts\python.exe scripts/collect_firmware.py --environment esp32p4-release --output work/prebuilt
.\.venv\Scripts\python.exe scripts/collect_firmware.py --environment esp32s3-waveshare-43-release --output work/prebuilt
```

The package requires both `work/prebuilt/guition-p4/` and `work/prebuilt/waveshare-s3-43/`. Its schema-2 manifest records board, chip, status, image offsets, sizes and hashes. The builder verifies image chip headers, current firmware version and factory/application consistency before archiving. Then:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe scripts/build_windows_release.py --firmware-dir work/prebuilt
```

The script builds a windowed `AI-Monitor.exe` with its replaceable `_internal` Qt runtime, a separate `AI-Monitor-Console.exe` for background/stdin workflows, and upstream `firmware-flasher.exe`, exports tracked source, adds the matching images/manifest, gathers dependency licenses and pinned esptool/Qt/PySide corresponding source, then creates the ZIP and internal file hashes in `work/windows-release`. It rejects an existing package directory so an old configuration cannot be silently mixed into a new release. Python/PlatformIO are needed only by the builder, not by the recipient of the portable ZIP.

The desktop build uses a clean PATH to avoid unrelated ICU DLLs. An unexpected bundled ICU aborts packaging; the exact windowed EXE must pass --gui-check before archiving. The native desktop tests use synthetic settings and never flash or log into a real account.

Tagging/publishing is a maintainer action. Preparing an archive locally does not upload it to GitHub.

Versions are kept on one source: `#define FW_VERSION` in `src/config.h`. All build scripts parse it through `tools/project_version.py` (UTF-8/BOM tolerant, pre-release tolerant), executable version resources are generated from it at build time instead of the removed hand-maintained `scripts/windows_version.txt`, and the host-tool identity `HOST_VERSION` in the same module must match — `tests/test_project_version.py` and the release build itself refuse a mismatch, and the test also verifies that the top heading of `docs/RELEASE_NOTES.md` names the same version. A failed build removes its half-built package directory and publishes the ZIP through a temporary name, so retries are never blocked and no truncated archive is left behind. After building the portable package, create and test the per-user installer:

```powershell
./scripts/install_inno_builder.ps1 -Destination work/inno-builder
.\.venv\Scripts\python.exe scripts/build_windows_installer.py --package work/windows-release/ai-monitor-p4-v1.16.1-windows --compiler work/inno-builder/compiler/ISCC.exe --output work/windows-release
.\.venv\Scripts\python.exe scripts/test_windows_install.py --installer work/windows-release/AI-Monitor-Setup-v1.16.1-windows.exe
```

Run installer smoke tests on a clean Windows user profile; they refuse to overwrite a registered installation. The compiler is hash-pinned and its upstream Authenticode publisher is verified; that does not sign our resulting app. Until a signing identity is available, label the release unsigned and retain [Windows protection](WINDOWS_TRUST.md). The installer excludes private configuration; uninstall never recursively deletes user data.
