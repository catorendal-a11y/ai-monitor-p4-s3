"""Reference-inspired terminal dashboard renderables, using real observed metadata."""
from rich import box
from rich.console import Group
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.align import Align
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
    table=Table(expand=True,box=box.HORIZONTALS,show_edge=False,show_lines=True,
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


def nova_panel(rows,image_rows=6):
    current=[row['state'] for row in rows if not row['state'].startswith('Last:')]
    if any(state in ('ERROR','FAILED') for state in current):mood='Needs attention';color='#ff7777'
    elif any(state in ('WORKING','THINKING','READING','SEARCHING','EDITING','WRITING','RUNNING','BUILDING','TESTING') for state in current):mood='Working';color=GREEN
    elif any(state in ('WAITING','NEEDS ATTENTION') for state in current):mood='Waiting';color='#ffcf66'
    elif current and all(state in ('IDLE','DONE','COMPLETED') for state in current):mood='Idle';color=MUTED
    elif current:mood='Unknown';color=MUTED
    else:mood='No fresh events';color=MUTED
    pose='error' if mood=='Needs attention' else 'attention' if mood=='Waiting' else 'work' if mood=='Working' else 'done'
    caption=Text('NOVA / ',style='bold');caption.append(mood,style=color)
    return Group(Align.center(nova_cells(pose,image_rows)),Align.center(caption))


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
