"""Task counts require successful post-tool results, never pre-veto completion hooks."""
from contextlib import closing
from datetime import datetime
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import agent_history as history
from usage_history import connect


class TaskHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        with closing(connect(self.root,True)):pass
        history.configure(self.root,True,17)

    def payload(self,name='TaskUpdate',event='PostToolUse',**response):
        return dict(hook_event_name=event,session_id='private session',tool_use_id='own tool use',
            tool_name=name,tool_input=dict(taskId='private task',status='completed'),
            tool_response=dict(success=True,taskId='private task',statusChange=dict(
                **{'from':'in_progress','to':'completed'}),**response))

    def record(self,payload,at=10):history.observe_task(self.root,payload,7,at)
    def summary(self,start=0,end=100):
        with closing(connect(self.root)) as db:return history.task_summary(db,'claude',start,end)

    def test_confirmed_post_tool_transition_is_counted_once_without_text_or_raw_ids(self):
        payload=self.payload();payload['tool_response']['private_response']='NEVER STORE THIS'
        self.record(payload);self.record(payload)
        result=self.summary()
        self.assertEqual(result['completedTasks'],1)
        self.assertIsNone(result['failedTasks'])
        raw=(self.root/'history.db').read_bytes()
        for text in (b'private session',b'private task',b'NEVER STORE THIS'):self.assertNotIn(text,raw)

    def test_pre_veto_failure_mismatch_and_repeated_completed_status_do_not_count(self):
        cases=[self.payload(event='TaskCompleted'),self.payload(event='PostToolUseFailure')]
        p=self.payload();p['tool_response']['success']=False;cases.append(p)
        p=self.payload();p['tool_response']['taskId']='other';cases.append(p)
        p=self.payload();p['tool_response']['statusChange']['from']='completed';cases.append(p)
        p=self.payload();p['tool_response']['success']=1;cases.append(p)
        p=self.payload('TaskGet');p['tool_response']={'task':{'id':'private task','status':'completed'}};cases.append(p)
        for payload in cases:self.record(payload)
        self.assertIsNone(self.summary()['completedTasks'])

    def test_create_start_and_finish_report_distinct_client_tasks_not_turns(self):
        self.record(dict(hook_event_name='PostToolUse',session_id='private session',tool_use_id='create',
            tool_name='TaskCreate',tool_input={'subject':'DO NOT STORE'},
            tool_response={'task':{'id':'private task','subject':'DO NOT STORE'}}),1)
        started=self.payload();started['tool_use_id']='start'
        started['tool_input']['status']='in_progress'
        started['tool_response']['statusChange']={'from':'pending','to':'in_progress'}
        self.record(started,2);self.record(self.payload(),3)
        self.assertEqual(self.summary(),dict(createdTasks=1,startedTasks=1,completedTasks=1,failedTasks=None))
        with closing(connect(self.root)) as db:
            self.assertIsNone(history.summarize(db,'claude',0,100)['completedTurns'])

    def test_consent_off_clock_errors_and_old_database_are_unknown(self):
        history.configure(self.root,False,18);self.record(self.payload())
        self.assertIsNone(self.summary()['completedTasks'])
        history.configure(self.root,True,19)
        for at in (True,float('nan'),-1):self.record(self.payload(),at)
        self.assertIsNone(self.summary()['completedTasks'])
        with closing(connect(self.root,True)) as db,db:
            db.execute('DROP TABLE task_events')
        self.assertIsNone(self.summary()['completedTasks'])

    def test_half_open_day_does_not_double_count_midnight_and_reopened_task_is_one_task(self):
        self.record(self.payload(),50)
        other=self.payload();other['tool_use_id']='second completion'
        self.record(other,60)
        self.assertEqual(self.summary()['completedTasks'],1)
        with closing(connect(self.root)) as db:
            self.assertIsNone(history.task_summary(db,'claude',0,50,end_exclusive=True)['completedTasks'])
            self.assertEqual(history.task_summary(db,'claude',50,100)['completedTasks'],1)
