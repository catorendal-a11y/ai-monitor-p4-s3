"""AI Monitor terminal companion. Keyboard navigation; existing metadata only."""
import argparse
import asyncio
from pathlib import Path
import sys
from textual.app import App,ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal,VerticalScroll
from textual.widgets import Footer,Static,TabbedContent,TabPane
from host_security import safe_text
from project_version import HOST_VERSION
from terminal_data import default_root,read_dashboard


def number(value):
    return 'Unknown' if value is None else f'{value:,}'


def duration(value):
    return 'Unknown start' if value is None else f'{value//3600}:{value//60%60:02}:{value%60:02}'


def quota_text(rows):
    lines=['RECORDED PROVIDER QUOTA','']
    for row in rows:
        remaining=row['remaining']
        bar='-'*20 if remaining is None else '#'*round(remaining/5)+'-'*(20-round(remaining/5))
        percent='Unknown' if remaining is None else f'{remaining:g}% left'
        lines.extend([f"{row['name']} / {row['health'].replace('_',' ')}",
                      f'[{bar}]  {percent}',row['quota_note'],''])
    if not rows:lines.append('Select providers in the desktop app.')
    return '\n'.join(lines)


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
    Screen { background: #0c1215; color: #eff5f3; }
    #brand { height: 3; padding: 1 2 0 2; color: #35d07f; text-style: bold; }
    #connection { height: auto; padding: 0 2; color: #a3b2bc; }
    TabbedContent { height: 1fr; }
    Tabs { background: #11191d; }
    Tab.-active { color: #35d07f; text-style: bold; }
    TabPane { padding: 1 2; }
    VerticalScroll { height: 1fr; }
    .panel { border: round #263239; padding: 1 2; height: auto; margin-bottom: 1; }
    #overview-top { height: auto; }
    #quota { width: 2fr; }
    #overview-device { width: 1fr; margin-left: 1; }
    #notice { height: auto; color: #ffcf66; padding: 0 2; }
    #help { display: none; height: auto; padding: 1 2; border: round #35d07f; }
    Footer { background: #11191d; }
    '''
    BINDINGS=[Binding(str(i),f"page('{page}')",page.title(),show=False,priority=True)
              for i,page in enumerate(('overview','agents','history','device','settings'),1)]+[
        Binding('r','reload','Reload',priority=True),Binding('?','help','Help',priority=True),
        Binding('escape','dismiss_help','Close help',show=False),Binding('q','quit','Quit',priority=True)]

    def __init__(self,root,reader=read_dashboard):
        super().__init__();self.root=Path(root);self.reader=reader
        self.reading=False;self.help_visible=False;self.latest=None

    def compose(self)->ComposeResult:
        yield Static(f'AI MONITOR  |  NOVA / Terminal  {HOST_VERSION}',id='brand',markup=False)
        yield Static('Reading local status...',id='connection',markup=False)
        with TabbedContent(id='pages'):
            with TabPane('1 Overview',id='overview'):
                with VerticalScroll():
                    with Horizontal(id='overview-top'):
                        yield Static('Loading...',id='quota',classes='panel',markup=False)
                        yield Static('DEVICE',id='overview-device',classes='panel',markup=False)
                    yield Static('OBSERVED AGENTS',id='overview-agents',classes='panel',markup=False)
            with TabPane('2 Agents',id='agents'):
                with VerticalScroll():yield Static('',id='agents-content',classes='panel',markup=False)
            with TabPane('3 History',id='history'):
                with VerticalScroll():yield Static('',id='history-content',classes='panel',markup=False)
            with TabPane('4 Device',id='device'):
                with VerticalScroll():yield Static('',id='device-content',classes='panel',markup=False)
            with TabPane('5 Settings',id='settings'):
                with VerticalScroll():yield Static('',id='settings-content',classes='panel',markup=False)
        yield Static('',id='notice',markup=False)
        yield Static('1–5 Choose page | Tab Move focus | Arrows / PageUp / PageDown Scroll\n'
                     'R Reload local metadata (does not poll providers) | Q Quit\n'
                     'Quota comes from optional local history; its recording age is always shown.\n'
                     'Settings are managed in the existing desktop app. No extra USB connection.',
                     id='help',markup=False)
        yield Footer()

    def on_mount(self):
        self.set_interval(2,self.action_reload);self.action_reload()

    def on_resize(self,event):
        self.query_one('#overview-top').styles.layout='vertical' if event.size.width<90 else 'horizontal'
        self.query_one('#overview-device').styles.width='1fr' if event.size.width>=90 else '100%'
        self.query_one('#overview-device').styles.margin=(0,0,1,1 if event.size.width>=90 else 0)
        self.query_one('#quota').styles.width='2fr' if event.size.width>=90 else '100%'

    def action_page(self,page):
        self.query_one(TabbedContent).active=page

    def action_help(self):
        self.help_visible=not self.help_visible;self.query_one('#help').display=self.help_visible

    def action_dismiss_help(self):
        self.help_visible=False;self.query_one('#help').display=False

    def action_reload(self):
        if not self.reading:
            self.reading=True;self.run_worker(self.read(),name='local-metadata')

    async def read(self):
        try:
            value=await asyncio.to_thread(self.reader,self.root)
            self.latest=value;self.present(value)
        except Exception:
            self.query_one('#notice',Static).update('Local data could not be read. R retries; Q quits.')
        finally:self.reading=False

    def present(self,value):
        def update(selector,text):self.query_one(selector,Static).update(text)
        update('#connection',value['connection']+f"  |  {len(value['agents'])} observed sessions  |  History "+('enabled' if value['history_enabled'] else 'disabled'))
        update('#quota',quota_text(value['providers']))
        agents=agents_text(value['agents']);update('#agents-content',agents);update('#overview-agents',agents)
        device=value['device']
        stamp='Unknown observation age' if device.get('age') is None else f"Observed {device['age']}s ago"
        description='DEVICE\n\n'+f"{device.get('board','Unknown')}\n{device.get('port','Unknown')}\nFirmware {device.get('firmware','Unknown')}\n{stamp}"
        update('#device-content',description+'\n\nStatus comes from the existing host.\nNo second USB connection is opened.')
        update('#overview-device',description+'\n\n  .-----.'+'\n  | ^ ^ |\n  |  _  |\n  `-----\'\n    NOVA')
        lines=['LOCAL HISTORY / TODAY','']
        if not value['history_enabled']:lines.append('History is disabled. Enable it in the desktop app to collect future observations.')
        for row in value['history']:
            metrics=row.get('agents',{})
            lines.extend([row['provider'],f"Tokens: {number(row['today'])}  /  Sessions: {number(metrics.get('sessions'))}",
                f"Observed active time: {duration(metrics.get('activeSeconds'))}",
                'Daily tokens, oldest to today: '+' / '.join(number(n) for n in row['daily']),''])
        lines.append('Unknown gaps remain unknown. Elapsed run time is not active time.')
        update('#history-content','\n'.join(lines))
        settings=['SAVED SETTINGS','']+[f'{key}: {safe_text(item,80)}' for key,item in value['settings'].items()]
        settings+=['','Manage configuration, credentials and host lifecycle in the desktop app.',
                   'This terminal is a read-only companion. Closing it leaves the host running.']
        update('#settings-content','\n'.join(settings));update('#notice',value['error'])


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
