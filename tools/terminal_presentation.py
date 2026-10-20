"""Reference-inspired terminal dashboard renderables, using real observed metadata."""
from rich import box
from rich.console import Group
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.panel import Panel
from terminal_art import nova_cells

GREEN='#95ffc2'
MUTED='#a5adb7'
LINE='#65717b'
AMBER='#ffcf66'
RED='#ff7777'


def heading(title,content):
    return Group(Text(title,style='bold '+GREEN),Rule(style=LINE),content)


def remaining_color(remaining):
    return RED if remaining<=10 else AMBER if remaining<=30 else GREEN


def percent_caption(remaining,stale=False):
    return Text(f'{remaining:g}% left',style=MUTED if stale else 'bold '+remaining_color(remaining))


def quota_bar(remaining,segments,stale=False):
    filled=max(0,min(segments,round(remaining*segments/100)))
    bar=Text();bar.append('█'*filled,style=MUTED if stale else remaining_color(remaining))
    bar.append('░'*(segments-filled),style='#35434d')
    return bar


def countdown(seconds):
    if seconds<=0:return 'now'
    if seconds<3600:return f'{max(1,seconds//60)}m'
    if seconds<86400:return f'{seconds//3600}h {seconds//60%60:02}m'
    return f'{seconds//86400}d {seconds//3600%24}h'


def remaining_color(remaining):
    return RED if remaining<=10 else AMBER if remaining<=30 else GREEN


def percent_caption(remaining,stale=False):
    return Text(f'{remaining:g}% left',style=MUTED if stale else 'bold '+remaining_color(remaining))


def quota_bar(remaining,segments,stale=False):
    filled=max(0,min(segments,round(remaining*segments/100)))
    bar=Text();bar.append('█'*filled,style=MUTED if stale else remaining_color(remaining))
    bar.append('░'*(segments-filled),style='#35434d')
    return bar


def countdown(seconds):
    if seconds<=0:return 'now'
    if seconds<3600:return f'{max(1,seconds//60)}m'
    if seconds<86400:return f'{seconds//3600}h {seconds//60%60:02}m'
    return f'{seconds//86400}d {seconds//3600%24}h'


def provider_table(rows,compact=False,dense=False):
    table=Table(expand=True,show_header=False,show_edge=False,box=box.HORIZONTALS,
                border_style=LINE,padding=(0 if dense else 1,0 if compact else 1),show_lines=True)
    table.add_column(min_width=8,max_width=12,ratio=2,no_wrap=True,overflow='ellipsis')
    table.add_column(width=13,no_wrap=True)
    table.add_column(width=14 if compact else 22,no_wrap=True)
    table.add_column(min_width=9 if compact else 12,ratio=3,overflow='fold')
    for row in rows:
        name={'ZCode':'Z Code','Claude Code':'Claude'}.get(row['name'],row['name'])
        provider_color={'Codex':GREEN,'Z Code':'#76c9ff','Claude':'#c4a7ff'}.get(name,GREEN)
        label=Text(name,style='bold '+provider_color)
        if row['health'] not in ('ready','activity_only'):label.append('\n'+row['health'].replace('_',' '),style=MUTED)
        windows=row.get('windows') or []
        if windows:
            stale=row['health']=='unavailable'
            for index,window in enumerate(windows):
                detail=Text(window['title']+' / '+window['window'],style=MUTED if stale else 'bold')
                if window['reset_in'] is not None:detail.append('\nResets in '+countdown(window['reset_in']),style=MUTED)
                if index==len(windows)-1:detail.append('\n'+row['quota_note'],style=MUTED)
                table.add_row(label if index==0 else Text(''),percent_caption(window['remaining'],stale),
                              quota_bar(window['remaining'],12 if compact else 20,stale),detail)
            continue
        remaining=row['remaining'];known=remaining is not None
        caption=percent_caption(remaining) if known else Text('Activity only' if row['health']=='activity_only' else 'Unknown',style=MUTED)
        bar=quota_bar(remaining,12 if compact else 20) if known else Text('—',style=MUTED)
        note=row['quota_note'].replace(' / ','\n')
        if not known and row['health']=='activity_only':note='Quota unavailable'
        table.add_row(label,caption,bar,Text(note,style=MUTED))
    if not rows:table.add_row('No providers selected','','','Open Settings')
    return heading('PROVIDER USAGE',table)


def state_color(state):
    if state.startswith('Last:'):return MUTED
    if state in ('WAITING','NEEDS ATTENTION'):return '#ffcf66'
    if state in ('ERROR','FAILED'):return '#ff7777'
    return GREEN if state not in ('UNKNOWN','IDLE') else MUTED


# The same 12 hues as the device's session chips (src/ui_agents.cpp hue_colors).
HUE_COLORS=('#F26B6B','#F2A25C','#E8D55B','#A5D96B','#5CD68A','#5CD6C0','#5CC4F2','#6B8CF2','#8F6BF2','#C06BF2','#F26BC8','#F26B94')


def session_cell(row):
    """Recognizable name with its hue; the id tail stays as the exact identity."""
    name=row.get('name')
    if not name:return Text(row['id'])
    cell=Text('● ',style=HUE_COLORS[row.get('hue',0)%len(HUE_COLORS)])
    cell.append(name)
    cell.append(f" {row['id']}",style=MUTED)
    return cell


def agent_table(rows):
    table=Table(expand=True,box=box.HORIZONTALS,show_edge=False,show_lines=False,
                border_style=LINE,header_style=MUTED,padding=(0,1))
    for caption,ratio in (('Provider',2),('Session',4),('Last event',3),('State',3)):
        table.add_column(caption,ratio=ratio)
    for row in rows:
        table.add_row(Text(row['provider']),session_cell(row),Text(f"{row['age']}s ago"),
                      Text('● '+row['state'],style=state_color(row['state'])))
    if not rows:table.add_row('No observed sessions','—','—','Unknown')
    return heading('OBSERVED AGENTS',table)


def device_panel(device,connection):
    board={'guition-p4':'ESP32-P4','waveshare-s3-43':'ESP32-S3'}.get(device.get('board'),device.get('board','Unknown'))
    text=Text(board+' / '+device.get('port','Unknown')+'  ',style='bold')
    connected=device.get('connected',False)
    text.append('● Connected' if connected else '○ Unconfirmed',style=GREEN if connected else MUTED)
    text.append('\nFirmware : '+device.get('firmware','Unknown'),style=MUTED)
    age=device.get('sync_age')
    text.append('\nLast sync: '+('Unknown' if age is None else f'{age}s ago'),style=MUTED)
    return text


def nova_mood(rows):
    """(mood, color, pose) from current, non-expired session states only."""
    current=[row['state'] for row in rows if not row['state'].startswith('Last:')]
    if any(state in ('ERROR','FAILED') for state in current):mood='Needs attention';color='#ff7777'
    elif any(state in ('WORKING','THINKING','READING','SEARCHING','EDITING','WRITING','RUNNING','BUILDING','TESTING') for state in current):mood='Working';color=GREEN
    elif any(state in ('WAITING','NEEDS ATTENTION') for state in current):mood='Waiting';color='#ffcf66'
    elif current and all(state in ('IDLE','DONE','COMPLETED') for state in current):mood='Idle';color=MUTED
    elif current:mood='Unknown';color=MUTED
    else:mood='No fresh events';color=MUTED
    pose='error' if mood=='Needs attention' else 'attention' if mood=='Waiting' else 'work' if mood=='Working' else 'done'
    return mood,color,pose,len(current)


def nova_panel(rows,image_rows=6):
    mood,color,pose,live=nova_mood(rows)
    caption=Text('NOVA / ',style='bold');caption.append(mood,style='bold '+color)
    parts=[Align.center(nova_cells(pose,image_rows)),Align.center(caption)]
    if live:parts.append(Align.center(Text(f"{live} live session{'' if live==1 else 's'}",style=MUTED)))
    return Group(*parts)


def history_panel(rows,enabled):
    """Daily numeric observations only; dots are unknown, not zero-height bars."""
    if not enabled:
        return heading('LOCAL HISTORY / TODAY',Text('History is disabled. Open Settings to collect future observations.',style=MUTED))
    table=Table(expand=True,box=box.SIMPLE,header_style=MUTED,padding=(1,1))
    for name in ('Provider','Today / tokens','Daily trend','Sessions','Active time'):
        table.add_column(name)
    for row in rows:
        values=row['daily'];peak=max((n for n in values if n is not None),default=0)
        graph=Text()
        for value in values:
            glyph='·' if value is None else '▁' if not peak else '▁▂▃▄▅▆▇█'[min(7,round(value*7/peak))]
            graph.append(glyph+' ',style=MUTED if value is None else GREEN)
        metrics=row.get('agents',{});active=metrics.get('activeSeconds')
        table.add_row(Text(row['provider'],style='bold'),
                      'Unknown' if row['today'] is None else f"{row['today']:,}",graph,
                      'Unknown' if metrics.get('sessions') is None else str(metrics['sessions']),
                      'Unknown' if active is None else f'{active//3600}:{active//60%60:02}:{active%60:02}')
    if not rows:table.add_row('No recorded observations','Unknown','·','Unknown','Unknown')
    return heading('LOCAL HISTORY / TODAY',Group(table,Text(
        'Daily trend: oldest → today; scaled per provider. · = unknown gap; ▁ = zero/minimum.\n'
        'Elapsed run time includes waiting and is not active time.',style=MUTED)))


WORKING_STATES=('WORKING','THINKING','READING','SEARCHING','EDITING','WRITING','RUNNING','BUILDING','TESTING')


def clock(seconds):
    return 'Unknown' if seconds is None else f'{seconds//3600}:{seconds//60%60:02}:{seconds%60:02}'


def urgent_quota(providers):
    """(remaining, label) of the lowest live quota window, or None; stale rows never headline."""
    best=None
    for row in providers:
        if row.get('health')=='unavailable':continue
        name={'ZCode':'Z Code','Claude Code':'Claude'}.get(row['name'],row['name'])
        windows=row.get('windows') or ([dict(remaining=row.get('remaining'),title='',window='')] if row.get('remaining') is not None else [])
        for window in windows:
            if window['remaining'] is None:continue
            label=(name+' '+window['title']).strip()
            if best is None or window['remaining']<best[0]:best=(window['remaining'],label)
    return best


def headline(providers,agents):
    """One line that answers "do I need to do anything?": session states, then the tightest quota."""
    current=[row['state'] for row in agents if not row['state'].startswith('Last:')]
    errors=sum(state in ('ERROR','FAILED') for state in current)
    waiting=sum(state in ('WAITING','NEEDS ATTENTION') for state in current)
    working=sum(state in WORKING_STATES for state in current)
    line=Text()
    for count,word,color in ((errors,'error',RED),(waiting,'need you',AMBER),(working,'working',GREEN)):
        if count:line.append(f'● {count} {word}   ',style='bold '+color)
    if not line.plain:line.append('● No active sessions   ',style=MUTED)
    quota=urgent_quota(providers)
    if quota:
        line.append('│  ',style=LINE)
        line.append(f'{quota[0]:g}% left',style='bold '+remaining_color(quota[0]))
        line.append(' · '+quota[1],style=MUTED)
    return line


def session_cards(rows,columns=2):
    """One card per session in the same hue the display uses; waiting sessions stand out."""
    if not rows:
        return Text('No recent observed sessions.\nUse Check AI setup and Provider events on this page.',style=MUTED)
    cards=[]
    for row in rows:
        stale=row['state'].startswith('Last:')
        color=MUTED if stale else state_color(row['state'])
        hue=HUE_COLORS[row.get('hue',0)%len(HUE_COLORS)]
        body=Text('● '+row['state'],style='bold '+color)
        body.append(f"\n{row['provider']} {row['id']}",style=MUTED)
        body.append(f"\nLast event {row['age']}s ago / elapsed {clock(row.get('elapsed'))}",style=MUTED)
        title=Text('● ',style=hue);title.append(row.get('name') or row['id'],style='bold')
        cards.append(Panel(body,title=title,title_align='left',box=box.ROUNDED,
                           border_style=AMBER if color==AMBER else LINE,padding=(0,1)))
    grid=Table.grid(expand=True,padding=(0,1))
    for _ in range(columns):grid.add_column(ratio=1)
    for start in range(0,len(cards),columns):
        line=cards[start:start+columns]
        grid.add_row(*line,*['']*(columns-len(line)))
    return grid


def facts_table(title,pairs):
    """Aligned label/value rows; values may be Text to carry their own color."""
    table=Table.grid(padding=(0,2))
    table.add_column(style=MUTED,no_wrap=True,min_width=22);table.add_column(overflow='fold')
    for label,value in pairs:table.add_row(label,value)
    return heading(title,table)


def settings_panel(settings,close_policy):
    pairs=[]
    for key,value in settings.items():
        shown=Text(('On' if value else 'Off'),style=GREEN if value else MUTED) if isinstance(value,bool) else Text(str(value))
        pairs.append((key[:-2].replace('_',' ')+' (s)' if key.endswith('_s') else key.replace('_',' '),shown))
    return Group(facts_table('SAVED SETTINGS',pairs),Text('\nUse Edit settings to configure board, providers, credentials and collection preferences.\n'+close_policy,style=MUTED))
