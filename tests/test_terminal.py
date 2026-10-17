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
    def test_graphical_quota_and_state_keep_textual_meaning(self):
        from rich.console import Console
        from io import StringIO
        from terminal_presentation import provider_table,agent_table,nova_panel
        stream=StringIO();console=Console(file=stream,width=100,color_system=None)
        console.print(provider_table([dict(name='Codex',remaining=25,health='ready',quota_note='Recorded 2m ago / 7d window')]))
        console.print(agent_table([dict(provider='Codex',id='test',state='WAITING',age=4,elapsed=None)]))
        console.print(nova_panel([dict(state='UNKNOWN')]))
        output=stream.getvalue()
        self.assertIn('█',output);self.assertIn('25% left',output)
        self.assertIn('● WAITING',output);self.assertIn('Unknown',output)
        self.assertNotIn('Ready',output)

    def test_history_graph_preserves_unknown_gaps_and_disabled_state(self):
        from rich.console import Console
        from io import StringIO
        from terminal_presentation import history_panel
        stream=StringIO();console=Console(file=stream,width=100,color_system=None)
        console.print(history_panel([dict(provider='Codex',today=None,daily=[0,None,8,16],agents={})],True))
        text=stream.getvalue();self.assertIn('·',text);self.assertIn('█',text)
        self.assertIn('Unknown',text);self.assertIn('gap',text)
        stream.seek(0);stream.truncate()
        console.print(history_panel([],False));self.assertIn('disabled',stream.getvalue())

    def test_reference_tables_keep_activity_only_and_old_states_truthful(self):
        from rich.console import Console
        from io import StringIO
        from terminal_presentation import provider_table,nova_panel,agent_table
        stream=StringIO();console=Console(file=stream,width=100,color_system=None)
        console.print(provider_table([dict(name='Claude Code',remaining=None,health='activity_only',quota_note='No recorded quota')]))
        text=stream.getvalue();self.assertIn('Activity only',text);self.assertIn('Quota unavailable',text)
        self.assertNotIn('% left',text)
        stream.seek(0);stream.truncate()
        rows=[dict(provider='Codex',id='test',state='Last: WORKING',age=45,elapsed=None)]
        console.print(nova_panel(rows));console.print(agent_table(rows))
        self.assertIn('No fresh events',stream.getvalue());self.assertIn('Last: WORKING',stream.getvalue())

    def test_extra_provider_rows_remain_scrollable_in_reference_layout(self):
        # Renderable data keeps every selection; the fixed overview panel scrolls its content.
        from rich.console import Console
        from io import StringIO
        from terminal_presentation import provider_table
        rows=[dict(name='Provider '+str(i),remaining=i*10,health='ready',quota_note='Recorded 1m ago / 5h window') for i in range(8)]
        stream=StringIO();Console(file=stream,width=70).print(provider_table(rows))
        self.assertIn('Provider 7',stream.getvalue())
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
        with patch.object(data,'compact_history') as history,patch.object(data,'local_config',return_value=self.config),\
             patch.object(data,'owned_hosts',return_value=[]),patch.object(data,'read_status',return_value=None),\
             patch.object(data,'live_agents',return_value=[]):
            data.read_dashboard(self.root,now=1000)
        history.assert_not_called()


def fixture():
    return dict(connection='USB connected / COM6',error='',providers=[dict(name='Codex',
        remaining=29,quota_note='Recorded 0m ago / 7d window',health='ready')],
        agents=[dict(provider='Codex',id='a91f2c08',state='WORKING',age=2,elapsed=12)],
        history=[dict(provider='Codex',today=None,daily=[None]*7,agents={'sessions':None})],
        device=dict(board='ESP32-P4',port='COM6',firmware='v1.19.1-rc11',age=2),
        settings=dict(board='guition-p4',port='COM6',interval_s=30,usage_history=True),history_enabled=True)


async def mounted_widget(pilot,selector):
    for _ in range(60):
        matches=pilot.app.screen.query(selector)
        if matches:return matches.first()
        await pilot.pause(.05)
    raise AssertionError('Widget did not mount: '+selector)


class TerminalUITests(unittest.IsolatedAsyncioTestCase):
    async def test_overview_agents_fit_common_window_height(self):
        value=fixture()
        value['providers']*=3
        value['agents'].append(dict(provider='Z Code',id='second-agent',state='WAITING',age=2,elapsed=10))
        app=TerminalApp(ROOT,reader=lambda _:value)
        async with app.run_test(size=(120,30)) as pilot:
            await pilot.pause(.2)
            main=app.screen_stack[0]
            agents=main.query_one('#overview-agents')
            self.assertLessEqual(agents.region.bottom,main.query_one('#statusbar').region.y)
            self.assertGreaterEqual(agents.region.height,7)
            self.assertIn('second-agent',app.export_screenshot())
            await pilot.resize_terminal(120,40);await pilot.pause(.1)
            self.assertLessEqual(agents.region.bottom,main.query_one('#statusbar').region.y)
            await pilot.resize_terminal(120,30);await pilot.pause(.1)
            self.assertLessEqual(agents.region.bottom,main.query_one('#statusbar').region.y)
            self.assertIn('second-agent',app.export_screenshot())

    async def test_invalid_settings_keep_draft_and_focus_field_until_corrected(self):
        from terminal_forms import settings_form
        from textual.widgets import Input,Select,Switch
        app=TerminalApp(ROOT,reader=lambda _:fixture())
        submitted=[]
        async with app.run_test(size=(100,38)) as pilot:
            await pilot.pause(.1)
            form=settings_form(dict(board='guition-p4',port='COM6',interval_s=30,providers=['codex']))
            app.push_screen(form,submitted.append);await pilot.pause(.1)
            key=form.query_one('#field-key',Input);key.value='DRAFT_SECRET'
            cases=[('interval','abc','15'),('interval','241','15'),
                   ('option-reconnect_s','1','2'),('port','bad port','auto')]
            for name,bad,good in cases:
                field=form.query_one('#field-'+name,Input);field.value=bad
                form.query_one('#submit').press();await pilot.pause(.1)
                self.assertIs(app.screen,form);self.assertEqual(submitted,[])
                self.assertIs(form.focused,field);self.assertEqual(key.value,'DRAFT_SECRET')
                self.assertIn('Nothing was saved',str(form.query_one('#form-error').render()))
                self.assertNotIn('DRAFT_SECRET',str(form.query_one('#form-error').render()))
                field.value=good
            form.query_one('#field-board',Select).value=Select.NULL
            form.query_one('#submit').press();await pilot.pause(.1)
            self.assertIs(app.screen,form);self.assertIs(form.focused,form.query_one('#field-board'))
            form.query_one('#field-board',Select).value='guition-p4'
            form.query_one('#field-provider-codex',Switch).value=False
            form.query_one('#submit').press();await pilot.pause(.1)
            self.assertIs(app.screen,form);self.assertEqual(submitted,[])
            form.query_one('#field-provider-codex',Switch).value=True
            form.query_one('#submit').press();await pilot.pause(.1)
            self.assertEqual(len(submitted),1);self.assertEqual(submitted[0]['key'],'DRAFT_SECRET')
            self.assertEqual(key.value,'')

    async def test_reference_layout_has_separate_device_robot_tables_and_bottom_status(self):
        from textual.widgets import Static
        app=TerminalApp(ROOT,reader=lambda _:fixture())
        async with app.run_test(size=(120,40)) as pilot:
            await pilot.pause(.2)
            main=app.screen_stack[0]
            self.assertTrue(main.query('#nova-panel'))
            self.assertTrue(main.query('#overview-device'))
            quota=main.query_one('#quota',Static)
            agents=main.query_one('#overview-agents',Static)
            self.assertNotIsInstance(quota.render(),str)
            self.assertIn('Provider',app.export_screenshot())
            self.assertGreater(main.query_one('#connection').region.y,agents.region.y)
    async def test_operation_forms_cancel_without_backend_calls(self):
        from unittest.mock import Mock
        from terminal_forms import ActionForm
        service=Mock();app=TerminalApp(ROOT,reader=lambda _:fixture(),service=service)
        async with app.run_test(size=(120,45)) as pilot:
            await pilot.pause(.1)
            for key,button in [('2','events'),('2','quota-link'),('2','codex_setup'),
                               ('3','history-report'),('3','export-history'),('3','clear_history'),('3','diagnostics'),
                               ('4','connect_pc'),('5','recover')]:
                await pilot.press(key);app.screen.query_one('Button#'+button).press();await pilot.pause(.05)
                self.assertIsInstance(app.screen,ActionForm)
                await pilot.press('escape')
            service.execute.assert_not_called()

    async def test_busy_guard_failure_and_close_policy(self):
        from unittest.mock import Mock
        service=Mock();value=fixture();value['running']=True;value['settings']['keep_host_on_close']=False
        service.execute.side_effect=RuntimeError('SECRET FAILURE')
        app=TerminalApp(ROOT,reader=lambda _:value,service=service)
        async with app.run_test(size=(120,40)) as pilot:
            await pilot.pause(.15)
            app.operation_busy=True;await pilot.press('q');self.assertTrue(app.is_running)
            app.operation_busy=False;await pilot.press('q');await pilot.pause(.15)
            self.assertEqual(service.execute.call_args.args[0],'stop');self.assertTrue(app.is_running)
            self.assertFalse(app.quit_after_stop)
            self.assertNotIn('SECRET',app.last_action_notice)

    async def test_pack_and_pixel_results_are_terminal_native(self):
        from unittest.mock import Mock
        from terminal_forms import ActionForm,ResultScreen
        service=Mock();service.execute.side_effect=[{'packs':[],'selected':'','output':''},
                                                 {'output':'','pixels':bytes(800*480*2)}]
        app=TerminalApp(ROOT,reader=lambda _:fixture(),service=service)
        async with app.run_test(size=(120,45)) as pilot:
            await pilot.pause(.1);await pilot.press('4');app.screen.query_one('Button#packs').press();await pilot.pause(.15)
            self.assertIsInstance(app.screen,ActionForm);await pilot.press('escape')
            app.screen.query_one('Button#screen').press();await pilot.pause(.2)
            self.assertIsInstance(app.screen,ResultScreen);await pilot.press('escape')

    async def test_event_changes_use_explicit_provider_and_confirmation(self):
        from unittest.mock import Mock
        from textual.widgets import Select,Input
        calls=[]
        service=Mock();service.execute.side_effect=lambda name,values:calls.append((name,dict(values))) or {'output':'Linked'}
        app=TerminalApp(ROOT,reader=lambda _:fixture(),service=service)
        async with app.run_test(size=(120,45)) as pilot:
            await pilot.pause(.1);await pilot.press('2');app.screen.query_one('Button#events').press();await pilot.pause(.1)
            app.screen.query_one('#field-provider',Select).value='codex'
            app.screen.query_one('#field-confirm',Input).value='LINK'
            app.screen.query_one('#submit').press();await pilot.pause(.2)
            self.assertEqual(calls[0],('link_events',{'provider':'codex','confirm':'LINK'}))

    async def test_edit_is_cancelable_and_global_shortcuts_do_not_steal_input(self):
        from unittest.mock import Mock
        from terminal_forms import ActionForm
        from textual.widgets import Input
        service=Mock();service.execute.return_value={'settings':dict(board='guition-p4',port='COM6',interval_s=30,providers=['codex'])}
        app=TerminalApp(ROOT,reader=lambda _:fixture(),service=service)
        async with app.run_test(size=(120,45)) as pilot:
            await pilot.pause(.1);await pilot.press('5');await pilot.click('Button#settings');await pilot.pause(.1)
            self.assertIsInstance(app.screen,ActionForm)
            port=await mounted_widget(pilot,'#field-port')
            # Settle modal mount before moving focus with a real click.
            await pilot.pause()
            port.value='';port.scroll_visible(immediate=True)
            await pilot.pause();await pilot.click('#field-port')
            await pilot.pause();self.assertIs(app.screen.focused,port)
            await pilot.press('q','r','1','2','3');self.assertEqual(port.value,'qr123')
            await pilot.press('escape');self.assertEqual(service.execute.call_count,1)

    async def test_settings_submit_uses_shared_save_and_secret_is_not_rendered(self):
        from unittest.mock import Mock
        from terminal_forms import ActionForm,ResultScreen
        from textual.widgets import Input
        captured=[]
        def execute(name,values):
            if name=='settings':return {'settings':dict(board='guition-p4',port='COM6',interval_s=30,providers=['codex'])}
            captured.append(dict(values));return {'output':'Settings saved'}
        service=Mock();service.execute.side_effect=execute
        app=TerminalApp(ROOT,reader=lambda _:fixture(),service=service)
        async with app.run_test(size=(120,45)) as pilot:
            await pilot.pause(.1);await pilot.press('5');await pilot.click('Button#settings');await pilot.pause(.1)
            form=app.screen;key=form.query_one('#field-key',Input);self.assertTrue(key.password)
            key.value='NEW_SECRET'
            form.query_one('#submit').press();await pilot.pause(.2)
            self.assertEqual(service.execute.call_args.args[0],'save')
            self.assertIs(captured[0]['clear_key'],False)
            self.assertEqual(captured[0]['providers'],['codex'])
            self.assertIs(captured[0]['options']['start_host_on_open'],False)
            self.assertIsInstance(app.screen,ResultScreen)
            (await mounted_widget(pilot,'#close')).press();await pilot.pause(.1)
            self.assertEqual(service.execute.call_count,2)

    async def test_firmware_cancel_and_wrong_confirmation_never_write(self):
        from unittest.mock import Mock
        from terminal_forms import ActionForm
        service=Mock();service.execute.return_value={'prepared':dict(board='guition-p4',port='COM6',kind='update'),'output':'Checked'}
        app=TerminalApp(ROOT,reader=lambda _:fixture(),service=service)
        async with app.run_test(size=(120,45)) as pilot:
            await pilot.pause(.1);await pilot.press('4');await pilot.click('Button#firmware');await pilot.pause(.1)
            app.screen.query_one('#submit').press();await pilot.pause(.2)
            self.assertIsInstance(app.screen,ActionForm)
            app.screen.query_one('#submit').press();await pilot.pause(.1)
            self.assertEqual(service.execute.call_count,1)
            await pilot.press('escape');self.assertEqual(service.execute.call_count,1)

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

