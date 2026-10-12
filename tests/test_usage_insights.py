"""Synthetic numeric history/session tests; no personal data, cloud or USB."""
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import aim_control as control
import provider_setup as setup
import session_activity as sessions
import usage_history as history


class SessionTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Windows command wrapper')
    def test_windows_observer_suppresses_output_failure_and_oversize_input(self):
        from host_security import powershell_executable
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); (root/'tools').mkdir()
            observed=root/'observed.txt'
            (root/'tools/aim_control.py').write_text(
                'import sys\nfrom pathlib import Path\n'
                f'Path({str(observed)!r}).write_text(str(len(sys.stdin.read())))\n'
                'print("fixture output"); print("fixture error",file=sys.stderr); sys.exit(7)\n')
            command=setup.claude_command(root,'--claude-event')
            encoded=command.rsplit(' ',1)[1]
            arguments=[powershell_executable(),'-NoProfile','-EncodedCommand',encoded]
            result=subprocess.run(arguments,input='{"fixture":"safe"}',text=True,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0)
            self.assertEqual(result.stdout,''); self.assertEqual(result.stderr,'')
            self.assertTrue(observed.exists()); observed.unlink()
            result=subprocess.run(arguments,input='x'*100000,text=True,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0)
            self.assertEqual(result.stdout,''); self.assertEqual(result.stderr,'')
            self.assertFalse(observed.exists())

    def test_documented_events_are_state_only_deduplicated_and_expire(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            payload={'session_id':'fixture-private-session','prompt':'fixture private text',
                     'tool_input':{'command':'never execute this'},'hook_event_name':'UserPromptSubmit'}
            sessions.claude_event(payload,root,now=1000)
            sessions.claude_event(payload,root,now=1001)
            self.assertEqual(sessions.aggregate(sessions.summary(root,['claude'],now=1002))['running'],1)
            files=list(root.rglob('*.json')); self.assertEqual(len(files),1)
            self.assertEqual(set(json.loads(files[0].read_text())),{'state','received_at'})
            self.assertNotIn('fixture',files[0].name+files[0].read_text())
            sessions.claude_event(dict(payload,hook_event_name='PermissionRequest'),root,now=1003)
            self.assertEqual(sessions.aggregate(sessions.summary(root,['claude'],now=1004))['waiting'],1)
            sessions.claude_event(dict(payload,hook_event_name='Stop'),root,now=1005)
            self.assertEqual(sessions.aggregate(sessions.summary(root,['claude'],now=1006))['completed'],1)
            self.assertFalse(sessions.aggregate(sessions.summary(root,['claude'],now=1036))['known'])
            self.assertEqual(sessions.summary(root,['codex'],now=1006)['providers'],[])
            self.assertEqual(sessions.summary(root,['claude'],now=999)['providers'],[])

    def test_invalid_records_and_notifications_cannot_control_anything(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            for kind in ('auth_success','idle_prompt','unknown'):
                sessions.claude_event({'session_id':'fixture','hook_event_name':'Notification','notification_type':kind},root)
            self.assertFalse(list(root.rglob('*.json')))
            for state in ('execute',None,False,[],{},-1):
                with self.assertRaises((ValueError,TypeError)):
                    sessions.ingest_event('claude',{'session_id':'fixture','state':state},root)
            sessions.ingest_event('claude',{'session_id':'fixture','state':'running'},root)
            path=next(root.rglob('*.json'))
            for invalid in ({'state':'running','received_at':True},
                            {'state':{},'received_at':1000},
                            {'state':'waiting','received_at':1000,'command':'fixture'},
                            {'state':'running','received_at':float('nan')}):
                path.write_text(json.dumps(invalid))
                self.assertEqual(sessions.summary(root,['claude'],now=1001)['providers'],[])

    def test_session_count_is_bounded(self):
        with tempfile.TemporaryDirectory() as name:
            for index in range(70):
                sessions.ingest_event('claude',{'session_id':f'fixture-{index}','state':'waiting'},name,now=1000)
            self.assertEqual(len(list(Path(name).rglob('*.json'))),64)
            self.assertEqual(sessions.aggregate(sessions.summary(name,['claude'],now=1001))['waiting'],64)

    def test_hook_link_preserves_custom_hooks_and_removal_is_scoped(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); path=root/'.claude/settings.json'; path.parent.mkdir()
            original={'theme':'fixture','statusLine':{'type':'command','command':'fixture-custom'},
                      'hooks':{'Stop':[{'matcher':'','hooks':[{'type':'command','command':'fixture-existing'}]}]}}
            path.write_text(json.dumps(original))
            setup.claude_session_link(root,home=root)
            linked=json.loads(path.read_text())
            self.assertEqual(linked['statusLine'],original['statusLine'])
            self.assertEqual(linked['hooks']['Stop'][0],original['hooks']['Stop'][0])
            for event in setup.CLAUDE_EVENTS:
                hook=linked['hooks'][event][-1]['hooks'][0]
                self.assertEqual(set(hook),{'type','command','timeout'})
                self.assertEqual(hook['timeout'],2)
            before=path.read_bytes()
            setup.claude_session_link(root,home=root)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(len(list(path.parent.glob('*backup*'))),1)
            setup.claude_session_link(root,remove=True,home=root)
            self.assertEqual(json.loads(path.read_text()),original)
            setup.claude_session_link(root,remove=True,home=root)
            self.assertEqual(json.loads(path.read_text()),original)

    def test_claude_hook_cli_is_silent_and_nonblocking_even_on_invalid_input(self):
        with tempfile.TemporaryDirectory() as name, patch.object(control,'ROOT',Path(name)):
            control.save_config(dict(control.host.DEFAULT_CONFIG,board='guition-p4',providers=['claude']),Path(name))
            setup.claude_session_link(Path(name),home=Path(name))
            for raw in (b'{',b'{"hook_event_name":"PermissionRequest","session_id":"fixture","tool_input":{"command":"fixture"}}',b'x'*65537):
                stdin=io.TextIOWrapper(io.BytesIO(raw))
                stdout=io.StringIO()
                with patch.object(sys,'stdin',stdin),patch.object(sys,'stdout',stdout):
                    self.assertEqual(control.main(['--claude-event']),0)
                self.assertEqual(stdout.getvalue(),'')

    def test_unlink_invalidates_existing_and_inflight_events_even_after_relink(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); activity=root/'tools/activity'
            setup.claude_session_link(root,home=root)
            marker=sessions.link_marker(activity)
            payload={'session_id':'fixture','hook_event_name':'PermissionRequest'}
            sessions.claude_event(payload,activity,generation=marker['generation'])
            self.assertEqual(sessions.aggregate(sessions.summary(activity,['claude']))['waiting'],1)
            setup.claude_session_link(root,remove=True,home=root)
            sessions.claude_event(payload,activity,generation=marker['generation'])
            self.assertFalse(sessions.aggregate(sessions.summary(activity,['claude']))['known'])
            setup.claude_session_link(root,home=root)
            self.assertFalse(sessions.aggregate(sessions.summary(activity,['claude']))['known'])
            sessions.claude_event(payload,activity,generation=sessions.link_marker(activity)['generation'])
            self.assertEqual(sessions.aggregate(sessions.summary(activity,['claude']))['waiting'],1)
            new=sessions.link_marker(activity)
            sessions.claude_event(dict(payload,hook_event_name='UserPromptSubmit'),activity,generation=new['generation'])
            sessions.claude_event(payload,activity,generation=marker['generation'])
            self.assertEqual(sessions.aggregate(sessions.summary(activity,['claude']))['running'],1)

    @unittest.skipUnless(os.name=='nt','Windows file sharing semantics')
    def test_atomic_event_record_retries_windows_sharing_failure_without_deleting_destination(self):
        from telemetry_bridge import write_record
        import telemetry_bridge
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'fixture.json'; write_record(path,{'state':'idle'})
            actual=telemetry_bridge.os.replace; calls=[]
            def transient(source,target):
                calls.append(target)
                if len(calls)==1:
                    error=PermissionError('fixture sharing lock'); error.winerror=32; raise error
                return actual(source,target)
            with patch.object(telemetry_bridge.os,'replace',side_effect=transient),patch.object(telemetry_bridge.time,'sleep'):
                write_record(path,{'state':'running'})
            self.assertEqual(len(calls),2); self.assertEqual(json.loads(path.read_text()),{'state':'running'})


class HistoryTests(unittest.TestCase):
    def test_reset_can_precede_projected_exhaustion(self):
        with tempfile.TemporaryDirectory() as name:
            now=1800000000; minute=now//60
            self.fixture(name,[('codex',minute-i,300,'model',10-i,now+30,1) for i in (0,1,2)])
            forecast=history.read_history(name,['codex'],now=now+1)['forecasts'][0]
            self.assertIsNone(forecast['estimated_hours_to_limit'])

    def test_history_is_opt_in_and_collection_is_numeric_only(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); now=1800000000
            recorder=history.HistoryRecorder(root,clock=lambda:now)
            recorder.record_tokens({'codex':12}); recorder.close()
            self.assertFalse((root/'history.db').exists())
            recorder=history.HistoryRecorder(root,True,clock=lambda:now)
            recorder.record_tokens({'codex':12,'zcode':7,'claude':True,'unknown':999})
            recorder.record_tokens({'codex':8})
            recorder.record_quota('codex',[dict(title='fixture private label',usedPercent=10,windowMinutes=300,
                                               resetsAt=datetime.fromtimestamp(now+5000,timezone.utc).isoformat(),token='fixture secret')])
            recorder.close()
            result=history.read_history(root,['codex'],now=now+1)
            self.assertEqual(sum(r['total'] for r in result['tokens']),20)
            self.assertEqual(len(result['quota']),1)
            self.assertNotIn(b'fixture',(root/'history.db').read_bytes())
            self.assertEqual(history.read_history(root,['gemini'],now=now+1)['tokens'],[])
            self.assertEqual(result['forecasts'],[])

    def fixture(self,root,rows):
        with closing(history.connect(root,True)) as db,db:
            db.executemany('INSERT INTO quota VALUES(?,?,?,?,?,?,?)',rows)

    def test_forecast_requires_fresh_monotonic_same_reset_and_epoch(self):
        with tempfile.TemporaryDirectory() as name:
            now=1800000000; minute=now//60
            rows=[('codex',minute-i,300,'model',30-i*5,now+5000,1) for i in (0,1,2)]
            self.fixture(name,rows)
            result=history.read_history(name,['codex'],now=now+1)
            self.assertAlmostEqual(result['forecasts'][0]['percent_per_hour'],300)
            self.assertAlmostEqual(result['forecasts'][0]['estimated_hours_to_limit'],70/300)
            self.assertEqual(history.read_history(name,['codex'],now=now+700)['forecasts'],[])
            with closing(history.connect(name,True)) as db,db:
                db.execute('UPDATE quota SET epoch=2 WHERE minute=?',(minute,))
            self.assertEqual(history.read_history(name,['codex'],now=now+1)['forecasts'],[])
            with closing(history.connect(name,True)) as db,db:
                db.execute('UPDATE quota SET epoch=1,reset=0')
            self.assertEqual(history.read_history(name,['codex'],now=now+1)['forecasts'],[])

    def test_resets_decreases_gaps_and_incomplete_samples_have_no_prediction(self):
        for minutes,values in (((0,1),(30,25)),((0,1,2),(10,30,25)),((0,1,30),(30,25,20))):
            with tempfile.TemporaryDirectory() as name:
                now=1800000000; m=now//60
                self.fixture(name,[('codex',m-i,300,'model',u,now+5000,1) for i,u in zip(minutes,values)])
                self.assertEqual(history.read_history(name,['codex'],now=now+1)['forecasts'],[])

    def test_unknown_or_tampered_databases_are_readonly_and_fail_safely(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); path=root/'history.db'; path.write_bytes(b'fixture unknown file')
            before=path.read_bytes()
            self.assertTrue(history.read_history(root,['codex'])['error'])
            self.assertEqual(path.read_bytes(),before)
        with tempfile.TemporaryDirectory() as name:
            now=1800000000
            self.fixture(name,[('codex',now//60,300,'=fixture formula',50,now+5000,1)])
            result=history.read_history(name,['codex'],now=now+1)
            self.assertTrue(result['error']); self.assertEqual(result['quota'],[])

    def test_disk_writer_does_not_block_usb_submission_or_disable(self):
        with tempfile.TemporaryDirectory() as name:
            entered,release=threading.Event(),threading.Event(); actual=history.connect
            def slow(*a,**kw):
                entered.set(); release.wait(2); return actual(*a,**kw)
            recorder=history.HistoryRecorder(name,True)
            with patch.object(history,'connect',side_effect=slow):
                try:
                    recorder.record_tokens({'codex':1}); self.assertTrue(entered.wait(1))
                    start=time.monotonic()
                    recorder.record_quota('codex',[{'usedPercent':10,'windowMinutes':300}])
                    recorder.configure(False)
                    self.assertLess(time.monotonic()-start,.1)
                finally: release.set(); recorder.close()
            self.assertEqual(history.read_history(name,['codex'])['tokens'],[])

    def test_retention_and_numeric_limits(self):
        with tempfile.TemporaryDirectory() as name:
            now=[1800000000]; recorder=history.HistoryRecorder(name,True,clock=lambda:now[0])
            recorder.record_tokens({'codex':5}); recorder.close()
            now[0]+=31*86400
            recorder=history.HistoryRecorder(name,True,clock=lambda:now[0]); recorder.record_tokens({'codex':3}); recorder.close()
            self.assertEqual(sum(r['total'] for r in history.read_history(name,['codex'],30,now[0])['tokens']),3)
            with closing(history.connect(name)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM tokens').fetchone()[0],1)


if __name__=='__main__': unittest.main()
