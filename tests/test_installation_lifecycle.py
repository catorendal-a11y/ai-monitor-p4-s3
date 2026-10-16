import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))

class LifecycleTests(unittest.TestCase):
    def test_upgrade_stops_only_scoped_host_and_preserves_integrations(self):
        import installation_lifecycle as life
        with tempfile.TemporaryDirectory() as td, patch('aim_control.stop_host') as stop, patch('aim_control.owned_hosts',return_value=[]), patch.object(life,'remove_startup_task') as task, patch.object(life,'remove_integrations') as hooks:
            life.prepare(Path(td))
            self.assertEqual(stop.call_args.args,(Path(td).resolve(),))
            task.assert_not_called(); hooks.assert_not_called()

    def test_failed_stop_never_removes_integrations(self):
        import installation_lifecycle as life
        with tempfile.TemporaryDirectory() as td, patch('aim_control.stop_host'), patch('aim_control.owned_hosts',return_value=[object()]), patch.object(life,'remove_integrations') as hooks:
            with self.assertRaises(RuntimeError): life.prepare(Path(td),uninstall=True)
            hooks.assert_not_called()

    def test_uninstall_preserves_private_configuration_and_custom_hooks(self):
        import installation_lifecycle as life
        import provider_setup as providers
        import json
        with tempfile.TemporaryDirectory() as td, patch('aim_control.stop_host'), patch('aim_control.owned_hosts',return_value=[]), patch.object(life,'remove_startup_task'):
            root=(Path(td)/'app').resolve(); root.mkdir(); home=Path(td)/'home'; home.mkdir()
            (root/'tools').mkdir(); config=root/'tools/aim_host.json'; config.write_text('{"fixture":"private","usage_history":false}')
            for link in (providers.codex_session_link,providers.claude_session_link,providers.zcode_session_link): link(root,home=home)
            providers.claude_bridge(root,home=home)
            path=home/'.claude/settings.json'; data=json.loads(path.read_text()); data['env']={'fixture':'preserve'}; data['hooks']['Stop'][0]['hooks'].append({'type':'command','command':'custom-user-observer'}); path.write_text(json.dumps(data))
            before=config.read_bytes(); life.prepare(root,uninstall=True,home=home)
            self.assertEqual(config.read_bytes(),before)
            self.assertEqual(providers.codex_session_state(root,home=home),'not linked')
            self.assertEqual(providers.zcode_session_state(root,home=home),'not linked')
            data=json.loads(path.read_text()); self.assertNotIn('statusLine',data); self.assertEqual(data['env'],{'fixture':'preserve'})
            self.assertEqual(data['hooks']['Stop'][0]['hooks'],[{'type':'command','command':'custom-user-observer'}])

    def test_task_cleanup_is_bounded_and_uses_exact_installation(self):
        import installation_lifecycle as life
        with patch.object(life.subprocess,'run',return_value=Mock(returncode=0,stdout='removed')) as run:
            life.remove_startup_task(Path('C:/fixture/app'))
            kw=run.call_args.kwargs; self.assertLessEqual(kw['timeout'],15)
            command=' '.join(run.call_args.args[0]); self.assertIn('AI Monitor Host',command); self.assertIn('AI-Monitor.exe',command); self.assertIn('--start-host',command); self.assertIn('Principal',command)

    def test_task_failure_blocks_uninstall(self):
        import installation_lifecycle as life
        with patch.object(life.subprocess,'run',return_value=Mock(returncode=1,stdout='sensitive errors')):
            with self.assertRaisesRegex(RuntimeError,'startup task'): life.remove_startup_task(Path('C:/fixture/app'))

    def test_observer_removal_preserves_custom_entry_metadata(self):
        import installation_lifecycle as life
        import provider_setup as providers
        import json
        with tempfile.TemporaryDirectory() as td:
            root=(Path(td)/'app').resolve(); root.mkdir(); home=Path(td)/'home'; home.mkdir()
            cases=((providers.codex_session_link,home/'.codex/hooks.json','Stop'),
                   (providers.claude_session_link,home/'.claude/settings.json','Stop'),
                   (providers.zcode_session_link,home/'.zcode/cli/config.json','TurnEnd'))
            for link,path,event in cases:
                link(root,home=home); data=json.loads(path.read_text())
                events=data['hooks'].get('events',data['hooks'])
                event=event if event in events else next(iter(events))
                events[event][0]['fixtureCustomMetadata']='preserve'
                expected=dict(events[event][0],hooks=[])
                path.write_text(json.dumps(data)); link(root,remove=True,home=home)
                after=json.loads(path.read_text())
                events=after.get('hooks',{}).get('events',after.get('hooks',{}))
                self.assertEqual(events[event],[expected])

    def test_custom_statusline_and_permission_hook_survive(self):
        import installation_lifecycle as life
        import json
        with tempfile.TemporaryDirectory() as td:
            root=(Path(td)/'app').resolve(); root.mkdir(); home=Path(td)/'home'
            path=home/'.claude/settings.json'; path.parent.mkdir(parents=True)
            custom={'type':'command','command':'custom'}
            original={'statusLine':custom,'hooks':{'PermissionRequest':[{'hooks':[custom]}]},'permissions':{'allow':['fixture']}}
            path.write_text(json.dumps(original)); life.remove_integrations(root,home=home)
            self.assertEqual(json.loads(path.read_text()),original)

    def test_invalid_client_settings_block_without_disclosing_content(self):
        import installation_lifecycle as life
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'app'; root.mkdir(); home=Path(td)/'home'
            path=home/'.claude/settings.json'; path.parent.mkdir(parents=True); path.write_text('{"hooks":"fixture-invalid"}')
            with self.assertRaises(ValueError): life.remove_integrations(root,home=home)

    @unittest.skipUnless(sys.platform=='win32','Windows task command mocks')
    def test_powershell_task_ownership_checks_with_mocked_scheduler(self):
        import installation_lifecycle as life
        import subprocess
        root=Path('C:/fixture/app')
        with patch.object(life.subprocess,'run',return_value=Mock(returncode=0)) as run:
            life.remove_startup_task(root)
            script=run.call_args.args[0][-1]
        executable=str(root.resolve()/'AI-Monitor.exe').replace("'","''")
        for mode in ('absent','foreign','owned','unavailable'):
            with self.subTest(mode=mode):
                fixture=("$script:removed=$false; function Get-ScheduledTask { "
                    + ("throw 'unavailable'" if mode=='unavailable' else "if ($script:removed) { return }; "
                       + ("return" if mode=='absent' else
                          "[pscustomobject]@{TaskName='AI Monitor Host'; Principal=[pscustomobject]@{UserId=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value};Actions=@([pscustomobject]@{Execute='"+
                          (executable if mode=='owned' else 'C:/other/AI-Monitor.exe')+"';Arguments='--start-host'})}"))
                    + " }; function Unregister-ScheduledTask { $script:removed=$true; Write-Output 'fixture-removed' }; ")
                result=subprocess.run([life.powershell_executable(),'-NoProfile','-NonInteractive','-Command',fixture+script],capture_output=True,text=True,timeout=12)
                self.assertEqual(result.returncode,1 if mode=='unavailable' else 0)
                self.assertEqual('fixture-removed' in result.stdout,mode=='owned')

    def test_installer_runs_preflight_before_deleting_executables(self):
        script=(Path(__file__).resolve().parents[1]/'scripts/windows_installer.iss').read_text()
        self.assertIn('InitializeUninstall',script); self.assertIn('--prepare-uninstall',script)
        self.assertIn('PrepareToInstall',script); self.assertIn('--prepare-upgrade',script)

if __name__=='__main__': unittest.main()

