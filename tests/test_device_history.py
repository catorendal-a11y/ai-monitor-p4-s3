"""Synthetic local SQLite summaries; no real history, providers or USB."""
from contextlib import closing
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from usage_history import connect, MAX_INTEGER
from device_history import compact_history, HistorySampler
from usb_history import UsbHistoryClient

class DeviceHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.starts=[29000000+1440*i for i in range(8)]
        self.now=(self.starts[6]+780)*60
        self.boundaries=('2026-10-14',self.starts)
    def summary(self,enabled=True):
        return compact_history(self.root,['codex','zcode'],enabled,self.now,self.boundaries)
    def rows(self,tokens=(),quota=()):
        with closing(connect(self.root,create=True)) as database,database:
            database.executemany('INSERT OR REPLACE INTO tokens VALUES(?,?,?)',tokens)
            database.executemany('INSERT OR REPLACE INTO quota VALUES(?,?,?,?,?,?,?)',quota)
    def test_disabled_never_opens_database_and_missing_records_stay_unknown(self):
        with patch('device_history.connect') as opened:
            self.assertEqual(self.summary(False)['providers'],[]);opened.assert_not_called()
        result=self.summary();self.assertIsNone(result['providers'][0]['today'])
        self.assertEqual(result['providers'][0]['hourly'],[None]*24);self.assertFalse(result['error'])
        self.assertFalse((self.root/'history.db').exists())
    def test_exact_day_and_hour_buckets_exclude_future_and_other_providers(self):
        start=self.starts[6];hour=int(self.now)//3600
        self.rows([('codex',start-1,11),('codex',start,20),('codex',hour*60,30),
                   ('codex',int(self.now)//60+1,99),('gemini',start,999),('zcode',start,7)])
        codex,zcode=self.summary()['providers'];self.assertEqual(codex['today'],50)
        self.assertEqual(codex['daily'][5],11);self.assertEqual(codex['hourly'][23],30)
        self.assertEqual(zcode['today'],7);self.assertIsNone(codex['daily'][0])
    def test_day_boundaries_support_23_and_25_hour_days(self):
        starts=[self.starts[0]]
        for hours in (24,23,25,24,24,24,24):starts.append(starts[-1]+hours*60)
        self.rows([('codex',starts[1],8),('codex',starts[2]-1,9)])
        result=compact_history(self.root,['codex'],True,(starts[6]+50)*60,('2026-10-14',starts))
        self.assertEqual(result['providers'][0]['daily'][1],17)
    def test_quota_trend_does_not_merge_windows_resets_epochs_or_tool_limits(self):
        start=self.starts[6];now=int(self.now)//60
        self.rows(quota=[('codex',start,300,'model',10.,self.now+1000,1),
                        ('codex',now,300,'model',40.,self.now+1000,1),
                        ('codex',start,10080,'model',99.,self.now+5000,1),
                        ('codex',now,43200,'tools',98.,self.now+5000,1)])
        quota=self.summary()['providers'][0]['quota'];self.assertEqual(quota['windowMinutes'],300)
        self.assertEqual(quota['changePercent'],30.)
        self.rows(quota=[('codex',now,300,'model',5.,self.now+2000,2)])
        self.assertIsNone(self.summary()['providers'][0]['quota']['changePercent'])
    def test_overflow_corruption_and_unknown_schema_never_return_partial_totals(self):
        start=self.starts[6]
        self.rows([('codex',start,MAX_INTEGER),('codex',start+1,1),('zcode',start,7)])
        result=self.summary();self.assertTrue(result['error'])
        self.assertTrue(all(p['today'] is None for p in result['providers']))
    def test_sampler_runs_read_off_caller_thread_and_discards_disabled_generation(self):
        sampler=HistorySampler(self.root,['codex'],False);self.addCleanup(sampler.close)
        self.assertIsNone(sampler.take())
        deadline=time.monotonic()+2;result=None
        while result is None and time.monotonic()<deadline:
            time.sleep(.005);result=sampler.take()
        self.assertIsNotNone(result);self.assertFalse(result['enabled'])
        self.assertFalse((self.root/'history.db').exists())
        sampler.configure(True,['zcode']);sampler.take();sampler.configure(False,['codex']);sampler.take()
        deadline=time.monotonic()+2;result=None
        while result is None and time.monotonic()<deadline:
            time.sleep(.005);result=sampler.take()
        self.assertFalse(result['enabled']);self.assertEqual(result['providers'],[])

    def test_usb_summary_has_bounded_individual_packets_and_exact_receipts(self):
        import json
        class Panel:
            info=dict(bootId=17)
            def __init__(self):self.messages=[];self.corrupt=None
            def send_line(self,raw):self.messages.append(json.loads(raw));self.assert_size=len(raw)
            def wait_for(self,kind,seconds,command):
                message=self.messages[-1]
                result=dict(type='history_reply',schema=1,cmd=command,ok=True,bootId=17,
                            epoch=message['epoch'],revision=message['revision'],index=message.get('index',0))
                if self.corrupt:result.update(self.corrupt)
                return result
        panel=Panel();client=UsbHistoryClient(panel,lambda:self.now)
        summary=self.summary();client.send(summary)
        self.assertEqual(len(panel.messages),3);self.assertLess(panel.assert_size,4095)
        self.assertEqual(panel.messages[0]['sampleAgeSeconds'],0)
        self.assertIsNone(panel.messages[1]['today']);self.assertEqual(panel.messages[1]['daily'],[None]*7)
        for change in ({'ok':1},{'schema':True},{'epoch':0},{'index':True},{'revision':0}):
            panel.corrupt=change
            with self.assertRaises(ValueError):client.send(summary)
        panel.corrupt=None
        summary['sampledAt']=self.now-121
        before=len(panel.messages)
        with self.assertRaises(ValueError):client.send(summary)
        self.assertEqual(len(panel.messages),before)

    def test_invalid_selection_dates_clocks_and_future_buckets_are_rejected(self):
        for providers in (['codex','codex'],['unknown']):
            with self.assertRaises(ValueError):compact_history(self.root,providers,True,self.now,self.boundaries)
        for now in (True,float('nan'),-1):
            with self.assertRaises(ValueError):compact_history(self.root,['codex'],True,now,self.boundaries)
        for date in ('2026-02-30','2026/10/14'):
            with self.assertRaises(ValueError):compact_history(self.root,['codex'],True,self.now,(date,self.starts))

    def test_daily_agent_summary_is_observed_and_token_only_provider_stays_unknown(self):
        import hashlib
        from agent_history import configure,record
        self.rows([('codex',self.starts[6],5),('zcode',self.starts[6],99)])
        configure(self.root,True,17)
        identity=hashlib.sha256(b'synthetic daily agent').hexdigest()
        start=self.starts[6]*60
        for event,state,offset in [('SessionStart','IDLE',1),('UserPromptSubmit','WORKING',10),
                                   ('PermissionRequest','WAITING',30),('PreToolUse','EDITING',50),
                                   ('Stop','COMPLETED',70)]:
            record(self.root,'codex',identity,7,event,state,start+offset,True)
        codex,zcode=self.summary()['providers']
        self.assertEqual(codex['agents'],dict(sessions=1,activeSeconds=40,completedTurns=1,failedTurns=0))
        self.assertTrue(all(value is None for value in zcode['agents'].values()))
        self.assertNotIn('task',str(codex['agents']).lower())

    def test_schema_one_device_reader_preserves_token_history_with_unknown_agent_metrics(self):
        self.rows([('codex',self.starts[6],42)])
        with closing(connect(self.root,create=True)) as database,database:
            database.execute('DROP TABLE agent_events');database.execute('PRAGMA user_version=1')
        result=self.summary();self.assertFalse(result['error'])
        self.assertEqual(result['providers'][0]['today'],42)
        self.assertTrue(all(value is None for value in result['providers'][0]['agents'].values()))

    def test_corrupt_agent_journal_clears_all_summaries_including_valid_tokens(self):
        self.rows([('codex',self.starts[6],42),('zcode',self.starts[6],9)])
        with closing(connect(self.root,create=True)) as database,database:
            database.execute('INSERT INTO agent_events VALUES(?,?,?,?,?,?,?,?,?)',
                ('invalid','codex','private raw id',7,17,'Stop','COMPLETED',self.now-1,1))
        result=self.summary();self.assertTrue(result['error'])
        self.assertTrue(all(p['today'] is None and all(v is None for v in p['agents'].values())
                            for p in result['providers']))
