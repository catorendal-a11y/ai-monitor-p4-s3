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
