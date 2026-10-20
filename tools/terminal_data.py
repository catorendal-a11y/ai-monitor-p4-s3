"""Read-only terminal projection of existing local metadata; no serial/model client."""
from pathlib import Path
import os
import sys
import time
from aim_control import local_config,owned_hosts
from host_status import read_status,validate_options
from host_security import safe_text
from provider_catalog import PROVIDERS
from device_history import compact_history
from live_events import live_agents
from session_identity import identity


def default_root():
    """Reuse the installed application when the terminal is a standalone companion."""
    own=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
    installed=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Programs/AI Monitor'
    if getattr(sys,'frozen',False) and (own/'tools/aim_host.json').is_file():return own
    return own if (own/'tools/aim_host.json').is_file() else installed if (installed/'tools/aim_host.json').is_file() else own


def window_text(minutes):
    if not minutes:return 'unknown'
    return f'{minutes//1440}d' if minutes%1440==0 else f'{minutes//60}h' if minutes%60==0 else f'{minutes}m'


def age_text(seconds):
    if seconds<60:return f'{seconds}s'
    if seconds<3600:return f'{seconds//60}m'
    if seconds<86400:return f'{seconds//3600}h {seconds//60%60:02}m'
    return f'{seconds//86400}d {seconds//3600%24}h'


def live_windows(entry,now):
    """Host-validated quota copy; reset countdowns are derived from the saved deadline."""
    if not isinstance(entry,dict):return []
    return [dict(title=window['title'],remaining=window['remaining'],window=window_text(window['window']),
                 reset_in=None if window['reset_at'] is None else max(0,int(window['reset_at']-now)))
            for window in entry['windows']]


def read_dashboard(root,now=None):
    root=Path(root);now=time.time() if now is None else now
    result=dict(connection='Host stopped',error='',providers=[],agents=[],history=[],device={},
                settings={},history_enabled=False,running=False)
    try:
        config=local_config(root);validate_options(config)
    except (OSError,ValueError,TypeError):
        result['error']='Local configuration unavailable. Use Settings / Recover invalid settings.'
        return result
    providers=config['providers'];enabled=config.get('usage_history',False)
    result['history_enabled']=enabled
    result['settings']={key:config.get(key) for key in ('board','port','interval_s','token_poll_s','usage_history')}
    result['settings'].update(keep_host_on_close=config.get('keep_host_on_close',True),start_host_on_open=config.get('start_host_on_open',False),
                              start_host_at_login=config.get('start_host_at_login',False))
    processes=owned_hosts(root)
    result['running']=bool(processes)
    health=read_status(root,{p.pid for p in processes}) or {}
    if health:
        result['connection']=safe_text(health.get('state','unknown').replace('_',' ').title()+' / '+health.get('port',''),80)
    elif processes:result['connection']='Host running / status unconfirmed'
    hardware=health.get('hardware',{})
    result['device']=dict(board=safe_text(health.get('board',config.get('board','Unknown')),50),
        port=safe_text(health.get('port',config.get('port','Unknown')),30),
        firmware=safe_text(hardware.get('firmwareVersion','Unknown'),40),
        connected=health.get('state')=='connected',
        sync_age=max(0,int(now-health['updated_at'])) if 'updated_at' in health else None,
        age=max(0,int(now-health['hardware_at'])) if 'hardware_at' in health else None)
    history=compact_history(root/'tools/activity',providers,True,now=now) if enabled else {'providers':[],'error':False}
    if history.get('error'):result['error']='History unavailable. Values remain unknown.'
    records={item['provider']:item for item in history['providers']}
    live_quota=health.get('quota',{})
    for provider in providers:
        record=records.get(provider,{})
        state=health.get('providers',{}).get(provider,'unconfirmed')
        windows=live_windows(live_quota.get(provider),now)
        remaining=None;source=None
        if windows:
            # The most constrained window decides whether work can continue.
            remaining=min(window['remaining'] for window in windows);source='live'
            age=max(0,int(now-live_quota[provider]['at']))
            note=('Last known '+age_text(age)+' ago; provider unavailable' if state=='unavailable'
                  else 'Live / updated '+age_text(age)+' ago')
        elif record.get('quota'):
            quota=record['quota'];source='history'
            remaining=round(100-quota['usedPercent'],1)
            note=f"Recorded {quota['ageMinutes']}m ago / {window_text(quota['windowMinutes'])} window"
        elif not result['running']:note='Start the host to read quota'
        else:note='Waiting for the first provider update' if state=='unconfirmed' else 'No quota reported'
        result['providers'].append(dict(name=PROVIDERS[provider][0],remaining=remaining,quota_note=note,
            health=state,windows=windows,source=source))
        result['history'].append(dict(provider=PROVIDERS[provider][0],today=record.get('today'),
            daily=record.get('daily',[None]*7),agents=record.get('agents',{})))
    for row in live_agents(root/'tools/activity',providers,now=now):
        age=row.get('observedAgeSeconds',0)
        name,hue=identity(row['id'])
        result['agents'].append(dict(provider=PROVIDERS[row['provider']][0],id=row['id'][-8:],name=name,hue=hue,
            state=('Last: ' if age>=30 else '')+row['state'].replace('_',' '),age=age,
            elapsed=row.get('elapsedSeconds')))
    return result
