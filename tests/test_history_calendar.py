from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
import sys, tempfile, unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import usage_history as history
import agent_history

class HistoryCalendarTests(unittest.TestCase):
    def test_calendar_buckets_honor_midnight_and_23_25_hour_days(self):
        for hours in (23,25):
            with self.subTest(hours=hours), tempfile.TemporaryDirectory() as folder:
                start=1800000000//60*60; finish=start+hours*3600; now=finish+3600
                boundaries=[('2026-10-24',start,finish),('2026-10-25',finish,finish+86400)]
                with closing(history.connect(folder,True)) as db,db:
                    db.executemany('INSERT INTO tokens VALUES(?,?,?)',[
                        ('codex',start//60-1,100),('codex',start//60,2),
                        ('codex',finish//60-1,3),('codex',finish//60,7)])
                with patch.object(history,'calendar_days',return_value=boundaries,create=True):
                    rows=history.read_history(folder,['codex'],7,now)['tokens']
                self.assertEqual([(r.get('date'),r['total']) for r in rows],[('2026-10-24',5),('2026-10-25',7)])
                with closing(history.connect(folder)) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM tokens').fetchone()[0],4)

    def test_daily_unknowns_explain_terminal_and_unsupported_task_evidence(self):
        with tempfile.TemporaryDirectory() as folder,closing(history.connect(folder,True)) as db,db:
            now=datetime(2026,10,16,12).timestamp()
            db.execute('INSERT INTO agent_events VALUES(?,?,?,?,?,?,?,?,?)',
                       ('fixture','codex','a'*64,1,1,'UserPromptSubmit','WORKING',now-10,1))
            rows=history.read_history(folder,['codex'],7,now)['daily_agents']
            self.assertEqual(rows[-1].get('unknownReasons',{}).get('completedTurns'),'no_terminal_evidence')
            self.assertEqual(rows[-1].get('unknownReasons',{}).get('completedTasks'),'unsupported_tasks')

    def test_clear_revokes_old_writer_without_unlinking_database(self):
        with tempfile.TemporaryDirectory() as folder:
            with closing(history.connect(folder,True)) as db,db:
                db.execute('INSERT INTO tokens VALUES(?,?,?)',('codex',100,9))
            agent_history.configure(folder,True,1)
            history.clear_history(folder)
            self.assertTrue((Path(folder)/'history.db').is_file())
            self.assertFalse(agent_history.configure(folder,True,1))
            with closing(history.connect(folder)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM tokens').fetchone()[0],0)

    def test_clear_failure_is_atomic_and_old_authority_stays_revoked(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            with closing(history.connect(folder,True)) as db,db:
                db.execute('INSERT INTO tokens VALUES(?,?,?)',('codex',100,9))
                db.execute("CREATE TRIGGER fixture_block_clear BEFORE DELETE ON task_events BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
                db.execute('INSERT INTO task_events VALUES(?,?,?,?,?,?,?)',('fixture','claude','a'*64,1,1,'created',100.))
            agent_history.configure(folder,True,1)
            with self.assertRaises(sqlite3.Error):history.clear_history(folder)
            self.assertFalse(agent_history.configure(folder,True,1))
            with closing(history.connect(folder)) as db:
                self.assertEqual(db.execute('SELECT tokens FROM tokens').fetchone()[0],9)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM task_events').fetchone()[0],1)

    def test_mixed_task_identities_have_specific_reason_without_changing_usb_summary(self):
        with tempfile.TemporaryDirectory() as folder,closing(history.connect(folder,True)) as db,db:
            now=datetime(2026,10,16,12).timestamp()
            for index,key in enumerate(('a'*64,'v2:'+'b'*64)):
                db.execute('INSERT INTO task_events VALUES(?,?,?,?,?,?,?)',
                           (str(index),'claude',key,1,1,'completed',now-10))
            db.commit()
            plain=agent_history.task_summary(db,'claude',now-100,now)
            self.assertNotIn('unknownReasons',plain)
            row=history.read_history(folder,['claude'],7,now)['daily_agents'][-1]
            self.assertIsNone(row['completedTasks'])
            self.assertEqual(row['unknownReasons']['completedTasks'],'mixed_task_identity')

if __name__=='__main__':unittest.main()
