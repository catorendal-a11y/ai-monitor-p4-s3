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


def default_root():
    """Reuse the installed application when the terminal is a standalone companion."""
    own=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
    installed=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Programs/AI Monitor'
    if getattr(sys,'frozen',False) and (own/'tools/aim_host.json').is_file():return own
    return own if (own/'tools/aim_host.json').is_file() else installed if (installed/'tools/aim_host.json').is_file() else own


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
    result['settings'].update(keep_host_on_close=config.get('keep_host_on_close',True),start_host_on_open=config.get('start_host_on_open',False))
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
    for provider in providers:
        record=records.get(provider,{})
        quota=record.get('quota')
        remaining=None;note='No recorded quota' if enabled else 'Quota history disabled'
        if quota:
            remaining=round(100-quota['usedPercent'],1)
            minutes=quota['windowMinutes'];window=f'{minutes//1440}d' if minutes and minutes%1440==0 else f'{minutes//60}h' if minutes and minutes%60==0 else f'{minutes}m'
            note=f"Recorded {quota['ageMinutes']}m ago / {window} window"
        result['providers'].append(dict(name=PROVIDERS[provider][0],remaining=remaining,quota_note=note,
            health=health.get('providers',{}).get(provider,'unconfirmed')))
        result['history'].append(dict(provider=PROVIDERS[provider][0],today=record.get('today'),
            daily=record.get('daily',[None]*7),agents=record.get('agents',{})))
    for row in live_agents(root/'tools/activity',providers,now=now):
        age=row.get('observedAgeSeconds',0)
        result['agents'].append(dict(provider=PROVIDERS[row['provider']][0],id=row['id'][-8:],
            state=('Last: ' if age>=30 else '')+row['state'].replace('_',' '),age=age,
            elapsed=row.get('elapsedSeconds')))
    return result
