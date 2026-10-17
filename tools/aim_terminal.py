"""AI Monitor terminal application with the shared desktop operations."""
import argparse
import asyncio
from pathlib import Path
import sys
import json
from textual.app import App,ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal,Vertical,VerticalScroll
from textual.widgets import Button,Static,TabbedContent,TabPane
from host_security import safe_text
from terminal_data import default_root,read_dashboard
from terminal_actions import TerminalActions
from terminal_forms import ActionForm,ResultScreen,settings_form,settings_values
from terminal_presentation import provider_table,agent_table,device_panel,nova_panel,history_panel


def number(value):
    return 'Unknown' if value is None else f'{value:,}'


def duration(value):
    return 'Unknown' if value is None else f'{value//3600}:{value//60%60:02}:{value%60:02}'


def agents_text(rows):
    lines=['OBSERVED AGENTS','']
    if not rows:lines.extend(['No recent observed sessions.','Check event observers in the desktop app.'])
    for row in rows:
        lines.extend([f"{row['provider']} / {row['id']}  |  {row['state']}",
                      f"Event {row['age']}s ago  |  Elapsed {duration(row['elapsed'])}",''])
    return '\n'.join(lines)


class TerminalApp(App):
    TITLE='AI Monitor — Terminal'
    CSS='''
    Screen { background: #101519; color: #eff5f3; }
    #brand { height: 3; padding: 1 2 0 2; color: #95ffc2; text-style: bold; }
    #connection { height: 1; width: 1fr; color: #95ffc2; }
    #statusbar { height: 2; border-top: solid #87929a; padding: 0 2; }
    #shortcuts { height: 1; width: auto; color: #a5adb7; }
    TabbedContent { height: 1fr; }
    Tabs { background: #101519; height: 3; border-bottom: solid #87929a; }
    Tab { padding: 0 2; height: 2; color: #a5adb7; }
    Tab.-active { background: #95ffc2; color: #101519; text-style: bold; }
    Underline { display: none; }
    TabPane { padding: 1 2; }
    VerticalScroll { height: 1fr; }
    .panel { border: round #526572; background: #151e25; padding: 0 1; height: auto; margin-bottom: 1; }
    #quota-wrap { border-top: solid #95ffc2; }
    #overview-device { border-top: solid #76c9ff; }
    #nova-panel { border: round #95ffc2; background: #13231f; }
    #overview-agents, #agents-content { border-top: solid #b4a0ff; }
    #history-content { border-top: solid #76c9ff; }
    Button { background: #1d2d37; border: tall #526572; }
    Button:hover { background: #2c414d; }
    Button:focus { border: tall #95ffc2; text-style: bold; }
    #overview-top { height: 18; margin-bottom: 1; }
    #quota-wrap { width: 2fr; height: 1fr; margin-right: 1; margin-bottom: 0; }
    #quota { height: auto; }
    #overview-side { width: 1fr; height: 1fr; }
    #overview-device { height: 9; }
    #nova-panel { height: 8; margin-bottom: 0; }
    #overview-agents { min-height: 8; }
    #notice { height: auto; max-height: 3; color: #ffcf66; padding: 0 2; }
    #help { display: none; height: auto; padding: 1 2; border: round #35d07f; }
    .actions { layout: horizontal; height: auto; margin-bottom: 1; }
    .actions Button { margin-right: 1; min-width: 12; }
    '''
    ENABLE_COMMAND_PALETTE=False
    BINDINGS=[Binding(str(i),f"page('{page}')",page.title(),show=False,priority=True)
              for i,page in enumerate(('overview','agents','history','device','settings'),1)]+[
        Binding('r','reload','Reload',priority=True),Binding('?','help','Help',priority=True),
        Binding('escape','dismiss_help','Close help',show=False),Binding('q','quit','Quit',priority=True)]

    def __init__(self,root,reader=read_dashboard,service=None):
        super().__init__();self.root=Path(root);self.reader=reader
        self.reading=False;self.help_visible=False;self.latest=None
        self.operation_busy=False;self.generation=0
        self.auto_start_checked=False;self.quit_after_stop=False
        self.last_action_notice=''
        self.service=service or TerminalActions(self.root,comparison=self.compare_from_worker)

    def actions(self,*items):
        # One row per two actions keeps keyboard targets usable in narrow windows.
        for index in range(0,len(items),2):
            with Horizontal(classes='actions'):
                for caption,identifier in items[index:index+2]:yield Button(caption,id=identifier)

    def compose(self)->ComposeResult:
        yield Static('AI MONITOR  |  NOVA / USB companion',id='brand',markup=False)
        with TabbedContent(id='pages'):
            with TabPane('1 Overview',id='overview'):
                with VerticalScroll():
                    with Horizontal(id='overview-top'):
                        with VerticalScroll(id='quota-wrap',classes='panel'):
                            yield Static('Loading...',id='quota',markup=False)
                        with Vertical(id='overview-side'):
                            yield Static('DEVICE',id='overview-device',classes='panel',markup=False)
                            yield Static('NOVA',id='nova-panel',classes='panel',markup=False)
                    yield Static('OBSERVED AGENTS',id='overview-agents',classes='panel',markup=False)
            with TabPane('2 Agents',id='agents'):
                with VerticalScroll():
                    yield from self.actions(('Check AI setup','setup_report'),('Provider events','events'),('Claude quota link','quota-link'),('Codex sign-in','codex_setup'))
                    yield Static('',id='agents-table',classes='panel',markup=False)
                    yield Static('',id='agents-content',classes='panel',markup=False)
            with TabPane('3 History',id='history'):
                with VerticalScroll():
                    yield from self.actions(('7 / 30 day report','history-report'),('Export CSV','export-history'),('Clear history','clear_history'),('Diagnostic export','diagnostics'))
                    yield Static('',id='history-content',classes='panel',markup=False)
            with TabPane('4 Device',id='device'):
                with VerticalScroll():
                    yield from self.actions(('Rescan ports','ports'),('Check USB','check_usb'),('Firmware','firmware'),('Device screen','screen'),('Companion packs','packs'),('Connect PC','connect_pc'))
                    yield Static('',id='device-content',classes='panel',markup=False)
            with TabPane('5 Settings',id='settings'):
                with VerticalScroll():
                    yield from self.actions(('Start host','start'),('Stop host','stop'))
                    yield from self.actions(('Edit settings','settings'),('Recent host log','log'),('Recover invalid settings','recover'))
                    yield Static('',id='settings-content',classes='panel',markup=False)
        yield Static('',id='notice',markup=False)
        yield Static('1–5 Choose page | Tab Move focus | Arrows / PageUp / PageDown Scroll\n'
                     'R Reload local metadata (does not poll providers) | Q Quit\n'
                     'Quota comes from optional local history; its recording age is always shown.\n'
                     'Tab / Enter activate controls. Escape cancels forms. Settings and host controls use the shared backend.',
                     id='help',markup=False)
        with Horizontal(id='statusbar'):
            yield Static('Reading local status...',id='connection',markup=False)
            yield Static('Tab Navigate  Enter Open  R Reload  ? Help  Q Quit',id='shortcuts',markup=False)

    def on_mount(self):
        self.apply_width(self.size.width)
        self.set_interval(2,self.action_reload);self.action_reload()

    def on_resize(self,event):
        if not self.ready():return
        self.apply_width(event.size.width)

    def apply_width(self,width):
        main=self.screen_stack[0]
        main.query_one('#overview-top').styles.layout='vertical' if width<90 else 'horizontal'
        main.query_one('#overview-top').styles.height=18 if width>=90 else 'auto'
        main.query_one('#overview-side').styles.width='1fr' if width>=90 else '100%'
        main.query_one('#overview-side').styles.height='1fr' if width>=90 else 'auto'
        main.query_one('#quota-wrap').styles.width='2fr' if width>=90 else '100%'
        main.query_one('#quota-wrap').styles.height='1fr' if width>=90 else 'auto'
        main.query_one('#quota-wrap').styles.margin=(0,1 if width>=90 else 0,0 if width>=90 else 1,0)
        main.query_one('#shortcuts').display=width>=100
        if self.latest:main.query_one('#quota',Static).update(provider_table(self.latest['providers'],compact=width<120))

    def check_action(self,action,parameters):
        # Global shortcuts must never steal digits, q, r or ? from form inputs.
        return not (len(self.screen_stack)>1 and action in ('page','reload','help','dismiss_help','quit'))

    def action_quit(self):
        if self.operation_busy:
            self.screen_stack[0].query_one('#notice',Static).update('Wait for the active operation to finish. No write is interrupted.')
        elif self.latest and self.latest.get('running') and self.latest['settings'].get('keep_host_on_close') is False:
            self.quit_after_stop=True;self.dispatch('stop',{})
        else:self.exit()

    def action_page(self,page):
        self.query_one(TabbedContent).active=page

    def action_help(self):
        self.help_visible=not self.help_visible;self.query_one('#help').display=self.help_visible

    def action_dismiss_help(self):
        self.help_visible=False;self.query_one('#help').display=False

    def action_reload(self):
        if not self.reading and not self.operation_busy:
            self.reading=True;self.run_worker(self.read(self.generation),name='local-metadata')

    def ready(self):
        return bool(self.screen_stack and self.screen_stack[0].query('#notice'))

    async def read(self,generation):
        try:
            if self.operation_busy:return
            value=await asyncio.to_thread(self.reader,self.root)
            if generation==self.generation and self.ready():
                self.latest=value;self.present(value)
                if not self.auto_start_checked and not value['error']:
                    self.auto_start_checked=True
                    if value['settings'].get('start_host_on_open') is True and not value.get('running'):
                        self.dispatch('start',{})
        except Exception:
            if generation==self.generation and self.ready():self.screen_stack[0].query_one('#notice',Static).update('Local data could not be read. R retries; Q quits.')
        finally:self.reading=False

    def present(self,value):
        def update(selector,text):self.screen_stack[0].query_one(selector,Static).update(text)
        if not self.operation_busy:
            self.screen_stack[0].query_one('Button#start').disabled=value.get('running',False)
            self.screen_stack[0].query_one('Button#stop').disabled=not value.get('running',False)
        count=len(value['agents'])
        update('#connection',value['connection']+f"  |  {count} observed session"+('' if count==1 else 's')+'  |  History '+('enabled' if value['history_enabled'] else 'disabled'))
        update('#quota',provider_table(value['providers'],compact=self.size.width<120))
        agents=agents_text(value['agents'])
        update('#agents-content',agents)
        update('#agents-table',agent_table(value['agents']))
        update('#overview-agents',agent_table(value['agents']))
        device=value['device']
        stamp='Unknown observation age' if device.get('age') is None else f"Observed {device['age']}s ago"
        description='DEVICE\n\n'+f"{device.get('board','Unknown')}\n{device.get('port','Unknown')}\nFirmware {device.get('firmware','Unknown')}\n{stamp}"
        update('#device-content',description+'\n\nStatus comes from the existing host.\nNo second USB connection is opened.')
        update('#overview-device',device_panel(device,value['connection']))
        update('#nova-panel',nova_panel(value['agents']))
        update('#history-content',history_panel(value['history'],value['history_enabled']))
        settings=['SAVED SETTINGS','']+[f'{key}: {safe_text(item,80)}' for key,item in value['settings'].items()]
        close_policy='Closing this terminal stops the owned host, following the saved preference.' if value['settings'].get('keep_host_on_close') is False else 'Closing this terminal leaves the host running. Use Stop host to stop it.'
        settings+=['','Use Edit settings to configure board, providers, credentials and collection preferences.',close_policy]
        update('#settings-content','\n'.join(settings));update('#notice',value['error'] or self.last_action_notice)

    def form(self,title,fields,action,note='',confirm=None):
        self.push_screen(ActionForm(title,fields,note,confirm),lambda values:self.dispatch(action,values) if values is not None else None)

    def on_button_pressed(self,event):
        if self.operation_busy:return
        action=event.button.id
        if action=='events':
            self.form('PROVIDER EVENT OBSERVERS',[
                ('provider','Provider','select',None,[(name,key) for key,(name,_,_) in __import__('provider_catalog').PROVIDERS.items() if key in ('codex','claude','zcode')]),
                ('remove','Remove only this installation\'s observer','bool',False,None)],'event-change',
                'Observers record state and hashed IDs only. They never approve tools. Review/trust Codex hooks and restart provider sessions after linking.',confirm='LINK')
        elif action=='quota-link':
            self.form('CLAUDE QUOTA BRIDGE',[('remove','Remove this installation\'s quota bridge','bool',False,None)],'quota-change',
                'Uses the official numeric statusline. Existing custom statuslines are preserved.',confirm='LINK')
        elif action=='firmware':
            self.form('FIRMWARE', [('kind','Operation','select','update',[('Application update / preserve settings','update'),('First installation / factory image','install')])], 'prepare_flash',
                'Files and port are verified first. Writing requires a second confirmation with the exact board and port.')
        elif action in ('history-report','export-history'):
            fields=[('days','Local calendar days','select',7,[('7 days',7),('30 days',30)])]
            if action=='export-history':fields.append(('path','New CSV output file','text','',None))
            self.form('LOCAL HISTORY',fields,'history_report' if action=='history-report' else 'export_history')
        elif action=='diagnostics':self.form('EXPORT DIAGNOSTICS',[('path','New JSON output file','text','',None)],action)
        elif action in ('clear_history','recover','codex_setup','connect_pc'):
            words={'clear_history':'CLEAR','recover':'RESET','codex_setup':'SETUP','connect_pc':'CONNECT'}
            notes={'clear_history':'Clear local history after stopping the owned writer. Collection preferences are retained.',
                   'recover':'Recover only invalid settings; preserve a private backup of the original.',
                   'codex_setup':'Open official installation/sign-in in a separate terminal. No model turn is started.',
                   'connect_pc':'Open MENU > SETTINGS > CONNECT PC on the physical display and tap CONNECT PC there. This operation pauses and restores the host. Approval stays disabled.'}
            self.form(action.replace('_',' ').upper(),[],action,notes[action],confirm=words[action])
        else:self.dispatch(action,{})

    def dispatch(self,action,values):
        if self.operation_busy:return
        if action=='event-change':action='unlink_events' if values.pop('remove') else 'link_events'
        elif action=='quota-change':action='unlink_quota' if values.pop('remove') else 'link_quota';values['provider']='claude'
        elif action=='pack-change':action=values.pop('operation')
        self.operation_busy=True;self.generation+=1
        if action=='clear_history':
            self.latest=None;self.screen_stack[0].query_one('#history-content',Static).update('Clearing history; previous values are no longer displayed.')
        for button in self.screen_stack[0].query(Button):button.disabled=True
        self.screen_stack[0].query_one('#notice',Static).update('Working: '+action.replace('_',' '))
        self.run_worker(self.perform(action,values),name='terminal-action')

    async def perform(self,action,values):
        preferences={key:values.get('options',{}).get(key) for key in ('keep_host_on_close','start_host_on_open')} if action=='save' else {}
        try:
            result=await asyncio.to_thread(self.service.execute,action,values)
        except Exception:
            self.quit_after_stop=False
            self.last_action_notice='Action failed. Check settings, selection and connection; private details were not printed.'
            if self.ready():self.screen_stack[0].query_one('#notice',Static).update(self.last_action_notice)
            return
        finally:
            values.clear();self.operation_busy=False
            for button in self.screen_stack[0].query(Button):button.disabled=False
        if not self.ready():return
        if self.latest:
            if action in ('start','stop'):self.latest['running']=action=='start'
            for key,value in preferences.items():
                if type(value) is bool:self.latest['settings'][key]=value
        if action=='stop' and self.quit_after_stop:
            self.exit();return
        self.last_action_notice=(result.get('output') or 'Action completed.').splitlines()[-1]
        self.screen_stack[0].query_one('#notice',Static).update(self.last_action_notice)
        if action=='settings':
            def save(fields):
                if fields is None:return
                try:prepared=settings_values(fields)
                except (ValueError,TypeError,KeyError):
                    self.screen_stack[0].query_one('#notice',Static).update('Invalid numeric settings; nothing was saved.');return
                self.dispatch('save',prepared)
            self.push_screen(settings_form(result['settings']),save)
        elif action=='prepare_flash':
            prepared=result['prepared']
            self.form('CONFIRM FIRMWARE WRITE',[],'flash',
                f"Board: {prepared['board']} / Port: {prepared['port']} / Operation: {prepared['kind']}\nThe selected host will stop. Keep USB connected.",confirm='FLASH')
        elif action in ('packs','import_pack','select_pack','builtin','remove_pack'):
            self.show_packs(result)
        elif action=='screen':
            self.push_screen(ResultScreen('DEVICE SCREEN / READ ONLY',screen_text(result['pixels'],self.size.width,self.size.height)))
        elif any(key!='output' for key in result) or result.get('output'):
            content=result.get('output','')
            if len(result)>1:content+='\n'+json.dumps({key:value for key,value in result.items() if key!='output'},indent=2)
            self.push_screen(ResultScreen(action.replace('_',' ').upper(),content[:65536]))
        self.action_reload()

    def show_packs(self,result):
        rows=result['packs'];choices=[(row['name'],row['id']) for row in rows]
        self.form('COMPANION PACKS',[
            ('operation','Action','select','builtin',[('Use built-in NOVA / ORBIT','builtin'),('Use selected pack','select_pack'),('Import and use pack','import_pack'),('Remove unused pack','remove_pack')]),
            ('id','Saved pack','select',result['selected'] if any(key==result['selected'] for _,key in choices) else None,choices),
            ('path','Pack archive path (for import)','text','',None),
            ('confirm','Type IMPORT for import or REMOVE for removal','text','',None)],'pack-change',
            'Activation is performed by the existing serial owner. Selection is not proof of activation.\n'+result.get('activation',''))

    def compare_from_worker(self,prompt):
        def present():
            form=ActionForm('COMPARE WITH PHYSICAL DISPLAY',[],
                'Code: '+prompt.code+'\nCompare every group and hold HOLD TO CONFIRM on the display for 1.8 seconds. Cancel if any group differs.',confirm='MATCH')
            timer=self.set_timer(45,lambda: form.action_cancel() if self.screen is form else prompt.decide(False))
            def decide(values):timer.stop();prompt.decide(values is not None and not prompt.cancelled)
            self.push_screen(form,decide)
        self.call_from_thread(present)


def screen_text(pixels,width,height):
    from rich.text import Text
    from rich.style import Style
    if len(pixels)!=800*480*2:raise ValueError('Unexpected screen dimensions')
    columns=max(8,min(100,width-10));rows=max(4,min(35,height-10));text=Text()
    def color(x,y):
        offset=(y*800+x)*2;value=pixels[offset]|pixels[offset+1]<<8
        return f'rgb({((value>>11)&31)*255//31},{((value>>5)&63)*255//63},{(value&31)*255//31})'
    for y in range(rows):
        for x in range(columns):
            text.append('▀',Style(color=color(x*800//columns,y*480//rows),
                                  bgcolor=color(x*800//columns,min(479,(y*2+1)*480//(rows*2)))))
        text.append('\n')
    return text


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,help='Existing AI Monitor application directory')
    parser.add_argument('--check',action='store_true',help='Headless UI smoke check using synthetic data')
    args=parser.parse_args(argv)
    if args.check:
        async def check():
            value=dict(connection='Synthetic check',error='',providers=[],agents=[],history=[],device={},settings={},history_enabled=False)
            app=TerminalApp(Path('.'),reader=lambda _:value)
            async with app.run_test(size=(100,35)) as pilot:
                await pilot.pause(.1);await pilot.press('2','3','4','5','1','q')
        asyncio.run(check());print('Terminal UI check passed.');return 0
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print('Open AI Monitor Terminal in an interactive terminal (or use --check).');return 2
    TerminalApp(args.root.resolve() if args.root else default_root()).run();return 0


if __name__=='__main__':
    raise SystemExit(main())
