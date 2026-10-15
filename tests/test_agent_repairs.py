"""Regression gates for ZCode opt-in, independent events and truthful USB health."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import aim_events
import live_events as live
import provider_setup as setup
from aim_host import Panel
from host_status import HostStatus, read_status
from telemetry_bridge import write_record


class AgentRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.activity = self.root / 'tools/activity'
        write_record(self.root / 'tools/aim_host.json', {'providers': ['zcode']})
        write_record(self.activity / 'zcode-session-link.json', {'enabled': True, 'generation': 17})

    def event(self, name, **extra):
        return dict(session_id='synthetic', hook_event_name=name, **extra)

    def test_zcode_observer_accepts_documented_states_and_discards_content(self):
        for event, extra, expected in [('UserPromptSubmit', {}, 'WORKING'),
                ('PreToolUse', {'tool_name':'Write'}, 'WRITING'),
                ('PermissionRequest', {}, 'WAITING'), ('PostToolUseFailure', {}, 'ERROR'),
                ('Stop', {}, 'COMPLETED')]:
            payload=self.event(event, prompt='fixture-private', tool_input={'command':'fixture-private'}, **extra)
            with patch('sys.stdin', SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode()))):
                aim_events.receive(self.root, 'zcode')
            rows=live.live_agents(self.activity, ['zcode'])
            self.assertEqual([r['state'] for r in rows], [expected])
        self.assertNotIn('fixture-private', ''.join(p.read_text() for p in (self.activity/'live').rglob('*.json')))

    def test_zcode_ignores_undocumented_child_events(self):
        live.lifecycle_event('zcode', self.event('UserPromptSubmit'), self.activity, 17, 100)
        live.lifecycle_event('zcode', self.event('SubagentStart', agent_id='child'), self.activity, 17, 101)
        self.assertEqual([r['state'] for r in live.live_agents(self.activity, ['zcode'], 102)], ['WORKING'])

    def test_interrupted_tool_freezes_elapsed_timer(self):
        for provider in ('claude','zcode'):
            write_record(self.activity/(provider+'-session-link.json'), {'enabled':True,'generation':17})
            live.lifecycle_event(provider,self.event('UserPromptSubmit'),self.activity,17,100)
            live.lifecycle_event(provider,self.event('PostToolUseFailure',is_interrupt=True),self.activity,17,110)
            row=live.live_agents(self.activity,[provider],120)[0]
            self.assertEqual((row['state'],row['elapsedSeconds']),('IDLE',10))

    def test_zcode_setup_preserves_existing_settings_and_removes_only_owned_hooks(self):
        file=self.root/'.zcode/cli/config.json'
        original={'fixture':'keep','hooks':{'enabled':True,'timeoutMs':9000,'events':{
            'Stop':[{'hooks':[{'type':'process','command':'fixture-custom','args':[]}]}]}}}
        write_record(file,original)
        with patch('provider_setup.event_process',return_value=['fixture-observer','--zcode-event']):
            setup.zcode_session_link(self.root,home=self.root)
            self.assertEqual(setup.zcode_session_state(self.root,home=self.root),'installed')
            first=file.read_bytes(); setup.zcode_session_link(self.root,home=self.root)
            self.assertEqual(first,file.read_bytes())
            setup.zcode_session_link(self.root,home=self.root,remove=True)
        self.assertEqual(json.loads(file.read_text()),original)
        self.assertFalse(live.marker(self.activity,'zcode')['enabled'])
        self.assertTrue(list(file.parent.glob('config.ai-monitor-backup-*.json')))

    def test_zcode_setup_does_not_enable_globally_disabled_custom_hooks(self):
        file=self.root/'.zcode/cli/config.json'
        write_record(file,{'hooks':{'enabled':False,'events':{}}})
        with patch('provider_setup.event_process',return_value=['fixture-observer']):
            setup.zcode_session_link(self.root,home=self.root)
            self.assertIn('disabled',setup.zcode_session_state(self.root,home=self.root))
        self.assertIs(json.loads(file.read_text())['hooks']['enabled'],False)

    def test_zcode_invalid_setup_is_atomic(self):
        file=self.root/'.zcode/cli/config.json'; write_record(file,{'hooks':{'events':{'Stop':'bad'}}})
        before=file.read_bytes()
        with self.assertRaises(ValueError): setup.zcode_session_link(self.root,home=self.root)
        self.assertEqual(before,file.read_bytes())

    def test_codex_marker_cannot_establish_installed_hooks(self):
        write_record(self.activity/'codex-session-link.json',{'enabled':True,'generation':17})
        self.assertEqual(setup.codex_session_state(self.root,home=self.root),'not linked')

    def test_codex_upgrade_migrates_only_exact_legacy_observer_and_preserves_custom_hooks(self):
        # Simulate an older source setup with a Python interpreter outside the release.
        with patch.object(sys,'executable',str(self.root/'old-python/python.exe')):
            old=setup.claude_command(self.root,'--codex-event')
        custom={'type':'command','command':'fixture-custom','timeout':2}
        old_hook={'type':'command','command':old,'timeout':2}
        file=self.root/'.codex/hooks.json'
        write_record(file,{'hooks':{event:[{'hooks':[old_hook,custom]}] for event in setup.CODEX_EVENTS}})
        setup.codex_session_link(self.root,home=self.root)
        document=json.loads(file.read_text())
        current={'type':'command','command':setup.claude_command(self.root,'--codex-event'),'timeout':2}
        for entries in document['hooks'].values():
            self.assertEqual(entries,[{'hooks':[current,custom]}])

    def test_independent_sampler_does_not_need_numeric_reader(self):
        live.lifecycle_event('zcode',self.event('UserPromptSubmit'),self.activity,17)
        sampler=live.LiveSampler(self.activity,['zcode'])
        try:
            sampler.poll()
            with sampler.condition:
                self.assertTrue(sampler.condition.wait_for(lambda:sampler.result is not None,timeout=2))
            rows=sampler.poll()['live_agents']; self.assertEqual(rows[0]['state'],'WORKING')
            sampler.configure(['codex'])
            self.assertIsNone(sampler.poll())  # A configuration change discards old-provider results.
        finally:
            sampler.close();sampler.worker.join(timeout=2)
            self.assertFalse(sampler.worker.is_alive())

    def test_usb_live_delivery_runs_without_numeric_sample_and_exports_ack(self):
        panel=Panel.__new__(Panel); panel.tokens_supported=False
        panel.info={'liveProtocol':1,'livePermissions':False,'liveMetadata':2,'bootId':17}
        panel.health=HostStatus(self.root/'tools')
        panel.live_sampler=Mock(); panel.live_sampler.poll.return_value={
            'live_agents':[{'provider':'zcode','id':'opaque','state':'WORKING'}],
            'live_sampled_at':time.monotonic()}
        with patch('usb_live.UsbLiveClient') as client:
            panel.report_tokens()
            client.return_value.send.assert_called_once()
        self.assertEqual(panel.health.data['live']['state'],'acknowledged')
        self.assertEqual(panel.health.data['live']['agent_count'],1)

    def test_failed_live_delivery_is_visible_without_claiming_ack(self):
        panel=Panel.__new__(Panel); panel.tokens_supported=False
        panel.info={'liveProtocol':1,'livePermissions':False,'bootId':17}
        panel.health=HostStatus(self.root/'tools'); panel.live_sampler=Mock()
        panel.live_sampler.poll.return_value={'live_agents':[],'live_sampled_at':time.monotonic()}
        with patch('usb_live.UsbLiveClient') as client:
            client.return_value.send.side_effect=TimeoutError('fixture')
            panel.report_tokens()
        self.assertEqual(panel.health.data['live']['state'],'error')

    def test_health_rejects_forged_live_counts_and_fields(self):
        health=HostStatus(self.root/'tools')
        health.data['live']={'state':'acknowledged','updated_at':time.time(),'agent_count':9}
        health.update('connected','COM9999')
        self.assertIsNone(read_status(self.root,{os.getpid()}))

    def test_console_link_is_explicit_and_requires_selected_provider(self):
        import aim_control as control
        with patch.object(control,'ROOT',self.root),patch.object(control,'local_config',return_value={'providers':['zcode']}), \
             patch('provider_setup.zcode_session_link',return_value='fixture linked') as link,patch('builtins.print'):
            self.assertEqual(control.main(['--link-events','zcode']),0)
            link.assert_called_once_with(self.root,remove=False)
        with patch.object(control,'ROOT',self.root),patch.object(control,'local_config',return_value={'providers':[]}), \
             patch('provider_setup.zcode_session_link') as link,patch('builtins.print'):
            self.assertEqual(control.main(['--link-events','zcode']),1)
            link.assert_not_called()


if __name__=='__main__':unittest.main()
