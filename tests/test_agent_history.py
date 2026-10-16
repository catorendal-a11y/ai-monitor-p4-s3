"""Synthetic event-only history, never real hooks/accounts or conversation files."""
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import agent_history as history
from usage_history import connect,HistoryRecorder,APPLICATION_ID
from device_history import compact_history


class AgentHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        with closing(connect(self.root,True)):pass
        history.configure(self.root,True,17)
        self.agent=hashlib.sha256(b'synthetic session').hexdigest()
    def event(self,event,state,at,agent=None,root=True,generation=7):
        history.record(self.root,'codex',agent or self.agent,generation,event,state,at,root)
    def summary(self,start=0,end=10000):
        with closing(connect(self.root)) as db:return history.summarize(db,'codex',start,end)
    def test_waiting_is_excluded_and_turn_completion_is_not_task_success(self):
        for event,state,at in [('SessionStart','IDLE',1),('UserPromptSubmit','WORKING',10),
              ('PermissionRequest','WAITING',30),('PreToolUse','RUNNING',50),('Stop','COMPLETED',70)]:
            self.event(event,state,at)
        self.assertEqual(self.summary(),dict(sessions=1,activeSeconds=40,completedTurns=1,failedTurns=0))
        self.assertNotIn('task',str(self.summary()).lower())
    def test_zcode_documented_lifecycle_is_recorded_in_opt_in_history(self):
        for event,state,at in [('SessionStart','IDLE',1),('UserPromptSubmit','WORKING',10),
                               ('PreToolUse','READING',20),('Stop','COMPLETED',40)]:
            history.record(self.root,'zcode',self.agent,7,event,state,at,True)
        with closing(connect(self.root)) as db:
            result=history.summarize(db,'zcode',0,100)
        self.assertEqual(result,dict(sessions=1,activeSeconds=30,completedTurns=1,failedTurns=0))

    def test_zcode_history_respects_disabled_consent(self):
        history.configure(self.root,False,18)
        history.record(self.root,'zcode',self.agent,7,'SessionStart','IDLE',1,True)
        with closing(connect(self.root)) as db:
            self.assertIsNone(history.summarize(db,'zcode',0,100)['sessions'])
    def test_parallel_agents_union_active_time_and_subagents_do_not_inflate_sessions(self):
        second=hashlib.sha256(b'synthetic subagent').hexdigest()
        self.event('SessionStart','IDLE',1);self.event('UserPromptSubmit','WORKING',10)
        self.event('SubagentStart','WORKING',20,second,False)
        self.event('Stop','COMPLETED',40);self.event('SubagentStop','COMPLETED',50,second,False)
        result=self.summary();self.assertEqual(result['activeSeconds'],40);self.assertEqual(result['sessions'],1)
    def test_duplicates_and_stop_without_start_cannot_invent_completed_turns(self):
        self.event('Stop','COMPLETED',1);self.assertIsNone(self.summary()['completedTurns'])
        self.event('UserPromptSubmit','WORKING',10);self.event('Stop','COMPLETED',20)
        self.event('Stop','COMPLETED',21);self.assertEqual(self.summary()['completedTurns'],1)
    def test_long_gaps_epochs_future_and_waiting_do_not_create_active_time(self):
        self.event('UserPromptSubmit','WORKING',10);self.event('Stop','COMPLETED',1000)
        self.assertIsNone(self.summary()['activeSeconds'])
        self.event('UserPromptSubmit','WORKING',2000)
        history.configure(self.root,True,18);self.event('Stop','COMPLETED',2005)
        self.assertIsNone(self.summary()['activeSeconds'])
        self.assertIsNone(self.summary(end=0)['sessions'])
    def test_daily_interval_is_clipped_and_failures_are_real_stop_failure_events(self):
        self.event('UserPromptSubmit','WORKING',90);self.event('StopFailure','ERROR',110)
        self.assertEqual(self.summary(100,120)['activeSeconds'],10)
        self.assertEqual(self.summary(100,120)['failedTurns'],1)
    def test_disabling_or_unknown_schema_rejects_writes_and_keeps_data_private(self):
        history.configure(self.root,False,18);self.event('SessionStart','IDLE',1)
        self.assertIsNone(self.summary()['sessions'])
        history.configure(self.root,True,19)
        with closing(connect(self.root)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM agent_events').fetchone()[0],0)
        history.record(self.root,'codex','raw private id',7,'SessionStart','IDLE',1,True)
        history.record(self.root,'codex',self.agent,7,'private prompt','IDLE',1,True)
        self.assertNotIn(b'private',(self.root/'history.db').read_bytes())
    def test_consent_change_between_read_and_commit_cancels_event(self):
        with patch.object(history,'read_local_json',side_effect=[dict(enabled=True,epoch=17),dict(enabled=False,epoch=18)]):
            self.event('SessionStart','IDLE',1)
        self.assertIsNone(self.summary()['sessions'])
    def test_schema_one_migration_preserves_existing_numeric_history(self):
        with closing(sqlite3.connect(self.root/'history.db')) as db,db:
            db.execute('DROP TABLE agent_events');db.execute('PRAGMA user_version=1')
            db.execute('INSERT INTO tokens VALUES(?,?,?)',('codex',10,42))
        with closing(connect(self.root)) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
        with closing(connect(self.root,True)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT tokens FROM tokens').fetchone()[0],42)
    def test_corrupt_journal_never_returns_partially_valid_summary(self):
        with closing(connect(self.root,True)) as db,db:
            db.execute('INSERT INTO agent_events VALUES(?,?,?,?,?,?,?,?,?)',('1','codex',self.agent,7,17,'Stop','PRIVATE',5,1))
        with self.assertRaises(ValueError):self.summary()
    def test_recorder_initializes_event_history_without_waiting_for_tokens(self):
        folder=self.root/'new';recorder=HistoryRecorder(folder,True);self.addCleanup(recorder.close)
        deadline=time.monotonic()+2
        while not (folder/'agent-history-consent.json').exists() and time.monotonic()<deadline:time.sleep(.005)
        self.assertTrue((folder/'history.db').exists())
        recorder.close()
        import json
        self.assertFalse(json.loads((folder/'agent-history-consent.json').read_text())['enabled'])

    def wait_marker(self,folder,enabled):
        import json
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            try:
                value=json.loads((folder/'agent-history-consent.json').read_text())
                if value['enabled'] is enabled:return value
            except (OSError,ValueError):pass
            time.sleep(.005)
        self.fail('History consent marker did not settle')

    def test_unchanged_opt_in_preserves_epoch_and_disable_wakes_idle_worker(self):
        folder=self.root/'idle';recorder=HistoryRecorder(folder,True);self.addCleanup(recorder.close)
        before=self.wait_marker(folder,True)
        recorder.configure(True)
        self.assertEqual(recorder.epoch,before['epoch'])
        recorder.configure(False)
        after=self.wait_marker(folder,False)
        self.assertNotEqual(before['epoch'],after['epoch'])
        self.assertTrue(recorder.worker.is_alive())

    def test_disable_during_consent_publication_revokes_superseded_epoch(self):
        folder=self.root/'race';entered=threading.Event();resume=threading.Event()
        original=history.configure
        def publication(directory,enabled,epoch):
            if enabled:
                entered.set();resume.wait(2)
            original(directory,enabled,epoch)
        with patch.object(history,'configure',side_effect=publication):
            recorder=HistoryRecorder(folder,True)
            try:
                self.assertTrue(entered.wait(2));recorder.configure(False);resume.set()
                self.wait_marker(folder,False)
                self.assertFalse(recorder.enabled)
            finally:resume.set();recorder.close()

    def test_failed_database_initialization_revokes_old_hook_consent(self):
        with patch('usage_history.connect',side_effect=sqlite3.OperationalError('synthetic unavailable storage')):
            recorder=HistoryRecorder(self.root,True)
            try:self.wait_marker(self.root,False)
            finally:recorder.close()
        self.assertFalse(recorder.worker.is_alive())

    def test_hook_writer_lock_timeout_and_invalid_arguments_are_bounded(self):
        with closing(sqlite3.connect(self.root/'history.db')) as locked:
            locked.execute('BEGIN IMMEDIATE')
            before=time.monotonic();self.event('SessionStart','IDLE',1)
            self.assertLess(time.monotonic()-before,.2)
            locked.rollback()
        self.assertIsNone(self.summary()['sessions'])
        history.record(self.root,'codex',self.agent,7,[],{},1,True)
        for start,end in ((True,10),(10,9),(0,float('nan'))):
            with self.assertRaises(ValueError):self.summary(start,end)

    def test_equal_timestamp_events_keep_received_order_not_random_identifier_order(self):
        # UUIDs are deliberately reverse-sorted: they must not reorder a prompt and stop.
        with patch.object(history.secrets,'token_hex',side_effect=['f'*32,'0'*32]):
            self.event('UserPromptSubmit','WORKING',10);self.event('Stop','COMPLETED',10)
        self.assertEqual(self.summary()['completedTurns'],1)

    def test_normalized_hook_journals_only_fixed_metadata_not_input_or_transcript(self):
        from live_events import lifecycle_event
        from telemetry_bridge import write_record
        write_record(self.root/'codex-session-link.json',dict(enabled=True,generation=7))
        for event,at in [('SessionStart',1),('UserPromptSubmit',10),('PreToolUse',20),('Stop',30)]:
            lifecycle_event('codex',dict(session_id='synthetic private session',hook_event_name=event,
                tool_name='apply_patch',tool_input={'secret':'DO_NOT_STORE_ARGUMENT'},
                prompt='DO_NOT_STORE_PROMPT',transcript_path='DO_NOT_OPEN_TRANSCRIPT'),self.root,7,at)
        self.assertEqual(self.summary()['completedTurns'],1)
        with closing(connect(self.root)) as db:
            rows=str(db.execute('SELECT * FROM agent_events').fetchall())
        for sensitive in ('DO_NOT_STORE_ARGUMENT','DO_NOT_STORE_PROMPT','DO_NOT_OPEN_TRANSCRIPT','synthetic private session'):
            self.assertNotIn(sensitive,rows)
            self.assertNotIn(sensitive.encode(),(self.root/'history.db').read_bytes())

if __name__=='__main__':unittest.main()
