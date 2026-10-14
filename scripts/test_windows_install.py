"""Prove clean installation, upgrade, GUI startup and settings-preserving uninstall."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile
import winreg

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installer', type=Path, required=True)
    args = parser.parse_args()
    key = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{873FC919-66BF-49AE-8265-F25894DBE139}_is1'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
            raise RuntimeError('Run installer smoke tests on a clean user profile; an installed AI Monitor already exists.')
    except FileNotFoundError:
        pass
    scratch = ROOT/'work'; scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='installer-test-', dir=scratch) as directory:
        target = Path(directory)/'AI Monitor'
        arguments = [str(args.installer.resolve()), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOICONS', f'/DIR={target}']
        installed = False
        try:
            subprocess.run(arguments, check=True, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
            installed = True
            assert not (target/'tools/aim_host.json').exists(), 'Fresh install exported configuration'
            for arguments_check in ([str(target/'AI-Monitor.exe'), '--gui-check'],
                                    [str(target/'firmware-flasher.exe'), '--help']):
                subprocess.run(arguments_check, check=True, timeout=40, stdout=subprocess.DEVNULL,
                               stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            config = target/'tools/aim_host.json'
            config.write_text('{"providers":["copilot"],"board":"guition-p4","port":"COM9999","zai_key":"fixture-private-key"}')
            before = hashlib.sha256(config.read_bytes()).digest()
            subprocess.run(arguments, check=True, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
            assert hashlib.sha256(config.read_bytes()).digest() == before, 'Upgrade modified local settings'
        finally:
            if installed:
                subprocess.run([str(target/'unins000.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
                               check=True, timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
        assert config.is_file() and hashlib.sha256(config.read_bytes()).digest() == before
        assert not (target/'AI-Monitor.exe').exists(), 'Uninstaller left application files'
    print('PASS: clean per-user installation, exact EXE/Qt startup, CLI flasher, upgrade and private-settings-preserving uninstall.')


if __name__ == '__main__': main()
