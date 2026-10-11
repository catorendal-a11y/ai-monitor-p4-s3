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


def verify_package(package: Path) -> str:
    package = package.resolve()
    version = numeric_version(fw_version(package))
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
    for name in ('AI-Monitor.exe', 'AI-Monitor-Console.exe', 'firmware-flasher.exe', '_internal/PySide6/Qt6Core.dll'):
        if not (package/name).is_file():
            raise ValueError('Incomplete application runtime')
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
