import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import aim_control as control
import aim_host as host
from provider_catalog import selected_providers
from token_activity import TokenReporter
from telemetry_bridge import ingest, read_counters, claude_statusline, read_claude_quota


class SelectionTests(unittest.TestCase):
    def test_deep_local_json_does_not_break_other_selected_activity_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = '['*20000 + '0' + ']'*20000
            claude = root/'.claude/projects/p/session.jsonl'; claude.parent.mkdir(parents=True)
            claude.write_text(nested+'\n', encoding='utf-8')
            gemini = root/'.gemini/tmp/p/chats/session-test.json'; gemini.parent.mkdir(parents=True)
            gemini.write_text(json.dumps({'messages':[{'type':'gemini','id':'synthetic','tokens':{'total':20}}]}))
            reporter = TokenReporter(home=root, providers=['claude','gemini'])
            self.assertTrue(reporter.poll()['sources'] & 8)
            gemini.write_text('{"messages":'+nested+'}', encoding='utf-8')
            reporter.last_poll = None
            self.assertEqual(reporter.poll()['delta'], 0)
    def test_first_run_has_no_ai_default_and_host_cannot_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'tools').mkdir()
            self.assertEqual(control.local_config(root)['providers'], [])
            with patch.object(host, 'CONFIG_PATH', root / 'tools/aim_host.json'):
                self.assertEqual(host.load_config()['providers'], [])
                with patch.object(control, 'stop_host') as stop:
                    with self.assertRaises(control.SetupError): control.start_host(root)
                    stop.assert_not_called()
            self.assertEqual(json.loads((root / 'tools/aim_host.json').read_text())['providers'], [])

    def test_explicit_selection_rejects_blank_duplicate_and_unknown_values(self):
        replies = iter(['', '3,3', '9', '3,4'])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(control.choose_providers([], lambda _: next(replies)), ['claude', 'gemini'])
        for value in [['unknown'], ['claude', 'claude'], 'claude', None]:
            with self.assertRaises(ValueError): selected_providers({'providers': value})

    def test_legacy_profiles_keep_previous_selection_but_new_empty_profile_does_not(self):
        self.assertEqual(selected_providers({'zai_key': 'fixture'}, legacy=True), ['codex','zcode'])
        self.assertEqual(selected_providers({'zai_key': 'fixture'}), [])
        self.assertEqual(selected_providers({'providers': [], 'zai_key': 'fixture'}, legacy=True), [])

    def test_claude_only_does_not_read_unselected_databases(self):
        with tempfile.TemporaryDirectory() as directory:
            reporter = TokenReporter(home=directory, providers=['claude'])
            with patch.object(reporter, 'read_counts') as database:
                self.assertFalse(reporter.poll()['known'])
                database.assert_not_called()

    def test_activity_only_provider_never_fetches_codex_or_zai_or_invents_quota(self):
        panel = Mock(); panel.retries = host.ProviderRetries(); panel.wait_for.return_value = {'type':'ack'}
        with patch.object(host, 'fetch_codex') as codex, patch.object(host, 'fetch_zcode') as zai:
            host.poll_cycle(dict(host.DEFAULT_CONFIG, board='guition-p4', providers=['gemini']), '', ['gemini'], 100, panel)
        codex.assert_not_called(); zai.assert_not_called()
        data = json.loads(panel.send_frame.call_args.args[0])['data'][0]
        self.assertTrue(data['informational']); self.assertNotIn('usage', data)
        self.assertTrue(panel.last_poll_success)

    def test_local_claude_and_gemini_tokens_baseline_deduplicate_and_follow_new_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); claude = root / '.claude/projects/project/session.jsonl'
            claude.parent.mkdir(parents=True)
            def event(identifier, output):
                return json.dumps({'type':'assistant','message':{'id':identifier,'content':'private text never retained',
                    'usage':{'input_tokens':10,'output_tokens':output,'cache_read_input_tokens':100}}})+'\n'
            claude.write_text(event('old',5))
            gemini = root / '.gemini/tmp/project/chats/session-test.json'; gemini.parent.mkdir(parents=True)
            gemini.write_text(json.dumps({'messages':[{'type':'gemini','id':'g1','content':'private', 'tokens':{'total':50}}]}))
            clock = {'now':0}
            reporter = TokenReporter(home=root, providers=['claude','gemini'], clock=lambda:clock['now'])
            self.assertEqual(reporter.poll()['sources'],12)
            with claude.open('a') as stream: stream.write(event('old',5)+event('new',20))
            clock['now']=2
            used=reporter.poll(); self.assertEqual(used['delta'],130); self.assertTrue(used['seen'])
            self.assertNotIn('private', repr(reporter.local.files))
            clock['now']=4; self.assertEqual(reporter.poll()['delta'],0)
            gemini.write_text(json.dumps({'messages':[{'type':'gemini','id':'g1','tokens':{'total':50}},
                {'type':'gemini','id':'g2','tokens':{'total':70}}]}))
            clock['now']=6; self.assertEqual(reporter.poll()['delta'],70)

    def test_partial_jsonl_record_is_retried_not_lost(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); file=root/'.claude/projects/p/s.jsonl'; file.parent.mkdir(parents=True)
            first={'type':'assistant','message':{'id':'old','usage':{'input_tokens':1}}}
            second={'type':'assistant','message':{'id':'new','usage':{'input_tokens':3}}}
            file.write_text(json.dumps(first)+'\n'+json.dumps(second)[:30])
            clock={'now':0}; reporter=TokenReporter(home=root,providers=['claude'],clock=lambda:clock['now'])
            self.assertEqual(reporter.poll()['delta'],0)
            with file.open('a') as stream: stream.write(json.dumps(second)[30:]+'\n')
            clock['now']=2; self.assertEqual(reporter.poll()['delta'],3)

    def test_bridge_persists_only_numeric_usage_and_hashed_session_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ingest('copilot', {'session_id':'private-session','total_tokens':20,'prompt':'private prompt','api_key':'fixture-key'}, root)
            contents=''.join(p.read_text() for p in root.rglob('*.json'))
            for value in ['private-session','private prompt','fixture-key']: self.assertNotIn(value, contents)
            reporter=TokenReporter(home=root,providers=['copilot'],activity_dir=root,clock=lambda:0)
            self.assertEqual(reporter.poll()['sources'],16)
            self.assertEqual(list(read_counters(root,'copilot').values()),[20])
            with self.assertRaises(ValueError): ingest('../escape',{'session_id':'s','total_tokens':2},root)

    def test_claude_quota_uses_rate_limits_not_context_occupancy_and_expires(self):
        with tempfile.TemporaryDirectory() as directory:
            payload={'context_window':{'used_percentage':99},'prompt':'private','rate_limits':{
                'five_hour':{'used_percentage':20,'resets_at':20000}}}
            with patch('telemetry_bridge.time.time', return_value=10000): claude_statusline(payload,directory)
            self.assertEqual(read_claude_quota(directory,10001)[0]['usedPercent'],20)
            self.assertIsNone(read_claude_quota(directory,10301))
            self.assertNotIn('private',(Path(directory)/'claude-quota.json').read_text())

    def test_claude_installation_preserves_existing_statusline(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); home=root/'home'; settings=home/'.claude/settings.json'; settings.parent.mkdir(parents=True)
            settings.write_text(json.dumps({'statusLine':{'type':'command','command':'original'}}))
            control.save_config(dict(host.DEFAULT_CONFIG, board='guition-p4',providers=['claude']),root)
            before=settings.read_bytes()
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(control.SetupError):
                control.integration_help(root,ask=lambda _: 'INSTALL',home=home)
            self.assertEqual(settings.read_bytes(),before)


if __name__ == '__main__': unittest.main()
