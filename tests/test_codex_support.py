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
import codex_support as support
import aim_control as control
import aim_host as host
from token_activity import TokenReporter


class RetainedBuffer(io.BytesIO):
    def close(self): pass


class CodexOnboardingTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows executable resolution')
    def test_posix_npm_shim_does_not_hide_native_windows_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'codex').write_text('#!/bin/sh\nexit 1\n')
            native=root/'native'; native.mkdir(); (native/'codex.exe').touch()
            with patch.dict(os.environ, {'PATH': str(root), 'CODEX_INSTALL_DIR': str(native)}):
                self.assertEqual(support.codex_command(), [str(native/'codex.exe')])

    @unittest.skipUnless(os.name == 'nt', 'Windows npm wrapper resolution')
    def test_extensionless_npm_shim_does_not_hide_working_cmd_wrapper(self):
        from host_security import path_executable
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'codex').write_text('#!/bin/sh\nexit 1\n')
            shim=root/'codex.cmd'; shim.touch()
            with patch.dict(os.environ, {'PATH': str(root)}):
                self.assertEqual(path_executable('codex'), str(shim))

    def test_existing_logged_in_client_is_reused_without_install_or_login(self):
        with patch.object(support,'codex_command',return_value=['official-cli']), \
                patch.object(support.subprocess,'run',return_value=Mock(returncode=0)) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(support.setup_codex(lambda _: self.fail('No prompt expected')))
        self.assertEqual(run.call_args.args[0],['official-cli','login','status'])
        self.assertEqual(run.call_args.kwargs['stdout'],support.subprocess.DEVNULL)

    def test_missing_client_install_then_official_sign_in_without_accepting_a_key(self):
        replies=iter(['y','y']); output=io.StringIO()
        with patch.object(support,'codex_command',side_effect=[None,['official-cli']]), \
                patch.object(support.subprocess,'run',side_effect=[Mock(returncode=0),Mock(returncode=1),Mock(returncode=0)]) as run, \
                contextlib.redirect_stdout(output):
            self.assertTrue(support.setup_codex(lambda _:next(replies)))
        commands=[call.args[0] for call in run.call_args_list]
        self.assertIn('https://chatgpt.com/codex/install.', ' '.join(commands[0]))
        self.assertEqual(commands[1:], [['official-cli','login','status'],['official-cli','login']])
        self.assertNotIn('--with-api-key',' '.join(' '.join(c) for c in commands))

    def test_declining_install_does_not_invoke_any_process(self):
        with patch.object(support,'codex_command',return_value=None), patch.object(support.subprocess,'run') as run, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(support.setup_codex(lambda _: 'n'))
        run.assert_not_called()

    def test_enter_does_not_accept_install_or_sign_in(self):
        with patch.object(support, 'codex_command', return_value=None), \
                patch.object(support.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(support.setup_codex(lambda _: ''))
        run.assert_not_called()
        with patch.object(support, 'codex_command', return_value=['official-cli']), \
                patch.object(support.subprocess, 'run', return_value=Mock(returncode=1)) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(support.setup_codex(lambda _: ''))
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ['official-cli', 'login', 'status'])

    def test_unselected_codex_is_not_prepared_and_existing_key_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); control.save_config(dict(host.DEFAULT_CONFIG, board='guition-p4',providers=['gemini'],zai_key='fixture-key'),root)
            with patch.object(control,'setup_codex') as prepare, patch.object(control.list_ports,'comports',return_value=[]), \
                    contextlib.redirect_stdout(io.StringIO()):
                control.configure(root,ask=lambda _: '',read_secret=lambda _: self.fail('Unselected key prompt'))
            prepare.assert_not_called()
            self.assertEqual(control.local_config(root)['providers'],['gemini'])
            self.assertEqual(control.local_config(root)['zai_key'],'fixture-key')

    def test_codex_home_is_used_for_default_counter_path_without_changing_explicit_test_home(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ,{'CODEX_HOME':directory}):
                self.assertEqual(support.codex_home(),Path(directory))
                self.assertEqual(TokenReporter(providers=['codex']).paths['codex'],Path(directory)/'state_5.sqlite')
                self.assertEqual(TokenReporter(home=Path('fixture'),providers=['codex']).paths['codex'],Path('fixture/.codex/state_5.sqlite'))

    def test_read_only_rpc_has_only_initialization_and_account_quota_methods(self):
        result={'rateLimits':{'limitId':'codex','primary':{'usedPercent':25,'windowDurationMins':300,'resetsAt':2000000000}}}
        incoming=[{'id':1,'result':{}},{'method':'account/updated','params':{'private':'not exported'}},{'id':2,'result':result}]
        process=Mock(pid=123456); process.stdin=RetainedBuffer(); process.stdout=RetainedBuffer(b''.join(json.dumps(v).encode()+b'\n' for v in incoming))
        process.poll.return_value=None
        with patch.object(support.subprocess,'Popen',return_value=process), patch.object(support.psutil,'Process',return_value=Mock(children=Mock(return_value=[]))):
            self.assertEqual(support.read_rate_limits(['official-cli']),result)
        methods=[json.loads(line)['method'] for line in process.stdin.getvalue().splitlines()]
        self.assertEqual(methods,['initialize','initialized','account/rateLimits/read'])
        process.terminate.assert_called_once()

    def test_custom_install_directory_is_discovered_without_shell_interpolation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); binary=root/('codex.exe' if os.name=='nt' else 'codex'); binary.touch()
            with patch.dict(os.environ,{'CODEX_INSTALL_DIR':directory}), patch.object(support,'path_executable',return_value=None):
                self.assertEqual(support.codex_command(),[str(binary)])

    def test_npm_wrapper_is_resolved_to_node_and_known_script_not_a_shell_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); shim=root/'codex.cmd';shim.touch()
            script=root/'node_modules/@openai/codex/bin/codex.js';script.parent.mkdir(parents=True);script.touch()
            with patch.object(support,'path_executable',side_effect=lambda name: str(shim) if name=='codex' else 'node-fixture' if name=='node' else None):
                self.assertEqual(support.codex_command(),['node-fixture',str(script)])

    def test_error_reply_stops_the_owned_child_tree_and_does_not_return_server_details(self):
        incoming=[{'id':1,'result':{}},{'id':2,'error':{'message':'private authentication detail'}}]
        process=Mock(pid=123456);process.stdin=RetainedBuffer();process.stdout=RetainedBuffer(b''.join(json.dumps(v).encode()+b'\n' for v in incoming));process.poll.return_value=None
        child=Mock()
        with patch.object(support.subprocess,'Popen',return_value=process), \
                patch.object(support.psutil,'Process',return_value=Mock(children=Mock(return_value=[child]))), \
                patch.object(support.psutil,'wait_procs',return_value=([child],[])):
            with self.assertRaises(RuntimeError) as caught: support.read_rate_limits(['node-fixture','codex.js'])
        self.assertNotIn('private authentication detail',str(caught.exception))
        child.terminate.assert_called_once();process.terminate.assert_called_once()

    def test_cli_quota_mapping_prefers_codex_bucket_and_keeps_context_out_of_plan_usage(self):
        result={'rateLimits':{'primary':{'usedPercent':99}},'rateLimitsByLimitId':{'codex':{
            'limitId':'codex','primary':{'usedPercent':12,'windowDurationMins':300,'resetsAt':2000000000},
            'secondary':{'usedPercent':25,'windowDurationMins':10080,'resetsAt':2000100000}}}}
        with patch.object(host,'codex_command',return_value=['official-cli']), patch.object(host,'read_rate_limits',return_value=result), \
                patch.object(host.urllib.request,'urlopen') as legacy:
            rows,notice=host.fetch_codex()
        self.assertIsNone(notice); self.assertEqual(rows[0]['usedPercent'],12); self.assertEqual(rows[1]['title'],'Week')
        legacy.assert_not_called()

    def test_cli_error_text_is_not_exposed_and_invalid_percent_is_not_clamped_into_quota(self):
        for result in [RuntimeError('private server detail'), {'rateLimits':{'primary':{'usedPercent':float('nan')}}}]:
            with patch.object(host,'codex_command',return_value=['official-cli']), \
                    patch.object(host,'read_rate_limits',side_effect=result if isinstance(result,Exception) else None,
                                 return_value=result if not isinstance(result,Exception) else None):
                rows,notice=host.fetch_codex()
            self.assertIsNone(rows); self.assertNotIn('private server detail',notice)

    def test_over_quota_codex_percentage_reports_zero_remaining_without_setup_error(self):
        result = {'rateLimits':{'primary':{'usedPercent':200,'windowDurationMins':300}}}
        with patch.object(host, 'codex_command', return_value=['official-cli']), \
                patch.object(host, 'read_rate_limits', return_value=result):
            rows, notice = host.fetch_codex()
        self.assertIsNone(notice)
        self.assertEqual(rows[0]['usedPercent'], 100)
        data = json.loads(host.frame_payload('codex', 0, rows))
        self.assertEqual(data['data'][0]['usage']['rows'][0]['usedPercent'], 0)


if __name__ == '__main__': unittest.main()
