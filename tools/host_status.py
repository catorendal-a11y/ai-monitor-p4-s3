"""Atomic local health snapshots. Never store keys, prompts or RPC replies."""
import json
import math
import os
from pathlib import Path
import tempfile
import time
from host_security import read_local_json, serial_port

STATES = frozenset(('starting', 'waiting_usb', 'connecting', 'connected',
                    'reconnecting', 'stopped', 'error'))
OPTIONS = {'reconnect_s': (2, 60, 5), 'token_poll_s': (2, 15, 2),
           'log_font_size': (10, 18, 10)}
FLAGS = {'start_host_on_open': False, 'keep_host_on_close': True,
         'minimize_to_tray': True, 'close_to_tray': False, 'usage_history': False, 'usb_permissions': False}


def live_status_text(health):
    """An empty acknowledged packet confirms the transport, never a client agent."""
    value=health.get('live') if isinstance(health,dict) else None
    if not health or health.get('state')!='connected':return 'Agent USB: host not connected'
    if not isinstance(value,dict):return 'Agent USB: waiting for confirmation'
    if value.get('state')=='unsupported':return 'Agent USB: update display firmware'
    stamp=value.get('updated_at')
    if type(stamp) not in (int,float) or not 0<=time.time()-stamp<=35:return 'Agent USB: confirmation expired'
    if value.get('state')=='error':return 'Agent USB: delivery failed; retrying'
    if value.get('state')=='stale':return 'Agent USB: source sample expired'
    if value.get('state')=='acknowledged':
        return 'Agent USB confirmed / '+str(value.get('agent_count',0))+' observed agents'
    return 'Agent USB: waiting for confirmation'


def validate_options(config):
    for key, (low, high, default) in OPTIONS.items():
        value = config.get(key, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'{key} must be an integer between {low} and {high}')
    for key, default in FLAGS.items():
        if type(config.get(key, default)) is not bool:
            raise ValueError(f'{key} must be true or false')


class HostStatus:
    def __init__(self, directory):
        self.path = Path(directory) / 'aim_host.status.json'
        self.data = {'pid': os.getpid(), 'state': 'starting', 'port': '', 'providers': {}}

    def update(self, state=None, port=None):
        if state is not None:
            if state not in STATES: raise ValueError('Unknown host state')
            self.data['state'] = state
        if port is not None:
            try: self.data['port'] = serial_port(port) if port else ''
            except ValueError: self.data['port'] = ''
        self.data['updated_at'] = time.time()
        temporary = None
        try:
            descriptor, temporary = tempfile.mkstemp(prefix='.aim-status-', suffix='.tmp', dir=self.path.parent)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump(self.data, stream, allow_nan=False)
            os.replace(temporary, self.path)
        except OSError:
            pass  # Status is advisory; a scanner must not interrupt USB traffic.
        finally:
            if temporary and os.path.exists(temporary): os.unlink(temporary)

    def provider(self, name, state):
        from provider_catalog import PROVIDERS
        if name not in PROVIDERS or state not in ('ready', 'unavailable', 'activity_only'):
            raise ValueError('Unknown provider health')
        self.data['providers'][name] = state
        self.update()


def read_status(root, pids):
    try:
        data = read_local_json(Path(root) / 'tools/aim_host.status.json', 16384)
        if not isinstance(data, dict) or data.get('state') not in STATES: return None
        if type(data.get('pid')) is not int or data['pid'] not in pids: return None
        timestamp = data.get('updated_at')
        if type(timestamp) not in (int, float) or not 0 <= time.time() - timestamp <= 45: return None
        port = data.get('port')
        if not isinstance(port, str): return None
        if port: serial_port(port)
        if not isinstance(data.get('providers'), dict) or len(data['providers']) > 8: return None
        from provider_catalog import PROVIDERS
        for name, value in data['providers'].items():
            if name not in PROVIDERS or value not in ('ready', 'unavailable', 'activity_only'): return None
        if 'display_sources' in data:
            mask,stamp=data['display_sources'],data.get('display_sources_at')
            if type(mask) is not int or not 0<=mask<=255 or type(stamp) not in (int,float) or not math.isfinite(stamp): return None
        if 'live' in data:
            live=data['live']
            if not isinstance(live,dict) or set(live)!={'state','agent_count','updated_at'}:return None
            if live['state'] not in ('unsupported','acknowledged','stale','error'):return None
            if type(live['agent_count']) is not int or not 0<=live['agent_count']<=8:return None
            stamp=live['updated_at']
            if type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0<=stamp<=time.time()+1:return None
        if 'history' in data:
            from usage_history import ERRORS
            history=data['history']
            if not isinstance(history,dict) or type(history.get('enabled')) is not bool: return None
            if history.get('error') is not None and history['error'] not in ERRORS: return None
        if data.get('local_reader','starting') not in ('starting','reading','ready','unavailable','stalled'): return None
        if 'hardware' in data:
            from hardware_baseline import validate_hardware
            stamp=data.get('hardware_at')
            if type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0<=stamp<=time.time()+1: return None
            data['hardware']=validate_hardware(data['hardware'],data.get('board'))
        return data
    except (ValueError, OSError, TypeError):
        return None
