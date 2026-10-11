"""Connection health, recovery and settings regressions without real USB/accounts."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import aim_control as control
import aim_host as host
import desktop_support as desktop
import codex_support as codex
from host_status import HostStatus, read_status, validate_options
from token_activity import TokenReporter


class HostSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); (self.root/'tools').mkdir()

    def test_health_rejects_old_process_and_stale_connection(self):
        health = HostStatus(self.root/'tools')
        health.update('connected', 'COM6'); health.provider('codex', 'unavailable')
        self.assertEqual(read_status(self.root, {os.getpid()})['providers'], {'codex': 'unavailable'})
        self.assertIsNone(read_status(self.root, {999999}))
        with patch('host_status.time.time', return_value=health.data['updated_at'] + 46):
            self.assertIsNone(read_status(self.root, {os.getpid()}))
        self.assertIn('UNCONFIRMED', desktop.connection_summary(self.root, [Mock(pid=999999)]))

    def test_usb_connection_and_quota_failure_are_separate(self):
        health = HostStatus(self.root/'tools'); health.update('connected', 'COM6')
        health.provider('codex', 'unavailable')
        self.assertEqual(desktop.connection_summary(self.root, [Mock(pid=os.getpid())]), 'USB CONNECTED • COM6')
        health.update('reconnecting')
        self.assertIn('RECONNECTING', desktop.connection_summary(self.root, [Mock(pid=os.getpid())]))

    def test_health_never_accepts_raw_provider_reply_or_secret(self):
        health = HostStatus(self.root/'tools'); health.update('starting')
        with self.assertRaises(ValueError): health.provider('codex', 'fixture-private-key')
        with self.assertRaises(ValueError): health.provider('arbitrary-command', 'ready')
        self.assertNotIn('fixture-private-key', health.path.read_text())

    def test_health_write_failure_does_not_break_host(self):
        health = HostStatus(self.root/'tools')
        with patch('host_status.os.replace', side_effect=PermissionError): health.update('connected', 'COM6')
        self.assertFalse(list((self.root/'tools').glob('*.tmp')))

    def test_preferences_validate_before_config_replacement(self):
        control.save_config(dict(host.DEFAULT_CONFIG, board='guition-p4', providers=['gemini'], zai_key='fixture-key'), self.root)
        before = (self.root/'tools/aim_host.json').read_bytes()
        for options in ({'reconnect_s': True}, {'reconnect_s': 1}, {'token_poll_s': 16},
                        {'keep_host_on_close': 'true'}, {'log_font_size': 50}, {'endpoint': 'http://bad.invalid'}):
            with self.assertRaises(ValueError):
                desktop.save_settings(self.root, 'guition-p4', ['gemini'], 'COM6', 60, options=options)
            self.assertEqual((self.root/'tools/aim_host.json').read_bytes(), before)
        updated = desktop.save_settings(self.root, 'guition-p4', ['gemini'], 'COM6', 60,
            options={'reconnect_s': 10, 'token_poll_s': 6, 'log_font_size': 14, 'keep_host_on_close': False})
        self.assertEqual(updated['zai_key'], 'fixture-key'); self.assertEqual(updated['token_poll_s'], 6)
        self.assertFalse(updated['start_host_on_open'])

    def test_invalid_config_recovery_keeps_exact_private_original_and_requires_invalid_file(self):
        source = self.root/'tools/aim_host.json'; original = b'{"broken":"fixture-key",'
        source.write_bytes(original)
        with patch.object(control, 'stop_host') as stop: desktop.reset_invalid_settings(self.root)
        stop.assert_called_once_with(self.root, emit=print)
        backup = list(source.parent.glob('aim_host.invalid-*.json'))
        self.assertEqual(len(backup), 1); self.assertEqual(backup[0].read_bytes(), original)
        self.assertEqual(control.local_config(self.root)['providers'], [])
        with self.assertRaises(control.SetupError): desktop.reset_invalid_settings(self.root)

    def test_connection_check_never_flashes_or_fetches_account_quota(self):
        control.save_config(dict(host.DEFAULT_CONFIG, board='guition-p4', providers=['gemini'], port='COM6'), self.root)
        panel = Mock(); panel.wait_for.return_value = {'boardId': 'guition-p4', 'chip': 'esp32p4'}
        emit = Mock()
        with patch.object(control, 'owned_hosts', return_value=[]), patch.object(host, 'Panel', return_value=panel), \
             patch.object(desktop.time, 'sleep'), patch.object(control, 'flash_command') as flash, \
             patch.object(host, 'fetch_codex') as fetch:
            desktop.check_connection(self.root, emit)
        panel.close.assert_called_once(); flash.assert_not_called(); fetch.assert_not_called()
        self.assertEqual(json.loads(panel.send_line.call_args.args[0]), {'cmd': 'get_info'})
        self.assertIn('Verified', emit.call_args.args[0])

    def test_wrong_board_and_busy_host_are_actionable_without_stopping_it(self):
        control.save_config(dict(host.DEFAULT_CONFIG, board='guition-p4', providers=['gemini'], port='COM6'), self.root)
        with patch.object(control, 'owned_hosts', return_value=[Mock(pid=99999)]), patch.object(control, 'stop_host') as stop:
            with self.assertRaisesRegex(control.SetupError, 'Stop host'): desktop.check_connection(self.root, Mock())
            stop.assert_not_called()
        panel = Mock(); panel.wait_for.return_value = {'boardId': 'waveshare-s3-43', 'chip': 'esp32s3'}
        with patch.object(control, 'owned_hosts', return_value=[]), patch.object(host, 'Panel', return_value=panel), patch.object(desktop.time, 'sleep'):
            with self.assertRaisesRegex(control.SetupError, 'does not report'): desktop.check_connection(self.root, Mock())
        panel.close.assert_called_once()

    def test_disconnected_wait_returns_promptly_for_saved_usb_change(self):
        watcher = Mock(); watcher.pending = {}
        with patch.object(host.time, 'sleep') as sleep: host.wait_for_config(watcher, 60)
        watcher.check.assert_called_once(); sleep.assert_called_once()

    def test_token_poll_interval_is_independent_of_quota_poll(self):
        now = [0]
        reporter = TokenReporter(home=self.root, providers=[], clock=lambda: now[0]); reporter.poll_seconds = 6
        self.assertIsNotNone(reporter.poll()); now[0] = 2; self.assertIsNone(reporter.poll())
        now[0] = 6; self.assertIsNotNone(reporter.poll())

    def test_provider_failure_is_unavailable_even_when_display_acknowledges_frame(self):
        panel = Mock(); panel.health = HostStatus(self.root/'tools'); panel.health.update('connected', 'COM6')
        with patch.object(host, 'fetch_codex', return_value=(None, 'Codex quota unavailable')), patch.object(host, 'LOG'):
            host.poll_cycle(host.DEFAULT_CONFIG, '', ['codex'], 100, panel)
        panel.wait_for.assert_called_once_with('ack', seconds=2, frame_id=101)
        self.assertFalse(panel.last_poll_success)
        self.assertEqual(read_status(self.root, {os.getpid()})['providers']['codex'], 'unavailable')

    def test_keyless_zcode_is_activity_only_and_clears_old_quota_backoff(self):
        panel = Mock(); panel.health = HostStatus(self.root/'tools')
        panel.health.update('connected', 'COM6')
        panel.retries = host.ProviderRetries(240)
        panel.retries.failed('zcode', 'old invalid key')
        panel.fetcher = Mock(spec=host.FetchPool)
        with patch.object(host, 'fetch_zcode') as fetch, patch.object(host, 'LOG'):
            host.poll_cycle(host.DEFAULT_CONFIG, '', ['zcode'], 100, panel)
        fetch.assert_not_called(); panel.fetcher.fetch.assert_not_called()
        self.assertTrue(panel.last_poll_success)
        self.assertEqual(panel.retries.remaining('zcode'), 0)
        self.assertEqual(read_status(self.root, {os.getpid()})['providers']['zcode'], 'activity_only')
        data = json.loads(panel.send_frame.call_args.args[0])['data'][0]
        self.assertTrue(data['informational']); self.assertNotIn('usage', data)
        self.assertIn('add a Z.AI key for quota', data['notice'])
        panel.wait_for.assert_called_once_with('ack', seconds=2, frame_id=101)

    def test_invalid_start_preferences_cannot_replace_working_host(self):
        control.save_config(dict(host.DEFAULT_CONFIG, board='guition-p4', providers=['gemini'], port='COM9999', token_poll_s=False), self.root)
        with patch.object(control, 'stop_host') as stop, patch.object(control.subprocess, 'Popen') as spawn:
            with self.assertRaises(ValueError): control.start_host(self.root)
        stop.assert_not_called(); spawn.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows install layout')
    def test_native_codex_is_found_with_no_cli_on_explorer_path(self):
        executable = self.root/'OpenAI/Codex/bin/version-123/codex.exe'
        executable.parent.mkdir(parents=True); executable.touch()
        with patch.dict(os.environ, {'LOCALAPPDATA': str(self.root), 'CODEX_INSTALL_DIR': '', 'APPDATA': str(self.root)}), \
             patch.object(codex, 'path_executable', return_value=None):
            self.assertEqual(codex.codex_command(), [str(executable)])
