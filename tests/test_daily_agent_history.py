"""Local-day lifecycle reports use synthetic opt-in records only."""
from contextlib import closing
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import agent_history
from usage_history import connect,read_history


class DailyAgentHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.now=datetime(2026,10,16,12).timestamp()
        self.midnight=datetime(2026,10,16).timestamp()
        self.agent=hashlib.sha256(b'fixture').hexdigest()
        with closing(connect(self.root,True)):pass
        agent_history.configure(self.root,True,1)

    def event(self,event,state,at,provider='zcode'):
        agent_history.record(self.root,provider,self.agent,1,event,state,at,True)

    def test_local_daily_summary_includes_sessions_union_time_and_real_turn_outcomes(self):
        for event,state,at in [('SessionStart','IDLE',10),('UserPromptSubmit','WORKING',20),
                               ('PermissionRequest','WAITING',30),('PreToolUse','READING',40),
                               ('Stop','COMPLETED',60)]:
            self.event(event,state,self.midnight+at)
        result=read_history(self.root,['zcode'],7,self.now)
        rows=result.get('daily_agents',[])
        self.assertEqual(len(rows),7)
        self.assertEqual(rows[-1],dict(provider='zcode',date='2026-10-16',
            sessions=1,activeSeconds=30,completedTurns=1,failedTurns=0))
        self.assertIsNone(rows[0]['sessions'])
        self.assertNotIn('tasks',rows[-1])

    def test_midnight_event_is_counted_only_on_its_own_day(self):
        self.event('UserPromptSubmit','WORKING',self.midnight-10)
        self.event('Stop','COMPLETED',self.midnight)
        rows=read_history(self.root,['zcode'],7,self.now).get('daily_agents',[])
        self.assertEqual(len(rows),7)
        self.assertEqual(rows[-1]['completedTurns'],1)
        self.assertIsNone(rows[-2]['completedTurns'])
        self.assertEqual(rows[-2]['activeSeconds'],10)
        self.assertIsNone(rows[-1]['activeSeconds'])

    def test_missing_database_does_not_create_a_database_or_fabricate_zeroes(self):
        folder=self.root/'absent'
        result=read_history(folder,['zcode'],7,self.now)
        self.assertIn('daily_agents',result)
        self.assertEqual(result['daily_agents'],[])
        self.assertFalse(folder.exists())

    def test_corrupt_event_clears_the_entire_report(self):
        with closing(connect(self.root,True)) as db,db:
            db.execute('INSERT INTO agent_events VALUES(?,?,?,?,?,?,?,?,?)',
                ('bad','zcode',self.agent,1,1,'Stop','PRIVATE',self.midnight+50,1))
        report=read_history(self.root,['zcode'],7,self.now)
        self.assertIsNotNone(report['error'])
        self.assertEqual(report.get('daily_agents'),[])

    def test_invalid_clock_is_rejected(self):
        for clock in (True,float('nan'),-1):
            with self.subTest(clock=clock),self.assertRaises(ValueError):
                read_history(self.root,['zcode'],7,clock)


if __name__=='__main__':unittest.main()
