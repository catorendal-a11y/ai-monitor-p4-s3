"""Terminal control actions reuse the desktop safeguards without real hardware/configuration."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from terminal_actions import TerminalActions
import terminal_actions as actions


class TerminalActionsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.service=TerminalActions(self.root)
        self.config=dict(board='guition-p4',port='COM6',providers=['codex'],zai_key='SAVED_SECRET',usage_history=True)
        self.config_mock=patch.object(actions.control,'local_config',return_value=self.config)
        self.config_mock.start();self.addCleanup(self.config_mock.stop)

    def test_explicit_start_stop_use_selected_root(self):
        for name in ('start','stop'):
            with patch.object(actions.control,name+'_host') as call:
                self.service.execute(name)
                self.assertEqual(call.call_args.args[0],self.root)

    def test_start_does_not_replace_an_existing_owner(self):
        with patch.object(actions.control,'owned_hosts',return_value=[Mock(pid=12)]),patch.object(actions.control,'start_host') as start:
            self.assertIn('already running',self.service.execute('start')['output']);start.assert_not_called()

    def test_history_clear_requires_confirmation_before_touching_writer(self):
        with patch.object(actions.desktop,'clear_local_history') as clear:
            with self.assertRaises(ValueError):self.service.execute('clear_history')
            clear.assert_not_called()
            self.service.execute('clear_history',{'confirm':'CLEAR'})
            clear.assert_called_once()

    def test_save_preserves_secrets_unless_explicit_and_never_returns_them(self):
        with patch.object(actions.desktop,'save_settings',return_value=self.config) as save:
            result=self.service.execute('save',dict(board='guition-p4',port='COM6',providers=['codex'],interval=30,
                                                 key='',clear_key=False,options={'usage_history':True}))
            self.assertEqual(save.call_args.kwargs['key'],'')
            self.assertNotIn('SAVED_SECRET',repr(result))

    def test_firmware_needs_preparation_then_typed_confirmation_and_no_retry(self):
        with patch.object(actions.desktop,'prepare_flash',return_value=('COM6',[])) as prepare,\
             patch.object(actions.desktop,'write_firmware') as write:
            with self.assertRaises(ValueError):self.service.execute('flash',{'confirm':'FLASH'})
            write.assert_not_called()
            self.service.execute('prepare_flash',{'kind':'update'})
            with self.assertRaises(ValueError):self.service.execute('flash',{'confirm':'yes'})
            self.service.execute('flash',{'confirm':'FLASH'})
            self.assertEqual(write.call_args.args[:4],(self.root,'guition-p4','update','COM6'))
            with self.assertRaises(ValueError):self.service.execute('flash',{'confirm':'FLASH'})
            self.assertEqual(write.call_count,1)

    def test_link_requires_selected_provider_and_confirmation(self):
        with patch('provider_setup.codex_session_link',return_value='Linked') as link:
            with self.assertRaises(ValueError):self.service.execute('link_events',{'provider':'codex'})
            self.service.execute('link_events',{'provider':'codex','confirm':'LINK'})
            link.assert_called_once_with(self.root,remove=False)
            with self.assertRaises(ValueError):self.service.execute('link_events',{'provider':'claude','confirm':'LINK'})

    def test_action_output_redacts_saved_and_new_secrets_and_escape_characters(self):
        with patch.object(actions.control,'start_host',side_effect=lambda root,emit:emit('SAVED_SECRET\x1b[31m')):
            result=self.service.execute('start')
        self.assertNotIn('SAVED_SECRET',repr(result));self.assertNotIn('\x1b',repr(result))

    def test_no_arbitrary_command_or_path_overwrite(self):
        with self.assertRaises(ValueError):self.service.execute('shell',{'command':'anything'})
        path=self.root/'existing.json';path.write_text('keep',encoding='utf-8')
        with self.assertRaises(ValueError):self.service.execute('diagnostics',{'path':str(path)})
        self.assertEqual(path.read_text(encoding='utf-8'),'keep')

    def test_readiness_settings_ports_and_usb_route_to_shared_functions(self):
        result=self.service.execute('settings');self.assertNotIn('zai_key',result['settings'])
        with patch.object(actions.control.list_ports,'comports',return_value=[Mock(device='COM6')]):
            self.assertEqual(self.service.execute('ports')['ports'],['COM6'])
        with patch.object(actions.desktop,'check_connection') as check:
            self.service.execute('check_usb');self.assertEqual(check.call_args.args[0],self.root)
        with patch('provider_setup.setup_report',return_value=[{'provider':'codex'}]):
            self.assertEqual(self.service.execute('setup_report')['providers'][0]['provider'],'codex')
        with patch.object(actions.desktop,'recent_log',return_value='Safe log'):
            self.assertEqual(self.service.execute('log')['log'],'Safe log')

    def test_quota_and_official_setup_remain_explicit(self):
        with patch('provider_setup.claude_bridge',return_value='Updated') as bridge:
            self.service.execute('unlink_quota',{'provider':'claude','confirm':'LINK'})
            bridge.assert_called_once_with(self.root,remove=True)
        with patch.object(actions.desktop,'open_integrations') as setup:
            self.service.execute('codex_setup',{'confirm':'SETUP'});setup.assert_called_once_with(self.root,codex_only=True)
        with patch.object(actions.desktop,'reset_invalid_settings') as reset:
            with patch.object(actions.control,'local_config',side_effect=ValueError('private')):
                self.service.execute('recover',{'confirm':'RESET'})
            reset.assert_called_once()

    def test_numeric_history_and_diagnostic_exports_are_exclusive(self):
        report=dict(tokens=[dict(provider='codex',date='2026-10-16',total=42)],
                    quota=[dict(provider='codex',minute=100,used=71,window=300,kind='model',reset=9000)],
                    daily_agents=[dict(provider='codex',date='2026-10-16',sessions=None,completedTurns=1)],error=None)
        with patch('usage_history.read_history',return_value=report):
            self.assertEqual(self.service.execute('history_report',{'days':30})['history'],report)
            path=self.root/'history.csv';self.service.execute('export_history',{'path':str(path),'days':7})
            self.assertIn('observed_tokens',path.read_text(encoding='utf-8'))
            self.assertNotIn('None',path.read_text(encoding='utf-8'))
        with patch.object(actions,'read_status',return_value=None),patch.object(actions.control,'owned_hosts',return_value=[]):
            path=self.root/'diagnostics.json';self.service.execute('diagnostics',{'path':str(path)})
            self.assertNotIn('SAVED_SECRET',path.read_text(encoding='utf-8'))
        self.config['usage_history']=False
        with self.assertRaises(ValueError):self.service.execute('history_report')

    def test_companion_library_operations_do_not_claim_activation(self):
        import companion_packages as packs
        folder=self.root/'packs';folder.mkdir();(folder/('a'*64+'.pack')).write_bytes(b'fixture')
        from types import SimpleNamespace
        pack=SimpleNamespace(id='a'*64,name='Synthetic pack')
        with patch.object(packs,'directory',return_value=folder),patch.object(packs,'load',return_value=pack),\
             patch.object(packs,'selected',return_value=''),patch.object(packs,'select') as select,\
             patch.object(packs,'install',return_value=pack),patch.object(packs,'remove') as remove:
            self.assertEqual(self.service.execute('packs')['packs'][0]['name'],'Synthetic pack')
            self.service.execute('builtin');select.assert_called_with(self.root,'')
            self.service.execute('select_pack',{'id':pack.id});select.assert_called_with(self.root,pack.id)
            self.service.execute('import_pack',{'path':'fixture.zip','confirm':'IMPORT'})
            self.service.execute('remove_pack',{'id':pack.id,'confirm':'REMOVE'});remove.assert_called_once()

    def test_screen_receipt_uses_existing_owner_and_always_cancels_lease(self):
        with patch('mirror_service.request',return_value=23),patch('mirror_service.receive',return_value=(b'pixels',{})),\
             patch('mirror_service.cancel') as cancel:
            self.assertEqual(self.service.execute('screen')['pixels'],b'pixels')
            cancel.assert_called_once_with(self.root,23)
        with patch('enrollment_setup.connect_device') as connect:
            with self.assertRaises(ValueError):self.service.execute('connect_pc',{'confirm':'CONNECT'})
            self.service.comparison=Mock();self.service.execute('connect_pc',{'confirm':'CONNECT'})
            self.assertEqual(connect.call_args.args[:2],(self.root,self.service.comparison))
