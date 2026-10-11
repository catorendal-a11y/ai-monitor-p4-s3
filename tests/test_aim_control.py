import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import aim_control as control


class SetupTests(unittest.TestCase):
    def setUp(self):
        prepare = patch.object(control, 'setup_codex', return_value=True)
        prepare.start(); self.addCleanup(prepare.stop)
        ports = patch.object(control.list_ports, 'comports', return_value=[])
        ports.start(); self.addCleanup(ports.stop)
    def test_ambiguous_auto_port_fails_before_replacing_a_running_host(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control.save_config(dict(control.host.DEFAULT_CONFIG, providers=['codex'], board='guition-p4'), root)
            ports = [Mock(device='COM4', vid=0x303a), Mock(device='COM6', vid=0x303a)]
            with patch.object(control.list_ports, 'comports', return_value=ports), \
                    patch.object(control, 'stop_host') as stop, \
                    patch.object(control.subprocess, 'Popen') as spawn:
                with self.assertRaisesRegex(control.SetupError, 'COM4.*COM6'):
                    control.start_host(root)
            stop.assert_not_called(); spawn.assert_not_called()

    def test_explicit_port_works_with_multiple_matching_boards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control.save_config(dict(control.host.DEFAULT_CONFIG, providers=['codex'], board='guition-p4', port='COM6'), root)
            child = Mock(); child.poll.return_value = None
            with patch.object(control.list_ports, 'comports', return_value=[Mock(device='COM4', vid=0x303a), Mock(device='COM6', vid=0x303a)]), \
                    patch.object(control, 'stop_host'), patch.object(control.subprocess, 'Popen', return_value=child), \
                    patch.object(control.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
                control.start_host(root)
    def test_frozen_host_outlives_menu_using_independent_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control.save_config(dict(control.host.DEFAULT_CONFIG, providers=['codex'], board='guition-p4'), root)
            child = Mock(); child.poll.return_value = None
            with patch.object(control.sys, 'frozen', True, create=True), \
                    patch.object(control.host, 'load_config', return_value={'providers': ['codex'], 'board':'guition-p4'}), patch.object(control, 'stop_host'), \
                    patch.object(control.subprocess, 'Popen', return_value=child) as spawn, \
                    patch.object(control.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
                control.start_host(root)
            self.assertEqual(spawn.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')
            self.assertEqual(spawn.call_args.args[0][-1], '--host')

    def test_setup_preserves_existing_key_and_settings_without_printing_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {'port': 'COM6', 'zai_key': 'fixture-key', 'interval_s': 60, 'custom': True}
            control.save_config(config, root)
            output = io.StringIO()
            with contextlib.redirect_stdout(output), patch.object(control.list_ports, 'comports', return_value=[]):
                control.configure(root, ask=lambda _: '', read_secret=lambda _: '')
            self.assertEqual(control.local_config(root)['zai_key'], config['zai_key'])
            self.assertEqual(control.local_config(root)['interval_s'], 60)
            self.assertTrue(control.local_config(root)['custom'])
            self.assertNotIn(config['zai_key'], output.getvalue())
            self.assertFalse(list((root / 'tools').glob('*.tmp')))

    def test_invalid_key_cannot_replace_valid_local_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control.save_config(dict(control.host.DEFAULT_CONFIG, board='guition-p4', providers=['zcode']), root)
            before = (root / 'tools/aim_host.json').read_bytes()
            with contextlib.redirect_stdout(io.StringIO()), patch.object(control.list_ports, 'comports', return_value=[]):
                with self.assertRaises(ValueError):
                    control.configure(root, ask=lambda _: '', read_secret=lambda _: 'invalid\nsecret')
            self.assertEqual((root / 'tools/aim_host.json').read_bytes(), before)

    def test_numbered_port_selection_is_explicit_with_multiple_boards(self):
        ports = [Mock(device='COM6', description='Display'), Mock(device='COM4', description='Other board')]
        with patch.object(control.list_ports, 'comports', return_value=ports), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(control.choose_port(ask=lambda _: '2'), 'COM6')

    def test_malformed_config_is_preserved_and_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'tools').mkdir()
            path = root / 'tools/aim_host.json'; path.write_text('{broken')
            with self.assertRaises(control.SetupError):
                control.local_config(root)
            self.assertEqual(path.read_text(), '{broken')

    def test_host_control_ignores_other_checkouts_and_reused_python_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ours = Mock(pid=12345, info={'cmdline': ['python', str(root / 'tools/aim_host.py')], 'exe': sys.executable})
            other = Mock(pid=12346, info={'cmdline': ['python', str(root / 'other/tools/aim_host.py')], 'exe': sys.executable})
            reused = Mock(pid=12347, info={'cmdline': ['python', 'unrelated.py'], 'exe': sys.executable})
            with patch.object(control.psutil, 'process_iter', return_value=[ours, other, reused]):
                self.assertEqual(control.owned_hosts(root), [ours])

    def test_host_control_rejects_script_paths_used_as_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = str(root / 'tools/aim_host.py')
            commands = [(['editor.exe', script], str(root/'editor.exe')),
                        (['python', 'reader.py', script], sys.executable),
                        (['python', '-c', 'pass', script], sys.executable),
                        (['python', '-m', 'reader', script], sys.executable),
                        (['python', script, '--arbitrary'], sys.executable)]
            processes = [Mock(pid=900000+i, info={'exe':exe, 'cmdline':args}) for i, (args, exe) in enumerate(commands)]
            ours = Mock(pid=900010, info={'exe':sys.executable, 'cmdline':['python', '-u', '-B', script]})
            with patch.object(control.psutil, 'process_iter', return_value=processes+[ours]):
                self.assertEqual(control.owned_hosts(root), [ours])

    def test_confirmed_console_flash_uses_shared_guarded_backend(self):
        import desktop_support as desktop
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replies = iter(['1', '2', 'COM6', 'FLASH'])
            with contextlib.redirect_stdout(io.StringIO()), \
                    patch.object(control, 'flash_command', return_value=['synthetic-flasher']), \
                    patch.object(desktop, 'write_firmware', side_effect=control.SetupError('synthetic wrong identity')) as write, \
                    patch.object(control.subprocess, 'run') as run:
                with self.assertRaises(control.SetupError): control.flash(root, ask=lambda _:next(replies))
            write.assert_called_once_with(root, 'guition-p4', 'update', 'COM6', print)
            run.assert_not_called()

    def test_failed_noninteractive_diagnostics_and_setup_return_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(control, 'ROOT', Path(directory)), \
                    patch.object(control, 'status', side_effect=control.SetupError('synthetic invalid config')), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(control.main(['--check']), 1)
            with patch.object(control, 'ROOT', Path(directory)), \
                    patch.object(control, 'local_config', return_value={'providers':['codex']}), \
                    patch.object(control, 'setup_codex', side_effect=RuntimeError('synthetic failure')), \
                    patch('builtins.input', return_value=''), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(control.main(['--setup-codex']), 1)

    def test_firmware_hash_and_offsets_are_checked_before_flash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'firmware').mkdir()
            files = {}
            for name in ['factory.bin', 'application.bin']:
                content = ('synthetic-' + name).encode()
                (root / 'firmware' / name).write_bytes(content)
                files[name] = {'sha256': hashlib.sha256(content).hexdigest()}
            manifest = {'board': 'GUITION JC4880P433', 'chip': 'esp32p4', 'files': files}
            (root / 'firmware/manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(control.flash_command('install', 'COM6', root)[-2], '0x0')
            self.assertEqual(control.flash_command('update', 'COM6', root)[-2], '0x10000')
            (root / 'firmware/factory.bin').write_bytes(b'corrupt')
            with self.assertRaises(control.SetupError):
                control.flash_command('install', 'COM6', root)

    def test_cancelled_flash_never_stops_host_or_invokes_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replies = iter(['1', '1', 'COM6', 'NO'])
            with contextlib.redirect_stdout(io.StringIO()), patch.object(control, 'flash_command', return_value=['flasher']), \
                    patch.object(control, 'stop_host') as stop, patch.object(control.subprocess, 'run') as run, \
                    patch.object(control.list_ports, 'comports', return_value=[]):
                control.flash(root, ask=lambda _: next(replies))
            stop.assert_not_called(); run.assert_not_called()

    def test_status_is_local_and_does_not_show_keys_or_make_api_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control.save_config(dict(control.host.DEFAULT_CONFIG, board='guition-p4', zai_key='fixture-status-key'), root)
            output = io.StringIO()
            with contextlib.redirect_stdout(output), patch.object(control, 'owned_hosts', return_value=[]), \
                    patch.object(control.list_ports, 'comports', return_value=[]), \
                    patch.object(control.host.TokenReporter, 'poll', return_value={'sources': 0}), \
                    patch.object(control.host.urllib.request, 'urlopen') as network:
                control.status(root)
            network.assert_not_called()
            self.assertNotIn('fixture-status-key', output.getvalue())

    def test_status_uses_the_same_environment_key_precedence_as_the_host(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control.save_config(dict(control.host.DEFAULT_CONFIG, board='guition-p4',
                providers=['zcode'], zai_key='fixture-saved-key'), root)
            for environment, configured in (({}, True), ({'ZAI_API_KEY':''}, False),
                    ({'ZAI_API_KEY':'   '}, False), ({'ZAI_API_KEY':'fixture-env-key'}, True)):
                with self.subTest(environment_present=bool(environment), configured=configured):
                    output = io.StringIO()
                    with patch.dict(control.os.environ, environment, clear=True), \
                            contextlib.redirect_stdout(output), \
                            patch.object(control, 'owned_hosts', return_value=[]), \
                            patch.object(control.host, 'TokenReporter', return_value=Mock(poll=Mock(return_value={'sources':0}))), \
                            patch.object(control.host.urllib.request, 'urlopen') as network:
                        control.status(root)
                    network.assert_not_called()
                    self.assertIn('ZCode quota key: ' + ('configured' if configured else 'optional, not configured'), output.getvalue())
                    self.assertNotIn('fixture-saved-key', output.getvalue())
                    self.assertNotIn('fixture-env-key', output.getvalue())


if __name__ == '__main__':
    unittest.main()
