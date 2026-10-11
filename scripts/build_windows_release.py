"""Build a portable Windows ZIP from the public source and verified firmware."""
import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from board_profiles import BOARDS
from aim_control import firmware_file
from project_version import HOST_VERSION, fw_version, windows_version_resource
from collect_qt_sources import collect as collect_qt_sources


def run(*arguments):
    subprocess.run([sys.executable, *arguments], cwd=ROOT, check=True)


def build_desktop(*arguments):
    # Qt uses Windows' ICU. Unrelated image/PDF tools on the builder's PATH
    # can make PyInstaller bundle an incompatible ICU with the same DLL name.
    environment = dict(os.environ)
    system = Path(os.environ['SystemRoot'])
    environment['PATH'] = os.pathsep.join([str(Path(sys.executable).parent),
        str(Path(sys.base_prefix)), str(system / 'System32'), str(system)])
    subprocess.run([sys.executable, *arguments], cwd=ROOT, env=environment, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware-dir', type=Path, required=True, help='Directory containing both board-specific firmware folders')
    parser.add_argument('--output', type=Path, default=ROOT / 'work/windows-release')
    parser.add_argument('--executables-dir', type=Path, help='Deprecated: executable reuse is refused without build provenance')
    parser.add_argument('--qt-source-dir', type=Path, help='Reuse hash-verified corresponding-source archives')
    args = parser.parse_args()
    if args.executables_dir:
        parser.error('Executable reuse is disabled. Build all executables from the reviewed source in this run.')
    if sys.platform != 'win32':
        parser.error('Windows executables must be built on Windows.')
    git_root = Path(subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--show-toplevel'], text=True).strip())
    if git_root.resolve() != ROOT.resolve():
        parser.error('Release building requires this project to be its own Git root; parent repositories are refused.')
    version = fw_version(ROOT)
    if HOST_VERSION != version:
        parser.error('tools/project_version.py HOST_VERSION ' + HOST_VERSION +
                     ' does not match FW_VERSION ' + version + '; synchronize them before building.')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    package = output / ('ai-monitor-p4-' + version + '-windows')
    if package.exists() or (output / (package.name + '.zip')).exists():
        parser.error('Package directory or archive already exists; use a new output directory.')
    package.mkdir()
    try:
        build_package(output, package, version, args)
    except BaseException:
        # A half-built package would block every retry with "directory already
        # exists"; remove only the directory this run created.
        if package.resolve().parent != output:
            raise RuntimeError('Refusing package cleanup outside the selected output directory') from None
        shutil.rmtree(package, ignore_errors=True)
        raise
    print('Portable package: ' + str(output / (package.name + '.zip')))


def build_package(output, package, version, args):
    scratch = ROOT / 'work/windows-build'
    scratch.mkdir(parents=True, exist_ok=True)
    version_file = scratch / 'windows_version.txt'
    version_file.write_text(windows_version_resource(version), encoding='utf-8')
    common = ['-m', 'PyInstaller', '--noconfirm', '--clean',
              '--version-file', str(version_file),
              '--distpath', str(package), '--workpath', str(scratch / 'build'), '--specpath', str(scratch)]
    if args.executables_dir:
        raise RuntimeError('Executable reuse is disabled; build from the reviewed source.')
    else:
        gui_dist = scratch / 'desktop-dist'
        build_desktop(*common, '--distpath', str(gui_dist), '--onedir', '--windowed', '--name', 'AI-Monitor',
            '--paths', str(ROOT / 'tools'), '--exclude-module', 'esptool',
            '--icon', str(ROOT / 'assets/desktop/nova.ico'),
            '--add-data', str(ROOT / 'assets/desktop') + os.pathsep + 'assets/desktop',
            str(ROOT / 'tools/aim_desktop.py'))
        shutil.copytree(gui_dist / 'AI-Monitor', package, dirs_exist_ok=True)
        run(*common, '--onefile', '--console', '--name', 'AI-Monitor-Console', '--paths', str(ROOT / 'tools'),
            '--exclude-module', 'esptool', '--exclude-module', 'PySide6',
            str(ROOT / 'tools/aim_control.py'))
        run(*common, '--onefile', '--console', '--name', 'firmware-flasher', '--exclude-module', 'PySide6',
            '--collect-all', 'esptool', '--collect-all', 'esp_pylib',
            str(ROOT / 'scripts/esptool_entry.py'))
    if (package / '_internal/icuuc.dll').exists():
        raise RuntimeError('Unexpected bundled ICU: use a clean builder PATH; Qt requires the Windows system ICU')
    files = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files'], text=True).splitlines()
    # Export reviewed source; never recursively copy runtime/private directories.
    for name in files:
        relative = Path(name)
        if any(part in {'.git', '.pio', '.venv', '.codex', '.zcode', 'node_modules', 'work', '__pycache__', 'outputs'} for part in relative.parts):
            raise RuntimeError('Private/generated path in tracked release source')
        if relative.parts[:2] == ('tools', 'activity'):
            raise RuntimeError('Runtime activity records must not be exported')
        if relative.name.startswith('aim_host.invalid-') or relative.name in {'aim_host.json', 'aim_host.status.json', 'auth.json', 'credentials.json', 'secrets.json', '.env'} or \
                (relative.name.startswith('.env.') and relative.name != '.env.example') or \
                relative.suffix in {'.log', '.db', '.sqlite', '.sqlite3', '.jsonl', '.lock', '.bin', '.exe', '.lnk', '.pem', '.key'}:
            raise RuntimeError('Private/generated file in tracked release source')
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    firmware = package / 'firmware'
    firmware.mkdir()
    manifest = {'schema': 2, 'version': version, 'boards': {}}
    for board in BOARDS.values():
        folder = firmware / board.id
        folder.mkdir()
        record = {'board':board.name, 'chip':board.chip, 'experimental':board.experimental, 'files':{}}
        for name, offset in [('application.bin', 0x10000), ('factory.bin', 0)]:
            image = args.firmware_dir / board.id / name
            if not image.is_file(): raise RuntimeError('Required board-specific firmware is missing')
            data = image.read_bytes()
            if name == 'application.bin' and version.encode() not in data:
                raise RuntimeError('Firmware version does not match source')
            shutil.copy2(image, folder / name)
            record['files'][name] = {'sha256':hashlib.sha256(data).hexdigest(), 'bytes':len(data), 'offset':offset}
        manifest['boards'][board.id] = record
    (firmware / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    for board in BOARDS.values():
        firmware_file('install', package, board.id)
        firmware_file('update', package, board.id)
    # Test the exact app only after source, both images and their manifest are
    # present: its diagnostics also launch the actual packaged flasher child.
    subprocess.run([str(package / 'AI-Monitor.exe'), '--gui-check'], cwd=package, check=True, timeout=30)
    licenses = package / 'licenses'
    licenses.mkdir()
    for distribution in metadata.distributions():
        name = distribution.metadata['Name']
        directory = licenses / name
        directory.mkdir(exist_ok=True)
        copied = False
        for item in distribution.files or []:
            if item.name.lower().startswith(('license', 'copying', 'notice')):
                path = distribution.locate_file(item)
                if path.is_file():
                    target = directory / (str(item).replace('/', '_').replace('\\', '_'))
                    shutil.copy2(path, target)
                    copied = True
        info = {'name': name, 'version': distribution.version,
                'license': distribution.metadata.get('License-Expression') or distribution.metadata.get('License'),
                'source': distribution.metadata.get_all('Project-URL') or [distribution.metadata.get('Home-page')],
                'license_files_copied': copied}
        (directory / 'metadata.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    # Preserve the interpreter license shipped with the build environment.
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.exists():
        raise RuntimeError('Python runtime license missing from the build environment')
    shutil.copy2(python_license, licenses / 'Python-LICENSE.txt')
    sources = package / 'third-party-source'
    sources.mkdir()
    run('-m', 'pip', 'download', '--no-deps', '--no-binary=:all:', '--dest', str(sources), 'esptool==5.4.0')
    collect_qt_sources(sources, args.qt_source_dir)
    hashes = []
    for path in sorted(package.rglob('*')):
        if path.is_file():
            hashes.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.relative_to(package).as_posix())
    (package / 'SHA256SUMS.txt').write_text('\n'.join(hashes) + '\n', encoding='utf-8')
    archive = output / (package.name + '.zip')
    archive_package(package, archive)


def archive_package(package, archive):
    partial = archive.with_name(archive.name + '.partial')
    # Write beside the destination, then publish atomically: an interrupted run
    # must not leave a truncated archive that still looks like a deliverable.
    try:
        with zipfile.ZipFile(partial, 'w', zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(package.rglob('*')):
                if path.is_file():
                    bundle.write(path, package.name + '/' + path.relative_to(package).as_posix())
        os.replace(partial, archive)
    finally:
        partial.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
