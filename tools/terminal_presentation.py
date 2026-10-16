"""Reference-inspired terminal dashboard renderables, using real observed metadata."""
from rich import box
from rich.console import Group
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

GREEN='#95ffc2'
MUTED='#a5adb7'
LINE='#65717b'


def heading(title,content):
    return Group(Text(title,style='bold '+GREEN),Rule(style=LINE),content)


def provider_table(rows,compact=False):
    table=Table(expand=True,show_header=False,show_edge=False,box=box.HORIZONTALS,
                border_style=LINE,padding=(1,0 if compact else 1),show_lines=True)
    table.add_column(min_width=8,max_width=12,ratio=2,no_wrap=True,overflow='ellipsis')
    table.add_column(width=13,no_wrap=True)
    table.add_column(width=14 if compact else 22,no_wrap=True)
    table.add_column(min_width=9 if compact else 12,ratio=3,overflow='fold')
    for row in rows:
        name={'ZCode':'Z Code','Claude Code':'Claude'}.get(row['name'],row['name'])
        remaining=row['remaining'];known=remaining is not None
        caption=f'{remaining:g}% left' if known else 'Activity only' if row['health']=='activity_only' else 'Unknown'
        bar=Text('—',style=MUTED)
        if known:
            segments=12 if compact else 20
            filled=max(0,min(segments,round(remaining*segments/100)))
            bar=Text('[');bar.append('#'*filled,style=GREEN);bar.append('-'*(segments-filled),style=MUTED);bar.append(']')
        note=row['quota_note'].replace(' / ','\n')
        if not known and row['health']=='activity_only':note='Quota unavailable'
        label=Text(name,style='bold')
        if row['health'] not in ('ready','activity_only'):label.append('\n'+row['health'].replace('_',' '),style=MUTED)
        table.add_row(label,Text(caption,style=GREEN if known else MUTED),bar,Text(note,style=MUTED))
    if not rows:table.add_row('No providers selected','','','Open Settings')
    return heading('PROVIDER USAGE',table)


def state_color(state):
    if state.startswith('Last:'):return MUTED
    if state in ('WAITING','NEEDS ATTENTION'):return '#ffcf66'
    if state in ('ERROR','FAILED'):return '#ff7777'
    return GREEN if state not in ('UNKNOWN','IDLE') else MUTED


def agent_table(rows):
    table=Table(expand=True,box=box.HORIZONTALS,show_edge=False,show_lines=True,
                border_style=LINE,header_style=MUTED,padding=(0,1))
    for caption,ratio in (('Provider',2),('Session',3),('Last event',3),('State',3)):
        table.add_column(caption,ratio=ratio)
    for row in rows:
        table.add_row(Text(row['provider']),Text(row['id']),Text(f"{row['age']}s ago"),
                      Text(row['state'],style=state_color(row['state'])))
    if not rows:table.add_row('No observed sessions','—','—','Unknown')
    return heading('OBSERVED AGENTS',table)


def device_panel(device,connection):
    board={'guition-p4':'ESP32-P4','waveshare-s3-43':'ESP32-S3'}.get(device.get('board'),device.get('board','Unknown'))
    text=Text(board+'\n',style='bold')
    text.append(device.get('port','Unknown')+' / ')
    connected=device.get('connected',False)
    text.append('Connected' if connected else 'Unconfirmed',style=GREEN if connected else MUTED)
    text.append('\nFirmware : '+device.get('firmware','Unknown'),style=MUTED)
    age=device.get('sync_age')
    text.append('\nLast sync: '+('Unknown' if age is None else f'{age}s ago'),style=MUTED)
    return heading('DEVICE',text)


def nova_panel(rows):
    current=[row['state'] for row in rows if not row['state'].startswith('Last:')]
    if any(state in ('ERROR','FAILED') for state in current):mood='Needs attention';color='#ff7777'
    elif any(state in ('WORKING','THINKING','READING','SEARCHING','EDITING','WRITING','RUNNING','BUILDING','TESTING') for state in current):mood='Working';color=GREEN
    elif any(state in ('WAITING','NEEDS ATTENTION') for state in current):mood='Waiting';color='#ffcf66'
    elif current:mood='Ready';color=MUTED
    else:mood='No fresh events';color=MUTED
    robot="     o\n   .=|=.\n  .----- .\n (| ^ ^ |)\n  | [_] |\n   /   \\"
    table=Table.grid(expand=True,padding=(0,1));table.add_column(width=13);table.add_column(ratio=1)
    caption=Text('\n\nNOVA / ',style='bold');caption.append(mood,style=color)
    table.add_row(Text(robot,style=GREEN),caption)
    return table
