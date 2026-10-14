"""Create a per-user installer from an already tested, checksum-verified package."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from project_version import fw_version, numeric_version, version_tuple
from aim_control import firmware_file, SetupError
from board_profiles import BOARDS
from host_security import read_local_json


def verify_package(package: Path) -> str:
    package = package.resolve()
    source_version = fw_version(package)
    version = numeric_version(source_version)
    expected = set()
    for line in (package/'SHA256SUMS.txt').read_text().splitlines():
        digest, relative = line.split('  ', 1)
        file = (package/relative).resolve()
        if not file.is_relative_to(package) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('Invalid package checksum path')
        if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            raise ValueError('Package checksum mismatch')
        expected.add(file)
    actual = {file.resolve() for file in package.rglob('*') if file.is_file() and file != package/'SHA256SUMS.txt'}
    if actual != expected:
        raise ValueError('Unreviewed files in package')
    for file in actual:
        if file.name.startswith('aim_host.invalid-') or file.name in {'aim_host.json', 'aim_host.status.json', 'aim_host.log', 'auth.json', 'credentials.json'} or file.suffix in {'.db', '.sqlite', '.jsonl', '.lnk'}:
            raise ValueError('Private runtime file in package')
    for name in ('AI-Monitor.exe', 'AI-Monitor-Console.exe', 'AI-Monitor-Events.exe',
                 'AI-Monitor-Permission.exe', 'permission-runtime/base_library.zip',
                 'event-runtime/base_library.zip', '_internal/base_library.zip',
                 'firmware-flasher.exe', '_internal/PySide6/Qt6Core.dll'):
        if not (package/name).is_file():
            raise ValueError('Incomplete application runtime')
    manifest = read_local_json(package/'firmware/manifest.json')
    if (not isinstance(manifest, dict) or type(manifest.get('schema')) is not int or
            manifest['schema'] != 2 or manifest.get('version') != source_version):
        raise ValueError('Firmware manifest does not match the package version')
    for board in BOARDS.values():
        try:
            application = firmware_file('update', package, board.id)
            firmware_file('install', package, board.id)
        except SetupError as error:
            raise ValueError('Invalid packaged firmware for ' + board.id) from error
        if source_version.encode() not in application.read_bytes():
            raise ValueError('Firmware image does not match the package version')
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    version = verify_package(args.package)
    args.output.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(args.compiler.resolve()), '/Qp', f'/DPackageDir={args.package.resolve()}',
                    f'/DAppVersion={version}', f'/DAppNumericVersion={".".join(map(str, version_tuple("v"+version)))}',
                    f'/DOutputDir={args.output.resolve()}',
                    str(ROOT/'scripts/windows_installer.iss')], check=True)
    print('Verified per-user installer built; no administrator access or provider credentials required.')


if __name__ == '__main__': main()
