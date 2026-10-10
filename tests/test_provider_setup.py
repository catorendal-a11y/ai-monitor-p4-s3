import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from opencode_activity import read_counts, database_path
from provider_setup import claude_bridge, claude_command, readiness
from token_activity import TokenReporter


class ProviderSetupTests(unittest.TestCase):
    def test_memory_database_is_not_replaced_with_default_source(self):
        with patch.dict('os.environ', {'OPENCODE_DB': ':memory:'}):
            self.assertIsNone(read_counts(database_path()))
    def test_claude_link_is_idempotent_and_removal_preserves_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); settings = root / '.claude/settings.json'
            settings.parent.mkdir(); settings.write_text('{"theme":"dark"}')
            claude_bridge(root, home=root)
            linked = settings.read_bytes()
            backups = list(settings.parent.glob('*backup*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(json.loads(backups[0].read_text()), {'theme':'dark'})
            claude_bridge(root, home=root)
            self.assertEqual(settings.read_bytes(), linked)
            self.assertEqual(len(list(settings.parent.glob('*backup*'))), 1)
            claude_bridge(root, remove=True, home=root)
            self.assertEqual(json.loads(settings.read_text()), {'theme':'dark'})

    def test_custom_claude_statusline_is_never_replaced_or_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); settings = root / '.claude/settings.json'
            settings.parent.mkdir(); settings.write_text('{"statusLine":{"command":"custom"}}')
            before = settings.read_bytes()
            for remove in (False, True):
                with self.assertRaises(ValueError): claude_bridge(root, remove=remove, home=root)
                self.assertEqual(settings.read_bytes(), before)

    def test_frozen_gui_uses_console_helper_for_statusline(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(sys, 'frozen', True, create=True):
                with self.assertRaises(ValueError): claude_command(root)
                (root/'AI-Monitor-Console.exe').touch()
                command = claude_command(root)
                # Windows shell command is encoded; decode its explicit target.
                if '-EncodedCommand ' in command:
                    import base64
                    command = base64.b64decode(command.split('-EncodedCommand ')[1]).decode('utf-16le')
                self.assertIn('AI-Monitor-Console.exe', command)
                self.assertIn('--claude-statusline', command)

    def test_opencode_v2_numeric_only_readonly_and_fork_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder); path = home/'.local/share/opencode/opencode.db'
            path.parent.mkdir(parents=True)
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE session_v2(id TEXT,time_updated INTEGER,tokens_input INTEGER,tokens_output INTEGER,tokens_reasoning INTEGER,tokens_cache_read INTEGER,tokens_cache_write INTEGER)')
                db.execute("INSERT INTO session_v2 VALUES ('private-name',1,10,20,3,4,5)")
                db.execute('CREATE TABLE auth(secret TEXT)'); db.execute("INSERT INTO auth VALUES ('never-export')")
            raw = path.read_bytes(); counts = read_counts(path)
            self.assertEqual(list(counts.values()), [42]); self.assertNotIn('private-name', str(counts))
            self.assertEqual(path.read_bytes(), raw)
            reporter = TokenReporter(home=home, providers=['opencode'], clock=lambda:0)
            reporter.paths['opencode'] = path; reporter.poll_seconds = 0
            self.assertEqual(reporter.poll()['delta'], 0)
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('UPDATE session_v2 SET tokens_output=25')
                db.execute("INSERT INTO session_v2 VALUES ('imported',2,1000,1000,0,0,0)")
            self.assertEqual(reporter.poll()['delta'], 5)

    def test_opencode_v1_messages_ignore_text_and_invalid_token_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'test.db'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE message(id TEXT,time_updated INTEGER,data TEXT)')
                for identifier, role, amount in [('a','assistant',10),('b','user',999),('c','assistant',True)]:
                    db.execute('INSERT INTO message VALUES (?,1,?)', (identifier, json.dumps({'role':role,'text':'never-return-this',
                        'tokens':{'input':amount,'output':2,'reasoning':3,'cache':{'read':4,'write':5}}})))
            # SQL returns JSON boolean as an int; reject its type before extraction.
            self.assertEqual(list(read_counts(path).values()), [24])

    def test_opencode_rejects_views_and_unknown_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'test.db'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE VIEW session_v2 AS SELECT load_extension('untrusted')")
            self.assertIsNone(read_counts(path))

    def _readiness(self, config, sources, processes=None, status=None, cli=None, root=None, home=None, environment=None):
        """Synthetic readiness run: no real config, token sources, host or CLI are touched."""
        reporter = Mock(); reporter.poll.return_value = {'sources': sources}
        messages = []
        # Omit ZAI_API_KEY by default so a developer machine's real environment cannot change the result.
        with patch.dict('os.environ', environment or {}):
            if not environment: os.environ.pop('ZAI_API_KEY', None)
            with patch('aim_control.local_config', return_value=config), \
                 patch('aim_control.owned_hosts', return_value=processes or []), \
                 patch('host_status.read_status', return_value=status), \
                 patch('codex_support.codex_command', return_value=cli), \
                 patch('token_activity.TokenReporter', return_value=reporter), \
                 patch('subprocess.Popen') as spawn:
                readiness(root or Path('.'), messages.append, home=home)
        spawn.assert_not_called()
        return messages

    def test_readiness_reports_advanced_bridge_without_model_or_usb_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            config = {'providers':['cursor','opencode','zcode'],'zai_key':'synthetic-key'}
            messages = self._readiness(config, 128)
            self.assertIn('No bridge data received yet', messages[0])
            self.assertIn('--ingest cursor', messages[0])
            self.assertIn('readable', messages[1]); self.assertIn('Activity-only', messages[1])
            self.assertIn('not verified yet', messages[2])
            self.assertNotIn('synthetic-key', str(messages))

    def test_readiness_codex_states_separate_cli_signin_and_host_verification(self):
        config = {'providers':['codex'],'zai_key':''}
        for cli, processes, status, expected in [
            (None, [], None, 'Official CLI missing. Open Install / sign in Codex'),
            (['cli'], [], None, 'does not verify sign-in'),
            (['cli'], [Mock(pid=1)], None, 'has not reported Codex yet'),
            (['cli'], [Mock(pid=1)], {'providers':{'codex':'ready'}}, 'received account quota successfully'),
            (['cli'], [Mock(pid=1)], {'providers':{'codex':'unavailable'}}, 'could not read quota'),
            # The legacy file login can supply quota without the CLI; observed success is kept.
            (None, [Mock(pid=1)], {'providers':{'codex':'ready'}}, 'legacy file login'),
        ]:
            messages = self._readiness(config, 0, processes, status, cli)
            self.assertIn(expected, messages[0])
        failed = self._readiness(config, 0, [Mock(pid=1)], {'providers':{'codex':'unavailable'}}, ['cli'])
        self.assertIn('ChatGPT-backed login', failed[0])

    def test_readiness_distinguishes_configured_zcode_key_from_received_quota(self):
        config = {'providers':['zcode'],'zai_key':'synthetic-key'}
        for processes, status, expected in [
            ([], None, 'Quota is not verified yet'),
            ([Mock(pid=1)], {'providers':{}}, 'has not reported ZCode yet'),
            ([Mock(pid=1)], {'providers':{'zcode':'ready'}}, 'last received plan quota'),
            ([Mock(pid=1)], {'providers':{'zcode':'unavailable'}}, 'could not read quota'),
        ]:
            messages = self._readiness(config, 0, processes, status)
            self.assertIn(expected, messages[0]); self.assertNotIn('synthetic-key', str(messages))
        self.assertNotIn('verified', self._readiness(config, 0, [Mock(pid=1)], {'providers':{'zcode':'ready'}})[0])
        no_key = self._readiness({'providers':['zcode'],'zai_key':''}, 0)
        self.assertIn('save your own Z.AI coding-plan key', no_key[0])
        self.assertIn('encrypted login is not imported', no_key[0])

    def test_readiness_reports_rate_limiting_as_temporary(self):
        config = {'providers':['zcode'],'zai_key':'synthetic-key'}
        message = self._readiness(config, 0, [Mock(pid=1)], {'providers':{'zcode':'unavailable'}})[0]
        self.assertIn('automatic backoff', message); self.assertNotIn('rate-limited key', message)

    def test_readiness_accepts_zcode_key_from_environment_without_printing_it(self):
        messages = self._readiness({'providers':['zcode'],'zai_key':''}, 0,
                                   environment={'ZAI_API_KEY':'env-fixture-key'})
        self.assertIn('ZAI_API_KEY environment variable, not saved by the app', messages[0])
        self.assertNotIn('env-fixture-key', str(messages))

    def test_readiness_empty_environment_key_overrides_saved_key(self):
        messages = self._readiness({'providers':['zcode'],'zai_key':'synthetic-key'}, 0,
                                   environment={'ZAI_API_KEY':''})
        self.assertIn('empty ZAI_API_KEY variable overrides AI setup', messages[0])
        self.assertIn('uses no key', messages[0]); self.assertNotIn('synthetic-key', str(messages))

    def test_readiness_reports_claude_link_installation_state(self):
        config = {'providers':['claude'],'zai_key':''}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); home = root/'home'
            self.assertIn('not installed yet', self._readiness(config, 0, root=root, home=home)[0])
            claude_bridge(root, home=home)
            self.assertIn('Quota link installed', self._readiness(config, 0, root=root, home=home)[0])
            (home/'.claude/settings.json').write_text('{"statusLine":{"type":"command","command":"private-custom-command"}}')
            message = self._readiness(config, 0, root=root, home=home)[0]
            self.assertIn('preserved', message); self.assertNotIn('private-custom-command', message)

    def test_readiness_activity_only_and_reporting_bridge_never_invent_quota(self):
        messages = self._readiness({'providers':['copilot','gemini'],'zai_key':''}, 16 | 8)
        self.assertIn('Bridge token source readable', messages[0])
        self.assertIn('Account quota remains unavailable', messages[0])
        self.assertIn('Activity-only', messages[1]); self.assertIn('remaining account quota is unavailable', messages[1])
