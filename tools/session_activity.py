"""Opt-in, state-only session events. Never save prompt text or make decisions."""
import hashlib
from itertools import islice
import math
from pathlib import Path
import re
import time
from host_security import read_local_json
from provider_catalog import PROVIDERS
from telemetry_bridge import write_record

STATES = frozenset(('idle', 'running', 'waiting', 'completed', 'error', 'closed'))
LEASE_SECONDS = 900
TERMINAL_SECONDS = 30
MAX_SESSIONS = 64


def link_marker(directory):
    try:
        data=read_local_json(Path(directory)/'claude-session-link.json',1024)
        if (isinstance(data,dict) and type(data.get('enabled')) is bool
                and type(data.get('generation')) is int and 0<data['generation']<(1<<63)):
            return data
    except (ValueError,OSError,TypeError): pass
    return {'enabled':False,'generation':0}


def ingest_event(provider, payload, directory, now=None, generation=None):
    if provider not in PROVIDERS or not isinstance(payload, dict):
        raise ValueError('Invalid session event')
    identifier, state = payload.get('session_id'), payload.get('state')
    if not isinstance(identifier, str) or not 1 <= len(identifier) <= 200 or not isinstance(state,str) or state not in STATES:
        raise ValueError('Session events require an ID and an allowed state')
    timestamp = time.time() if now is None else now
    if type(timestamp) not in (int, float) or not math.isfinite(timestamp):
        raise ValueError('Invalid event time')
    folder = Path(directory)/'sessions'/provider
    key = hashlib.sha256(identifier.encode('utf-8')).hexdigest()
    record={'state':state, 'received_at':timestamp}
    if generation is not None:
        if type(generation) is not int or not 0<generation<(1<<63): raise ValueError('Invalid session generation')
        if provider=='claude':
            marker=link_marker(directory)
            if not marker['enabled'] or marker['generation']!=generation: return
        folder=folder/str(generation)
        record['generation']=generation
    write_record(folder/(key+'.json'),record)
    paths = sorted(folder.glob('*.json'), key=lambda p:p.stat().st_mtime, reverse=True)
    for old in paths[MAX_SESSIONS:]: old.unlink()


def claude_event(payload, directory, now=None, generation=None):
    """Observe documented hooks silently; stdout must never influence Claude."""
    if not isinstance(payload, dict): return
    event = payload.get('hook_event_name')
    if not isinstance(event,str): return
    state = {'SessionStart':'idle', 'UserPromptSubmit':'running', 'PreToolUse':'running',
             'PostToolUse':'running', 'PermissionRequest':'waiting', 'Stop':'completed',
             'StopFailure':'error', 'SessionEnd':'closed'}.get(event)
    state={'PostToolUseFailure':'error','PermissionDenied':'waiting','TeammateIdle':'idle',
           'SubagentStart':'running','SubagentStop':'completed'}.get(event,state)
    if event=='PostToolUseFailure' and payload.get('is_interrupt') is True:state='idle'
    if event == 'Notification':
        kind = payload.get('notification_type')
        state = 'waiting' if kind in ('permission_prompt','elicitation_dialog','agent_needs_input') else None
    if state is not None:
        identifier=payload.get('session_id')
        child=payload.get('agent_id')
        if child is not None or event in ('SubagentStart','SubagentStop','TeammateIdle'):
            if child is None and event=='TeammateIdle':child=payload.get('teammate_name')
            if (not isinstance(identifier,str) or not 1<=len(identifier)<=200 or
                    not isinstance(child,str) or not 1<=len(child)<=200):return
            identifier=hashlib.sha256(f'agent:{len(identifier)}:{identifier}{child}'.encode()).hexdigest()
        ingest_event('claude', {'session_id':identifier, 'state':state}, directory, now, generation)


def summary(directory, providers, now=None):
    timestamp = time.time() if now is None else now
    rows = []
    for provider in providers:
        if provider not in PROVIDERS: raise ValueError('Unsupported event source')
        marker=None
        if provider=='claude' and (Path(directory)/'claude-session-link.json').exists():
            marker=link_marker(directory)
            if not marker['enabled']: continue
        counts = dict(running=0, waiting=0, completed=0, error=0)
        known = False
        folder = Path(directory)/'sessions'/provider
        if marker is not None: folder=folder/str(marker['generation'])
        if folder.is_dir():
            paths = islice(folder.glob('*.json'),MAX_SESSIONS)
            for path in paths:
                if not re.fullmatch(r'[0-9a-f]{64}\.json', path.name): continue
                try:
                    data = read_local_json(path, 1024)
                    if not isinstance(data, dict) or set(data) not in ({'state','received_at'},{'state','received_at','generation'}): continue
                    if marker is not None and data.get('generation')!=marker['generation']: continue
                    state, received = data['state'], data['received_at']
                    if not isinstance(state,str) or state not in STATES or type(received) not in (int,float) or not math.isfinite(received): continue
                    age = timestamp-received
                    limit = TERMINAL_SECONDS if state in ('completed','error','closed') else LEASE_SECONDS
                    if not 0 <= age <= limit: continue
                    known = True
                    if state in counts: counts[state] += 1
                except (OSError,ValueError,TypeError,RecursionError): continue
        if known: rows.append(dict(provider=provider, **counts))
    return {'cmd':'session_activity','providers':rows}


def aggregate(message):
    rows = message.get('providers', [])
    return dict(known=bool(rows), **{key:sum(row[key] for row in rows)
                                   for key in ('running','waiting','completed','error')})
