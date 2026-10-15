"""Observer -> background sampler -> serial owner, using only synthetic data."""
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import aim_events
from aim_host import Panel
from telemetry_bridge import write_record
from token_activity import TokenReporter, TokenSampler


class AgentPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.activity = self.root / 'tools/activity'
        write_record(self.root / 'tools/aim_host.json', {'providers': ['codex']})
        write_record(self.activity / 'codex-session-link.json', {'enabled': True, 'generation': 17})

    def observe(self):
        payload = dict(session_id='synthetic-session', hook_event_name='PreToolUse',
                       tool_name='apply_patch', prompt='private-fixture',
                       tool_input={'command': 'private-fixture'})
        with patch('sys.stdin', SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode()))):
            self.assertEqual(aim_events.receive(self.root, 'codex'), 0)

    def sample(self, providers=('codex',)):
        # Numeric readers are replaced, while the real worker reads observer records.
        numeric = dict(cmd='token_activity', known=False, seen=False, sources=0, idleSeconds=0, delta=0)
        with patch.object(TokenReporter, 'poll', return_value=numeric):
            sampler = TokenSampler(providers=list(providers), activity_dir=self.activity, home=self.root)
            try:
                sampler.poll()
                with sampler.condition:
                    self.assertTrue(sampler.condition.wait_for(lambda: sampler.result is not None, timeout=2))
                return sampler.poll()
            finally:
                sampler.close()
                sampler.worker.join(timeout=2)
                self.assertFalse(sampler.worker.is_alive())

    def panel(self, message):
        panel = Panel.__new__(Panel)  # Never construct/open a serial port.
        panel.info = dict(liveProtocol=1, liveMetadata=2, livePermissions=False, bootId=17)
        panel.tokens_supported = True
        panel.sessions_supported = True
        panel.token_reporter = TokenReporter(providers=[], home=self.root)
        panel.token_reporter.poll = Mock(return_value=message)
        panel.send_line = Mock()
        def reply(kind, command):
            request = json.loads(panel.send_line.call_args.args[0])
            return dict(type=kind, schema=1, cmd=command, ok=True, bootId=17, epoch=2,
                        sequence=request.get('sequence', 0), permissions=False,
                        requestId=request.get('requestId', 0))
        panel.wait_for = Mock(side_effect=reply)
        return panel

    def commands(self, panel):
        return [json.loads(call.args[0]) for call in panel.send_line.call_args_list]

    def test_observation_reaches_live_transport_without_numeric_source_or_private_fields(self):
        self.observe()
        sample = self.sample()
        self.assertFalse(sample['known'])  # Agent state does not depend on token availability.
        panel = self.panel(sample)
        panel.report_tokens()
        commands = self.commands(panel)
        self.assertEqual([c['cmd'] for c in commands],
                         ['token_activity', 'session_activity', 'live_open', 'live_state'])
        self.assertNotIn('live_agents', commands[0])
        self.assertEqual(commands[-1]['agents'][0]['state'], 'EDITING')
        self.assertNotIn('private-fixture', json.dumps(commands))
        self.assertNotIn('synthetic-session', json.dumps(commands))

    def test_disabled_or_unselected_observer_cannot_create_live_rows(self):
        self.observe()
        self.assertEqual(self.sample(providers=('zcode',))['live_agents'], [])
        write_record(self.activity / 'codex-session-link.json', {'enabled': False, 'generation': 18})
        self.assertEqual(self.sample()['live_agents'], [])

    def test_stale_worker_sample_sends_empty_replacement(self):
        self.observe()
        sample = self.sample()
        sample['live_sampled_at'] -= 11
        panel = self.panel(sample)
        panel.report_tokens()
        self.assertEqual(self.commands(panel)[-1]['agents'], [])

    def test_live_timeout_preserves_numeric_delivery_and_does_not_blindly_replay(self):
        self.observe()
        panel = self.panel(self.sample())
        panel.wait_for.side_effect = TimeoutError('synthetic transport timeout')
        panel.report_tokens()
        self.assertIsNone(panel.live_client)
        panel.send_line.reset_mock()
        panel.report_tokens()
        self.assertEqual([c['cmd'] for c in self.commands(panel)], ['token_activity', 'session_activity'])

    def test_old_firmware_receives_only_compatible_commands(self):
        self.observe()
        panel = self.panel(self.sample())
        panel.info = {}
        panel.report_tokens()
        self.assertEqual([c['cmd'] for c in self.commands(panel)], ['token_activity', 'session_activity'])
        panel.wait_for.assert_not_called()


if __name__ == '__main__':
    unittest.main()
