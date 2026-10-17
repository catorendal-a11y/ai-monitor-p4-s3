"""Prove clean installation, upgrade, GUI startup and settings-preserving uninstall."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile
import os
import sys
import time
from unittest.mock import patch
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
    # This exercises real installed hooks only inside a disposable profile.
    sys.path.insert(0,str(ROOT/'tools'))
    from claude_paths import config_root
    from codex_support import codex_home
    from private_files import write_json
    import provider_setup as providers
    from claude_permission_setup import update as permission_update
    profile_files=[config_root()/'settings.json',codex_home()/'hooks.json',Path.home()/'.zcode/cli/config.json']
    if any(path.exists() for path in profile_files):
        raise RuntimeError('Use a disposable Windows profile without existing provider settings.')
    scratch = ROOT/'work'; scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='installer-test-', dir=scratch) as directory:
        target = Path(directory)/'AI Monitor'
        arguments = [str(args.installer.resolve()), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOICONS', f'/DIR={target}']
        installed = False
        fixture_host = None
        before = None
        try:
            subprocess.run(arguments, check=True, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
            installed = True
            assert not (target/'tools/aim_host.json').exists(), 'Fresh install exported configuration'
            terminal_bin = str(target/'terminal-bin')
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as environment:
                user_path = winreg.QueryValueEx(environment, 'Path')[0]
            assert user_path.split(';').count(terminal_bin) == 1, 'nova command PATH missing or duplicated'
            assert (target/'terminal-bin/nova.cmd').is_file(), 'nova command missing'
            for arguments_check in ([str(target/'AI-Monitor.exe'), '--gui-check'],
                                    [str(target/'firmware-flasher.exe'), '--help']):
                subprocess.run(arguments_check, check=True, timeout=40, stdout=subprocess.DEVNULL,
                               stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            config = target/'tools/aim_host.json'
            write_json(config,dict(providers=['claude'],board='guition-p4',port='COM9999',
                                   zai_key='fixture-private-key',usage_history=False))
            terminal_env=dict(os.environ,AI_MONITOR_PYTHON=sys.executable)
            subprocess.run([os.environ['COMSPEC'],'/c',str(target/'terminal-bin/nova.cmd'),'--check'],
                           check=True,timeout=30,env=terminal_env,stdout=subprocess.DEVNULL,
                           stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            # Exact installed command generation, with custom settings/hooks alongside it.
            with patch.object(sys,'frozen',True,create=True):
                for link in (providers.codex_session_link,providers.claude_session_link,providers.zcode_session_link): link(target)
                providers.claude_bridge(target)
                permission_update(target,opted_in=True)
            import json
            claude_settings=profile_files[0]
            document=json.loads(claude_settings.read_text())
            custom={'type':'command','command':'echo fixture-custom-observer'}
            document['env']={'AI_MONITOR_SMOKE_FIXTURE':'preserve'}
            document['hooks']['Stop'][0]['hooks'].append(custom)
            write_json(claude_settings,document)
            fixture_host=subprocess.Popen([str(target/'AI-Monitor-Console.exe'),'--host'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(3)
            assert fixture_host.poll() is None, 'Fixture host did not remain running'

            before = hashlib.sha256(config.read_bytes()).digest()
            subprocess.run(arguments, check=True, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
            assert hashlib.sha256(config.read_bytes()).digest() == before, 'Upgrade modified local settings'
            fixture_host.wait(timeout=15)
            fixture_host=subprocess.Popen([str(target/'AI-Monitor-Console.exe'),'--host'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(3)
            assert fixture_host.poll() is None, 'Uninstall fixture host did not remain running'
        finally:
            if installed:
                subprocess.run([str(target/'unins000.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
                               check=True, timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
        if fixture_host is not None: fixture_host.wait(timeout=15)
        assert config.is_file() and before is not None and hashlib.sha256(config.read_bytes()).digest() == before
        document=json.loads(claude_settings.read_text())
        assert document.get('env')=={'AI_MONITOR_SMOKE_FIXTURE':'preserve'}
        assert 'statusLine' not in document
        assert document['hooks']['Stop'][0]['hooks']==[custom], 'Uninstall removed custom hooks'
        assert not document['hooks'].get('PermissionRequest'), 'Permission helper was retained'
        with patch.object(sys,'frozen',True,create=True):
            # State readers require helper files; inspect exact stored collections instead.
            assert not json.loads(profile_files[1].read_text()).get('hooks')
            assert not json.loads(profile_files[2].read_text()).get('hooks',{}).get('events')
        assert not (target/'AI-Monitor.exe').exists(), 'Uninstaller left application files'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as environment:
            assert terminal_bin not in winreg.QueryValueEx(environment,'Path')[0].split(';'), 'Uninstaller retained nova PATH'
    print('PASS: clean per-user installation, EXE/Qt startup, running-host upgrade/uninstall, exact-owned integration cleanup and private-settings preservation.')


if __name__ == '__main__': main()
