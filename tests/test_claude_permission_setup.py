"""Temporary settings only; never touches the user's Claude installation or hooks."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from claude_permission_setup import update,hook,state
from permission_policy import release_ready,selected


class PermissionSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)/'home';self.home.mkdir()
        self.root=Path(self.tmp.name)/"Monitor $ literal's path";self.root.mkdir()
        (self.root/'AI-Monitor-Permission.exe').write_bytes(b'fixture-not-executable')
        self.settings=self.home/'.claude/settings.json'

    def test_exec_form_preserves_paths_and_has_no_shell_or_input_interpolation(self):
        value=hook(self.root)
        self.assertEqual(value,dict(type='command',command=str(self.root.resolve()/'AI-Monitor-Permission.exe'),args=[],timeout=30))
        self.assertNotIn('shell',value)

    def test_install_is_opt_in_preserves_rules_and_observers_and_is_idempotent(self):
        self.settings.parent.mkdir()
        original={'permissions':{'deny':['Bash(fixture)']},'hooks':{
            'PermissionRequest':[{'matcher':'Read','hooks':[{'type':'command','command':'custom-observer'}]}],
            'Stop':[{'hooks':[{'type':'command','command':'custom-stop'}]}]}}
        self.settings.write_text(json.dumps(original))
        before=self.settings.read_bytes()
        with self.assertRaises(ValueError):update(self.root,home=self.home)
        self.assertEqual(self.settings.read_bytes(),before)
        update(self.root,home=self.home,opted_in=True)
        linked=json.loads(self.settings.read_text());self.assertEqual(linked['permissions'],original['permissions'])
        self.assertEqual(linked['hooks']['Stop'],original['hooks']['Stop'])
        self.assertEqual(linked['hooks']['PermissionRequest'][0],original['hooks']['PermissionRequest'][0])
        self.assertEqual(state(self.root,self.home),'installed')
        self.assertEqual(len(list(self.settings.parent.glob('*backup*.json'))),1)
        update(self.root,home=self.home,opted_in=True)
        self.assertEqual(len(list(self.settings.parent.glob('*backup*.json'))),1)
        update(self.root,remove=True,home=self.home)
        self.assertEqual(json.loads(self.settings.read_text()),original)

    def test_removal_preserves_other_hooks_in_shared_entry_and_other_installations(self):
        own=hook(self.root);other=dict(type='command',command='other-helper',args=[],timeout=30)
        self.settings.parent.mkdir()
        self.settings.write_text(json.dumps({'hooks':{'PermissionRequest':[{'matcher':'','hooks':[own,other]}]}}))
        update(self.root,remove=True,home=self.home)
        self.assertEqual(json.loads(self.settings.read_text())['hooks']['PermissionRequest'][0]['hooks'],[other])

    def test_invalid_settings_or_missing_helper_are_not_overwritten(self):
        self.settings.parent.mkdir();self.settings.write_text('{invalid')
        before=self.settings.read_bytes()
        with self.assertRaises(ValueError):update(self.root,home=self.home,opted_in=True)
        self.assertEqual(self.settings.read_bytes(),before)
        (self.root/'AI-Monitor-Permission.exe').unlink()
        with self.assertRaises(ValueError):update(self.root,home=self.home,opted_in=True)
        self.assertEqual(self.settings.read_bytes(),before)

    def test_removal_preserves_custom_entry_metadata_even_without_other_hooks(self):
        self.settings.parent.mkdir()
        self.settings.write_text(json.dumps({'hooks':{'PermissionRequest':[
            {'matcher':'','hooks':[hook(self.root)],'custom':{'keep':True}}]}}))
        update(self.root,remove=True,home=self.home)
        self.assertEqual(json.loads(self.settings.read_text())['hooks']['PermissionRequest'],
                         [{'matcher':'','hooks':[],'custom':{'keep':True}}])

    def test_release_gate_cannot_be_enabled_by_preferences_or_provider_choice(self):
        self.assertFalse(release_ready())
        for config in ({},{'usb_permissions':1,'board':'guition-p4','providers':['claude']},
                       {'usb_permissions':True,'board':'waveshare-s3-43','providers':['claude']},
                       {'usb_permissions':True,'board':'guition-p4','providers':['codex']}):
            self.assertFalse(selected(config))
        self.assertTrue(selected({'usb_permissions':True,'board':'guition-p4','providers':['claude']}))
        self.assertFalse(release_ready())

if __name__=='__main__':unittest.main()
