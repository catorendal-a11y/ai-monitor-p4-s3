"""Synthetic native desktop flows; no panel, cloud request or real credentials."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import aim_control as control
import desktop_support as desktop
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


class DesktopSettingsTests(unittest.TestCase):
    def test_identity_probe_retries_slow_serial_boot_and_has_a_fixed_limit(self):
        read = Mock(side_effect=[TimeoutError('booting'), {'boardId':'guition-p4'}])
        with patch.object(desktop.time, 'sleep'):
            self.assertEqual(desktop._wait_for_boot(read)['boardId'], 'guition-p4')
        self.assertEqual(read.call_count, 2)
        read = Mock(side_effect=TimeoutError('still unavailable'))
        with patch.object(desktop.time, 'sleep'), self.assertRaises(TimeoutError):
            desktop._wait_for_boot(read)
        self.assertEqual(read.call_count, 3)
        read = Mock(side_effect=RuntimeError('wrong board'))
        with self.assertRaises(RuntimeError): desktop._wait_for_boot(read)
        self.assertEqual(read.call_count, 1)

    def test_update_waits_for_boot_but_timeout_cannot_start_a_write(self):
        panel = Mock()
        for outcomes, writes in (([TimeoutError('booting'), None], 1),
                                 (TimeoutError('unavailable'), 0)):
            panel.reset_mock(); panel.heartbeat.side_effect = outcomes
            with patch.object(desktop, 'prepare_flash', return_value=('COM6',['flasher'])), \
                    patch.object(control, 'stop_host'), patch.object(control.host, 'Panel', return_value=panel), \
                    patch.object(desktop.time, 'sleep'), patch.object(desktop, 'verify_firmware_boot') as boot, \
                    patch.object(desktop, 'run_firmware_command') as write:
                if writes:
                    desktop.write_firmware(Path('.'), 'guition-p4', 'update', 'COM6', Mock())
                else:
                    with self.assertRaises(control.SetupError):
                        desktop.write_firmware(Path('.'), 'guition-p4', 'update', 'COM6', Mock())
                self.assertEqual(write.call_count, writes)
                self.assertEqual(boot.call_count, writes)
                panel.close.assert_called_once()

    def test_post_flash_boot_reopens_only_selected_port_after_usb_returns(self):
        panel = Mock()
        with patch.object(control.host, 'Panel', side_effect=[OSError('re-enumerating'), panel]) as opened, \
                patch.object(desktop.time, 'sleep'):
            desktop.verify_firmware_boot('guition-p4', 'COM6')
        self.assertEqual(opened.call_args_list, [unittest.mock.call('COM6')] * 2)
        panel.heartbeat.assert_called_once()
        panel.close.assert_called_once()
        self.assertEqual(panel.expected_board.id, 'guition-p4')

    def test_post_flash_no_response_is_bounded_and_does_not_report_success(self):
        panel = Mock(); panel.heartbeat.side_effect = TimeoutError('unavailable')
        with patch.object(control.host, 'Panel', return_value=panel) as opened, \
                patch.object(desktop.time, 'sleep'), \
                self.assertRaisesRegex(control.SetupError, 'written, but startup could not be confirmed'):
            desktop.verify_firmware_boot('guition-p4', 'COM6')
        self.assertEqual(opened.call_count, 3)
        self.assertEqual(panel.heartbeat.call_count, 9)
        self.assertEqual(panel.close.call_count, 3)

    def test_post_flash_wrong_identity_does_not_retry(self):
        panel = Mock(); panel.heartbeat.side_effect = RuntimeError('wrong board')
        with patch.object(control.host, 'Panel', return_value=panel) as opened, \
                patch.object(desktop.time, 'sleep'), \
                self.assertRaisesRegex(control.SetupError, 'identity does not match'):
            desktop.verify_firmware_boot('guition-p4', 'COM6')
        opened.assert_called_once_with('COM6')
        panel.close.assert_called_once()

    @unittest.skipUnless(os.name=='nt','Windows sharing-lock retry')
    def test_transient_windows_lock_keeps_atomic_config_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            control.save_config(dict(control.host.DEFAULT_CONFIG),root)
            replace=control.os.replace
            attempts=[]
            def transient(source,target):
                attempts.append(target)
                if len(attempts)==1:
                    error=PermissionError('synthetic sharing lock'); error.winerror=32
                    raise error
                return replace(source,target)
            with patch.object(control.os,'replace',side_effect=transient), patch.object(control.time,'sleep'):
                control.save_config(dict(control.host.DEFAULT_CONFIG,board='guition-p4',providers=['gemini']),root)
            self.assertEqual(control.local_config(root)['providers'],['gemini'])
            self.assertEqual(len(attempts),2)
            self.assertFalse(list((root/'tools').glob('*.tmp')))

    def test_preserves_existing_key_and_extra_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control.save_config(dict(control.host.DEFAULT_CONFIG, board='guition-p4',
                                     providers=['zcode'], zai_key='fixture-private-key', custom=True), root)
            config = desktop.save_settings(root, 'waveshare-s3-43', ['gemini'], 'COM7', 60)
            self.assertEqual(config['zai_key'], 'fixture-private-key')
            self.assertTrue(config['custom'])
            self.assertEqual(config['board'], 'waveshare-s3-43')
            self.assertEqual(config['providers'], ['gemini'])
            self.assertEqual(desktop.save_settings(root, 'guition-p4', ['zcode'], 'auto', 240, clear_key=True)['zai_key'], '')

    def test_invalid_settings_never_replace_existing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control.save_config(dict(control.host.DEFAULT_CONFIG, board='guition-p4', providers=['gemini']), root)
            before = (root/'tools/aim_host.json').read_bytes()
            invalid = [('bad-board', ['gemini'], 'COM6', 60, ''),
                       ('guition-p4', [], 'COM6', 60, ''),
                       ('guition-p4', ['gemini'], 'https://attacker.invalid', 60, ''),
                       ('guition-p4', ['gemini'], 'COM6', True, ''),
                       ('guition-p4', ['gemini'], 'COM6', 60, 'secret\ninvalid')]
            for args in invalid:
                with self.assertRaises(ValueError): desktop.save_settings(root, *args)
                self.assertEqual((root/'tools/aim_host.json').read_bytes(), before)

    def test_log_is_bounded_and_redacts_keys_and_control_sequences(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'tools').mkdir()
            (root/'tools/aim_host.log').write_text('discard\n'*5000+'fixture-key\x1b[31m\nlast message\n')
            log=desktop.recent_log(root, ('fixture-key',))
            self.assertNotIn('fixture-key', log)
            self.assertNotIn('\x1b', log)
            self.assertIn('[REDACTED]', log)
            self.assertTrue(log.endswith('last message'))
            self.assertLessEqual(len(log.splitlines()), 100)

    def test_flash_revalidates_configuration_before_stopping_host(self):
        with patch.object(desktop, 'prepare_flash', return_value=('COM7', ['flasher'])), \
                patch.object(control, 'stop_host') as stop, patch.object(desktop.subprocess, 'Popen') as spawn:
            with self.assertRaises(control.SetupError):
                desktop.write_firmware(Path('.'), 'waveshare-s3-43', 'install', 'COM6', Mock())
        stop.assert_not_called(); spawn.assert_not_called()

    def test_application_update_requires_verified_panel_before_flashing(self):
        panel=Mock(); panel.heartbeat.side_effect=RuntimeError('synthetic wrong board')
        with patch.object(desktop, 'prepare_flash', return_value=('COM7', ['flasher'])), \
                patch.object(control, 'stop_host'), patch.object(control.host, 'Panel', return_value=panel), \
                patch.object(desktop.time, 'sleep'), patch.object(desktop.subprocess, 'Popen') as spawn:
            with self.assertRaises(control.SetupError):
                desktop.write_firmware(Path('.'), 'waveshare-s3-43', 'update', 'COM7', Mock())
        panel.close.assert_called_once(); spawn.assert_not_called()

    def test_console_host_is_owned_only_with_the_scoped_host_argument(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ours=Mock(pid=123,info={'exe':str(root/'AI-Monitor-Console.exe'),'cmdline':['AI-Monitor-Console.exe','--host']})
            setup=Mock(pid=124,info={'exe':str(root/'AI-Monitor-Console.exe'),'cmdline':['AI-Monitor-Console.exe','--integrations']})
            other=Mock(pid=125,info={'exe':str(root/'other/AI-Monitor-Console.exe'),'cmdline':['AI-Monitor-Console.exe','--host']})
            with patch.object(control.psutil, 'process_iter', return_value=[ours,setup,other]):
                self.assertEqual(control.owned_hosts(root), [ours])




if __name__ == '__main__': unittest.main()
