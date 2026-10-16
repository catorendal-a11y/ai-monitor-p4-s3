"""Terminal data boundaries and real keyboard/resize flows, using synthetic metadata."""
import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import terminal_data as data
from aim_terminal import TerminalApp
from textual.widgets import TabbedContent,Static


class TerminalDataTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.config=dict(providers=['codex','claude'],board='guition-p4',port='COM6',
                         interval_s=30,token_poll_s=2,usage_history=True,zai_key='DO-NOT-DISPLAY')

    def collect(self,health=None,history=None,agents=None):
        with patch.object(data,'local_config',return_value=self.config),patch.object(data,'owned_hosts',return_value=[]),\
             patch.object(data,'read_status',return_value=health),\
             patch.object(data,'compact_history',return_value=history or {'providers':[],'error':False}),\
             patch.object(data,'live_agents',return_value=agents or []):
            return data.read_dashboard(self.root,now=1000)

    def test_no_invented_quotas_or_agents_and_no_secrets(self):
        result=self.collect()
        self.assertEqual(result['agents'],[])
        self.assertEqual(len(result['providers']),2)
        self.assertIsNone(result['providers'][0]['remaining'])
        self.assertNotIn('DO-NOT-DISPLAY',repr(result))
        self.assertEqual(result['connection'],'Host stopped')

    def test_historical_quota_is_labeled_and_unknowns_preserved(self):
        history={'error':False,'providers':[dict(provider='codex',today=None,daily=[None]*7,
            quota=dict(usedPercent=71,windowMinutes=10080,ageMinutes=3),agents={'sessions':None})]}
        result=self.collect(history=history)
        row=result['providers'][0]
        self.assertEqual(row['remaining'],29)
        self.assertIn('3m ago',row['quota_note'])
        self.assertIn('Recorded',row['quota_note'])
        self.assertIsNone(result['history'][0]['today'])

    def test_expired_agent_state_is_not_current_and_identity_preserved(self):
        result=self.collect(agents=[dict(provider='codex',id='ab12cd34',state='WORKING',
                                        observedAgeSeconds=45,elapsedSeconds=77)])
        self.assertEqual(result['agents'][0]['state'],'Last: WORKING')
        self.assertEqual(result['agents'][0]['id'],'ab12cd34')
        self.assertEqual(result['agents'][0]['elapsed'],77)

    def test_bad_configuration_is_actionable_without_exception_text(self):
        with patch.object(data,'local_config',side_effect=ValueError('DO-NOT-DISPLAY')):
            result=data.read_dashboard(self.root,now=1000)
        self.assertIn('configuration',result['error'].lower())
        self.assertNotIn('DO-NOT-DISPLAY',repr(result))

    def test_disabled_history_does_not_read_the_database(self):
        self.config['usage_history']=False
        with patch.object(data,'compact_history') as history:
            self.collect()
        history.assert_not_called()


def fixture():
    return dict(connection='USB connected / COM6',error='',providers=[dict(name='Codex',
        remaining=29,quota_note='Recorded 0m ago / 7d window',health='ready')],
        agents=[dict(provider='Codex',id='a91f2c08',state='WORKING',age=2,elapsed=12)],
        history=[dict(provider='Codex',today=None,daily=[None]*7,agents={'sessions':None})],
        device=dict(board='ESP32-P4',port='COM6',firmware='v1.19.1-rc11',age=2),
        settings=dict(board='guition-p4',port='COM6',interval_s=30,usage_history=True),history_enabled=True)


class TerminalUITests(unittest.IsolatedAsyncioTestCase):
    async def test_all_tabs_reload_help_and_quit(self):
        app=TerminalApp(ROOT,reader=lambda _:fixture())
        async with app.run_test(size=(120,40)) as pilot:
            await pilot.pause(.15)
            for key,page in [('2','agents'),('3','history'),('4','device'),('5','settings'),('1','overview')]:
                await pilot.press(key);self.assertEqual(app.query_one(TabbedContent).active,page)
            await pilot.press('r');await pilot.pause(.1)
            await pilot.press('question_mark');await pilot.pause(.1)
            self.assertTrue(app.help_visible)
            await pilot.press('escape');self.assertFalse(app.help_visible)
            await pilot.press('q')

    async def test_small_terminal_scroll_and_plain_text_no_markup(self):
        value=fixture();value['agents'][0]['id']='[red]literal[/red]'
        app=TerminalApp(ROOT,reader=lambda _:value)
        async with app.run_test(size=(60,20)) as pilot:
            await pilot.pause(.15);await pilot.press('2','tab','down','pagedown')
            self.assertEqual(app.query_one(TabbedContent).active,'agents')
            content=app.query_one('#agents-content',Static)
            self.assertIn('[red]literal[/red]',str(content.render()))
            await pilot.resize_terminal(140,45);await pilot.pause(.1)
            self.assertEqual(app.query_one(TabbedContent).active,'agents')

    async def test_slow_reader_does_not_block_quit_or_overlap_reads(self):
        import threading
        began=threading.Event();release=threading.Event();calls=[]
        def slow(_):
            calls.append(1);began.set();release.wait(2);return fixture()
        app=TerminalApp(ROOT,reader=slow)
        try:
            async with app.run_test(size=(100,30)) as pilot:
                await asyncio.to_thread(began.wait,1)
                await pilot.press('r','r','2');self.assertEqual(len(calls),1)
                self.assertEqual(app.query_one(TabbedContent).active,'agents')
                release.set();await pilot.pause(.1)
        finally:release.set()

