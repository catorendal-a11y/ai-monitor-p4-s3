"""Synthetic lifecycle events; no clients, model turns or personal files."""
import base64
import json
import io
from pathlib import Path
import sys
import tempfile
import unittest
import os
import subprocess
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import live_events as live
import provider_setup as setup
import aim_events
from telemetry_bridge import write_record


class LiveEventTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.activity=self.root/'tools/activity'
        for provider in ('claude','codex'):
            write_record(self.activity/(provider+'-session-link.json'),dict(enabled=True,generation=17))

    def event(self,event,**fields):
        return dict(session_id='private-session-fixture',hook_event_name=event,
                    prompt='private prompt',tool_input={'command':'private command'},**fields)

    def test_codex_and_claude_normalization_never_retains_content(self):
        for provider in ('codex','claude'):
            live.lifecycle_event(provider,self.event('PermissionRequest'),self.activity,17,100)
        rows=live.live_agents(self.activity,['codex','claude'],101)
        self.assertEqual(len(rows),2);self.assertTrue(all(row['state']=='WAITING' for row in rows))
        for path in (self.activity/'live').rglob('*.json'):
            self.assertNotIn('private',path.name+path.read_text())
            self.assertEqual(set(json.loads(path.read_text())),{'schema','state','received_at','generation'})
        self.assertEqual(live.live_agents(self.activity,['zcode'],101),[])
        self.assertEqual(live.live_agents(self.activity,['codex'],130),[])

    def test_only_explicit_tools_are_classified_without_reading_arguments(self):
        for provider,tool,expected in (('codex','apply_patch','EDITING'),('codex','Bash','UNKNOWN'),
                                      ('claude','Edit','EDITING'),('claude','WebSearch','SEARCHING')):
            live.lifecycle_event(provider,self.event('PreToolUse',tool_name=tool),self.activity,17,100)
            self.assertEqual(live.live_agents(self.activity,[provider],101)[0]['state'],expected)

    def test_subagent_identity_does_not_replace_parent_and_closed_session_disappears(self):
        live.lifecycle_event('codex',self.event('UserPromptSubmit'),self.activity,17,100)
        live.lifecycle_event('codex',self.event('SubagentStart',agent_id='child'),self.activity,17,101)
        self.assertEqual(len(live.live_agents(self.activity,['codex'],102)),2)
        live.lifecycle_event('codex',self.event('SubagentStop',agent_id='child'),self.activity,17,103)
        self.assertEqual({row['state'] for row in live.live_agents(self.activity,['codex'],104)}, {'UNKNOWN','DONE'})
        live.lifecycle_event('codex',self.event('SessionEnd'),self.activity,17,105)
        self.assertEqual([row['state'] for row in live.live_agents(self.activity,['codex'],106)],['DONE'])

    def test_disabled_generation_mismatch_and_unknown_events_do_not_publish(self):
        live.lifecycle_event('codex',self.event('UserPromptSubmit'),self.activity,16,100)
        live.lifecycle_event('codex',self.event('NotAnEvent'),self.activity,17,100)
        self.assertFalse((self.activity/'live').exists())
        live.lifecycle_event('codex',self.event('Stop'),self.activity,17,100)
        write_record(self.activity/'codex-session-link.json',dict(enabled=False,generation=18))
        self.assertEqual(live.live_agents(self.activity,['codex'],101),[])

    def test_codex_receiver_requires_selected_provider_and_emits_no_decision(self):
        write_record(self.root/'tools/aim_host.json',dict(providers=['claude']))
        payload=json.dumps(self.event('PermissionRequest')).encode()
        with patch.object(aim_events.sys,'stdin',Mock(buffer=io.BytesIO(payload))):
            self.assertEqual(aim_events.receive(self.root,'codex'),0)
        self.assertFalse((self.activity/'live').exists())
        write_record(self.root/'tools/aim_host.json',dict(providers=['codex']))
        output=io.StringIO()
        with patch.object(aim_events.sys,'stdin',Mock(buffer=io.BytesIO(payload))),patch.object(aim_events.sys,'stdout',output):
            self.assertEqual(aim_events.receive(self.root,'codex'),0)
        self.assertEqual(output.getvalue(),'')
        self.assertEqual(live.live_agents(self.activity,['codex'])[0]['state'],'WAITING')

    def test_duplicate_events_are_bounded_and_waiting_takes_priority(self):
        for i in range(12):
            live.lifecycle_event('codex',dict(session_id=str(i),hook_event_name='Stop'),self.activity,17,100+i)
        live.lifecycle_event('claude',self.event('PermissionRequest'),self.activity,17,99)
        rows=live.live_agents(self.activity,['codex','claude'],112)
        self.assertEqual(len(rows),8);self.assertEqual(rows[0]['state'],'WAITING')

    def test_codex_setup_preserves_other_hooks_and_config_then_removes_only_owned_entries(self):
        home=self.root/'home';folder=home/'.codex';folder.mkdir(parents=True)
        config=folder/'config.toml';config.write_text('model = "fixture"\n')
        settings=folder/'hooks.json'
        original=dict(description='fixture',hooks={'Stop':[{'hooks':[{'type':'command','command':'fixture custom'}]}]})
        write_record(settings,original)
        with patch('provider_setup.claude_command',return_value='fixture observer'):
            self.assertIn('/hooks',setup.codex_session_link(self.root,home=home))
            first=settings.read_bytes()
            setup.codex_session_link(self.root,home=home)
            self.assertEqual(settings.read_bytes(),first)
            setup.codex_session_link(self.root,home=home,remove=True)
        self.assertEqual(json.loads(settings.read_text()),original)
        self.assertEqual(config.read_text(),'model = "fixture"\n')
        self.assertFalse(live.marker(self.activity,'codex')['enabled'])
        self.assertTrue(list(folder.glob('hooks.ai-monitor-backup-*.json')))

    def test_codex_observer_wrapper_emits_only_neutral_json_not_context(self):
        command=setup.claude_command(self.root,'--codex-event')
        if sys.platform=='win32':
            expression=base64.b64decode(command.rsplit(' ',1)[1]).decode('utf-16le')
            self.assertIn("[Console]::Out.WriteLine('{}')",expression)
            self.assertIn('*> $null',expression)
            self.assertNotIn('permissionDecision',expression)

    @unittest.skipUnless(os.name=='nt','Windows observer executable wrapper')
    def test_actual_windows_codex_wrapper_suppresses_child_output_and_oversize_payload(self):
        from host_security import powershell_executable
        (self.root/'tools').mkdir(exist_ok=True)
        observed=self.root/'observed.txt'
        (self.root/'tools/aim_events.py').write_text('import sys\nfrom pathlib import Path\n'
            f'Path({str(observed)!r}).write_text("observed")\n'
            'print("fixture private output");print("fixture private error",file=sys.stderr);sys.exit(7)\n')
        command=setup.claude_command(self.root,'--codex-event')
        args=[powershell_executable(),'-NoProfile','-EncodedCommand',command.rsplit(' ',1)[1]]
        result=subprocess.run(args,input='{"fixture":true}',capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0);self.assertEqual(result.stdout.strip(),'{}');self.assertEqual(result.stderr,'')
        self.assertTrue(observed.exists());observed.unlink()
        result=subprocess.run(args,input='x'*100000,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.stdout.strip(),'{}');self.assertFalse(observed.exists())


if __name__=='__main__':unittest.main()
