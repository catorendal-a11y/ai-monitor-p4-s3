"""Audit regressions use temporary databases and synthetic lifecycle events only."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import agent_history as history
from usage_history import connect,HistoryRecorder

class HistoryFixTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)/'activity'
        with closing(connect(self.folder,True)):pass
        history.configure(self.folder,True,17)
        self.agent=hashlib.sha256(b'synthetic').hexdigest()
    def insert(self,event,state,at,epoch=17):
        with closing(connect(self.folder,True)) as db,db:
            db.execute('INSERT INTO agent_events VALUES(?,?,?,?,?,?,?,?,?)',
                (str(time.time_ns()),'claude',self.agent,7,epoch,event,state,at,1))
    def test_midnight_outcomes_keep_older_prompt_but_do_not_count_gaps_as_active(self):
        for terminal,state,field in [('Stop','COMPLETED','completedTurns'),('StopFailure','ERROR','failedTurns')]:
            with self.subTest(terminal=terminal):
                with closing(connect(self.folder,True)) as db,db:db.execute('DELETE FROM agent_events')
                self.insert('UserPromptSubmit','WORKING',1000)
                self.insert('PreToolUse','READING',1500)
                self.insert('PostToolUse','WORKING',1900)
                self.insert(terminal,state,2100)
                with closing(connect(self.folder)) as db:result=history.summarize(db,'claude',2000,2200)
                self.assertEqual(result[field],1)
                self.assertEqual(result['activeSeconds'],100)
    def test_old_finished_turn_or_consent_epoch_cannot_seed_new_outcome(self):
        self.insert('UserPromptSubmit','WORKING',1);self.insert('Stop','COMPLETED',2)
        self.insert('Stop','COMPLETED',2100)
        with closing(connect(self.folder)) as db:self.assertIsNone(history.summarize(db,'claude',2000,2200)['completedTurns'])
        self.insert('UserPromptSubmit','WORKING',1000,18)
        with closing(connect(self.folder)) as db:self.assertIsNone(history.summarize(db,'claude',2000,2200)['completedTurns'])
    def test_numeric_maintenance_prunes_old_agent_and_task_events_without_hooks(self):
        self.insert('UserPromptSubmit','WORKING',1)
        with closing(connect(self.folder,True)) as db,db:
            db.execute('INSERT INTO task_events VALUES(?,?,?,?,?,?,?)',('old','claude',self.agent,7,17,'created',1))
        recorder=HistoryRecorder(self.folder,True);self.addCleanup(recorder.close)
        recorder.record_tokens({'claude':1})
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            with closing(connect(self.folder)) as db:
                count=db.execute('SELECT COUNT(*) FROM agent_events').fetchone()[0]+db.execute('SELECT COUNT(*) FROM task_events').fetchone()[0]
            if not count:break
            time.sleep(.01)
        self.assertEqual(count,0)
    def test_enabled_marker_has_bounded_lease_and_expired_hooks_do_not_write(self):
        marker=json.loads((self.folder/'agent-history-consent.json').read_text())
        self.assertGreater(marker.get('expires_at',0),time.time())
        with patch.object(history.time,'time',return_value=time.time()+100):
            history.record(self.folder,'claude',self.agent,7,'SessionStart','IDLE',1,True)
            history.observe_task(self.folder,dict(hook_event_name='PostToolUse',session_id='s',tool_use_id='u',
                tool_name='TaskCreate',tool_input={},tool_response={'task':{'id':'1'}}),7,1)
        with closing(connect(self.folder)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM agent_events').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM task_events').fetchone()[0],0)
    def test_idle_recorder_refreshes_lease_without_new_samples(self):
        with patch('usage_history.CONSENT_RENEW_SECONDS',.03,create=True):
            recorder=HistoryRecorder(self.folder,True);self.addCleanup(recorder.close)
            deadline=time.monotonic()+2;seen=[]
            while time.monotonic()<deadline:
                marker=json.loads((self.folder/'agent-history-consent.json').read_text())
                if marker['epoch']==recorder.epoch:
                    seen.append(marker.get('expires_at'))
                    if len(set(seen))>1:break
                time.sleep(.01)
            recorder.close()
        self.assertGreater(len(set(seen)),1)
    def test_thirty_day_summary_at_full_journal_budget_respects_sql_deadline(self):
        from usage_history import read_history
        import sqlite3
        now=time.time();begin=now-29*86400
        with closing(sqlite3.connect(self.folder/'history.db')) as db,db:
            db.executemany('INSERT INTO agent_events VALUES(?,?,?,?,?,?,?,?,?)',
                ((str(i),'claude',self.agent,7,17,'Stop' if i%2 else 'UserPromptSubmit',
                  'COMPLETED' if i%2 else 'WORKING',begin+i*(29*86400/50000),1)
                 for i in range(50000)))
        data=read_history(self.folder,['claude'],30,now)
        self.assertIsNone(data['error'])
        self.assertEqual(sum(row['completedTurns'] or 0 for row in data['daily_agents']),25000)

    def test_revoke_existing_marker_and_no_creation_for_missing_directory(self):
        revoke=getattr(history,'revoke',None)
        self.assertTrue(callable(revoke),'Missing explicit consent revocation API')
        revoke(self.folder)
        self.assertFalse(json.loads((self.folder/'agent-history-consent.json').read_text())['enabled'])
        missing=Path(self.temp.name)/'missing'
        revoke(missing)
        self.assertFalse(missing.exists())

if __name__=='__main__':unittest.main()
