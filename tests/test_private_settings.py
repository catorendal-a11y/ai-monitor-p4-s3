"""Real file protection on synthetic settings; never reads the user's settings."""
import ctypes
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))

def protected(path):
    if os.name!='nt':return stat.S_IMODE(path.stat().st_mode)&0o077==0
    api=ctypes.WinDLL('advapi32',use_last_error=True)
    size=ctypes.c_ulong()
    api.GetFileSecurityW(str(path),4,None,0,ctypes.byref(size))
    buffer=ctypes.create_string_buffer(size.value)
    if not api.GetFileSecurityW(str(path),4,buffer,size,ctypes.byref(size)):raise ctypes.WinError(ctypes.get_last_error())
    control=ctypes.c_ushort();revision=ctypes.c_ulong()
    if not api.GetSecurityDescriptorControl(buffer,ctypes.byref(control),ctypes.byref(revision)):raise ctypes.WinError(ctypes.get_last_error())
    return bool(control.value&0x1000)

class PrivateSettingsTests(unittest.TestCase):
    def test_settings_and_all_provider_backups_are_private(self):
        from provider_setup import claude_bridge,claude_session_link
        from claude_permission_setup import update
        from aim_control import save_config
        from telemetry_bridge import write_record
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);home=root/'home';settings=home/'.claude/settings.json'
            settings.parent.mkdir(parents=True);settings.write_text('{"env":{"SYNTHETIC_KEY":"fixture"}}')
            for name in ('AI-Monitor-Events.exe','AI-Monitor-Permission.exe'):(root/name).write_bytes(b'fixture')
            for operation in (lambda:claude_bridge(root,home=home),lambda:claude_session_link(root,home=home),
                              lambda:update(root,home=home,opted_in=True)):
                operation()
                self.assertTrue(protected(settings),'Settings lost protected ACL/private mode')
                for backup in settings.parent.glob('*backup*.json'):
                    self.assertTrue(protected(backup),'Backup must be private before copying secrets')
                    self.assertEqual(json.loads(backup.read_text())['env']['SYNTHETIC_KEY'],'fixture')
            save_config({'providers':['claude'],'usage_history':True,'zai_key':'fixture'},root)
            self.assertTrue(protected(root/'tools/aim_host.json'))
            write_record(root/'numeric.json',{'count':1})
            self.assertTrue(protected(root/'numeric.json'))

    def test_failed_protection_never_replaces_original_or_writes_secret(self):
        import private_files
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'settings.json';path.write_bytes(b'old')
            with patch.object(private_files,'protect',side_effect=OSError('Synthetic ACL failure')):
                with self.assertRaises(OSError):private_files.write_json(path,{'synthetic':'secret'})
            self.assertEqual(path.read_bytes(),b'old')
            self.assertEqual(list(path.parent.glob('*.tmp')),[])

    def test_temporary_is_already_private_when_prewrite_validation_runs(self):
        import private_files
        original=private_files.protect
        checked=[]
        def verify(path):
            checked.append(True)
            self.assertTrue(protected(Path(path)),'The temporary must be private from creation')
            self.assertEqual(Path(path).read_bytes(),b'')
            return original(path)
        with tempfile.TemporaryDirectory() as d,patch.object(private_files,'protect',side_effect=verify):
            private_files.write_json(Path(d)/'settings.json',{'synthetic':'fixture'})
        self.assertEqual(checked,[True])

    def test_stop_revokes_consent_even_without_a_running_host(self):
        import aim_control
        from agent_history import configure
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);activity=root/'tools/activity';configure(activity,True,123)
            with patch.object(aim_control,'owned_hosts',return_value=[]):aim_control.stop_host(root,emit=lambda _:None)
            self.assertFalse(json.loads((activity/'agent-history-consent.json').read_text())['enabled'])

    def test_saving_disabled_history_revokes_previous_consent(self):
        from aim_control import save_config
        from agent_history import configure
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);configure(root/'tools/activity',True,123)
            save_config({'providers':['claude'],'usage_history':False},root)
            self.assertFalse(json.loads((root/'tools/activity/agent-history-consent.json').read_text())['enabled'])

    def test_recovery_backup_keeps_original_bytes_and_private_protection(self):
        import aim_control as control
        import desktop_support as desktop
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            control.save_config(dict(control.host.DEFAULT_CONFIG,board='not-a-board',zai_key='synthetic-private-key'),root)
            original=(root/'tools/aim_host.json').read_bytes()
            with patch.object(control,'owned_hosts',return_value=[]):desktop.reset_invalid_settings(root,emit=lambda _:None)
            backup=next((root/'tools').glob('aim_host.invalid-*.json'))
            self.assertEqual(backup.read_bytes(),original)
            self.assertTrue(protected(backup),'Recovery must not create a weaker private copy')

    def test_failed_consent_revocation_does_not_persist_new_settings(self):
        import aim_control as control
        import desktop_support as desktop
        import private_files
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            control.save_config(dict(control.host.DEFAULT_CONFIG,board='guition-p4',providers=['claude'],usage_history=True),root)
            from agent_history import configure
            configure(root/'tools/activity',True,123)
            before=(root/'tools/aim_host.json').read_bytes();original=private_files.write_bytes
            def fail_consent(path,data):
                if Path(path).parent==root/'tools/activity':raise OSError('Synthetic consent-storage failure')
                return original(path,data)
            with patch.object(private_files,'write_bytes',side_effect=fail_consent):
                with self.assertRaises(OSError):
                    desktop.save_settings(root,'guition-p4',['claude'],'COM6',30,key='new-fixture-key',options={'usage_history':False})
            self.assertEqual((root/'tools/aim_host.json').read_bytes(),before)
