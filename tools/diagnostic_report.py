"""Bounded diagnostic exports from metadata only; never serialize raw inputs."""
import math
import re
import time

from board_profiles import BOARDS
from host_security import serial_port
from host_status import STATES
from project_version import HOST_VERSION
from provider_catalog import PROVIDERS


def _age(stamp, now):
    if type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0<=stamp<=now:
        return None
    return min(31536000,int(now-stamp))


def _choice(value, choices, fallback='unconfirmed'):
    return value if isinstance(value,str) and value in choices else fallback


def build(config, health, *, now=None):
    now=time.time() if now is None else now
    health=health if isinstance(health,dict) else {}
    board=_choice(config.get('board'),BOARDS)
    try: port=serial_port(config.get('port','auto'))
    except (ValueError,TypeError): port='unconfirmed'
    age=_age(health.get('updated_at'),now)
    current=(age is not None and age<=45 and health.get('board')==board and
             port in ('auto',health.get('port')) and health.get('state') in STATES)
    providers={}
    states=health.get('providers',{})
    for name in PROVIDERS:
        if name not in config.get('providers',[]): continue
        providers[name]={
            'quota_state':_choice(states.get(name),('ready','unavailable','activity_only')) if current else 'unconfirmed',
            'checked_age_s':_age(health.get('provider_updated_at',{}).get(name),now) if current else None,
            'success_age_s':_age(health.get('provider_success_at',{}).get(name),now) if current else None,
            'lifecycle_capability':'observer' if name in ('codex','claude','zcode') else 'unavailable',
        }
    connected=current and health.get('state')=='connected'
    live=health.get('live',{}) if connected else {}
    live_age=_age(live.get('updated_at'),now)
    count=live.get('agent_count')
    live_current=live_age is not None and live_age<=35
    from usage_history import ERRORS
    history=health.get('history',{}) if current else {}
    hardware_age=_age(health.get('hardware_at'),now) if connected else None
    hardware=health.get('hardware',{}) if hardware_age is not None and hardware_age<=45 else {}
    firmware=hardware.get('firmwareVersion')
    if not isinstance(firmware,str) or not re.fullmatch(r'v[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}(?:-rc[0-9]{1,4})?',firmware):firmware=None
    companion=health.get('companion',{}) if connected else {}
    companion_age=_age(companion.get('updated_at'),now)
    return {'schema':1,'app_version':HOST_VERSION,'board':board,'configured_port':port,
        'firmware_version':firmware,'firmware_age_s':hardware_age,
        'host':{'confirmed':current,'state':_choice(health.get('state'),STATES) if current else 'unconfirmed','age_s':age},
        'providers':providers,
        'agent_usb':{'state':_choice(live.get('state'),('unsupported','acknowledged','stale','error')) if live_current else 'unconfirmed',
                     'age_s':live_age,'agent_count':count if live_current and type(count) is int and 0<=count<=8 else None},
        'local_reader':_choice(health.get('local_reader'),('starting','reading','ready','unavailable','stalled')) if current else 'unconfirmed',
        'history':{'collection_enabled':config.get('usage_history') is True,'error':_choice(history.get('error'),ERRORS,None)},
        'companion_state':_choice(companion.get('state'),('active','builtin','overridden','different','installing','unconfirmed')) if companion_age is not None and companion_age<=45 else 'unconfirmed',
        'physical_permissions_enabled':False}


def provider_health_text(config,health,*,now=None):
    report=build(config,health,now=now)
    captions={'ready':'quota received','unavailable':'quota unavailable; check Host log / Provider setup',
              'activity_only':'activity only; no account quota','unconfirmed':'status unconfirmed'}
    lines=[]
    for name,value in report['providers'].items():
        text=PROVIDERS[name][0]+': '+captions[value['quota_state']]
        for field,label in (('checked_age_s','checked'),('success_age_s','last quota')):
            age=value[field]
            if age is not None:text+=f' | {label} {age}s ago'
        lines.append(text)
    lines.append('Mode: observation. Physical approval remains unavailable in this release.')
    return '\n'.join(lines)
