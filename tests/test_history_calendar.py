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

if __name__=='__main__':unittest.main()
