"""Opt-in lifecycle metadata. No transcripts, tool arguments, decisions or model calls."""
import hashlib
from itertools import islice
import math
from pathlib import Path
import re
import time
from host_security import read_local_json
from session_activity import link_marker, MAX_SESSIONS
from telemetry_bridge import write_record
from usb_live import STATES

SOURCES = frozenset(('codex', 'claude'))
LEASE_SECONDS = 30


def marker(directory, provider):
    if provider == 'claude': return link_marker(directory)
    if provider != 'codex': return {'enabled': False, 'generation': 0}
    try:
        value = read_local_json(Path(directory)/'codex-session-link.json',1024)
        if (isinstance(value,dict) and type(value.get('enabled')) is bool and
                type(value.get('generation')) is int and 0 < value['generation'] < (1 << 63)):
            return value
    except (ValueError,OSError,TypeError): pass
    return {'enabled': False, 'generation': 0}


def lifecycle_event(provider, payload, directory, generation, now=None):
    if provider not in SOURCES or not isinstance(payload,dict) or type(generation) is not int: return
    current = marker(directory,provider)
    if not current['enabled'] or current['generation'] != generation: return
    session,event = payload.get('session_id'),payload.get('hook_event_name')
    if not isinstance(session,str) or not 1 <= len(session) <= 200 or not isinstance(event,str): return
    state = {'SessionStart':'IDLE','UserPromptSubmit':'UNKNOWN','PermissionRequest':'WAITING',
             'PreToolUse':'UNKNOWN','PostToolUse':'UNKNOWN','Stop':'DONE','SessionEnd':'closed',
             'Interrupt':'IDLE','SubagentStart':'UNKNOWN','SubagentStop':'DONE'}.get(event)
    if event == 'StopFailure' and provider == 'claude': state = 'FAILED'
    if event == 'Notification' and provider == 'claude':
        state = 'WAITING' if payload.get('notification_type') in ('permission_prompt','elicitation_dialog','agent_needs_input') else None
    if event == 'PreToolUse':
        tool=payload.get('tool_name')
        if tool in (('apply_patch',) if provider=='codex' else ('Edit','Write','MultiEdit')): state='EDITING'
        if provider=='claude' and tool in ('Grep','Glob','WebSearch'): state='SEARCHING'
    if state is None: return
    identity='session:'+session
    if event in ('SubagentStart','SubagentStop'):
        agent=payload.get('agent_id')
        if not isinstance(agent,str) or not 1 <= len(agent) <= 200: return
        # Length prefixes avoid composite-ID collisions; no raw identifiers are persisted.
        identity=f'agent:{len(session)}:{session}{agent}'
    timestamp=time.time() if now is None else now
    if type(timestamp) not in (int,float) or not math.isfinite(timestamp): return
    folder=Path(directory)/'live'/provider/str(generation)
    key=hashlib.sha256(identity.encode('utf-8')).hexdigest()
    record=dict(schema=1,state=state,received_at=timestamp,generation=generation)
    write_record(folder/(key+'.json'),record)
    # Bounded scan, even if the local directory was filled with unrelated files.
    paths=[path for path in islice(folder.glob('*.json'),MAX_SESSIONS*2)
           if re.fullmatch(r'[0-9a-f]{64}\.json',path.name) and not path.is_symlink()]
    paths.sort(key=lambda path:path.stat().st_mtime,reverse=True)
    for path in paths[MAX_SESSIONS:]: path.unlink()


def live_agents(directory, providers, now=None):
    timestamp=time.time() if now is None else now
    if type(timestamp) not in (int,float) or not math.isfinite(timestamp): return []
    rows=[]
    for provider in providers:
        if provider not in SOURCES: continue
        current=marker(directory,provider)
        if not current['enabled']: continue
        folder=Path(directory)/'live'/provider/str(current['generation'])
        if not folder.is_dir(): continue
        for path in islice(folder.glob('*.json'),MAX_SESSIONS*2):
            if not re.fullmatch(r'[0-9a-f]{64}\.json',path.name) or path.is_symlink(): continue
            try:
                value=read_local_json(path,1024)
                if (not isinstance(value,dict) or set(value)!={'schema','state','received_at','generation'} or
                        type(value['schema']) is not int or value['schema']!=1 or
                        type(value['generation']) is not int or value['generation']!=current['generation'] or
                        not isinstance(value['state'],str) or value['state'] not in STATES or
                        type(value['received_at']) not in (int,float) or not math.isfinite(value['received_at']) or
                        not 0 <= timestamp-value['received_at'] < LEASE_SECONDS): continue
                rows.append((value['received_at'],dict(provider=provider,id=path.stem,state=value['state'])))
            except (OSError,ValueError,TypeError,RecursionError): continue
    rows.sort(key=lambda row:(row[1]['state'] not in ('WAITING','FAILED'),-row[0],row[1]['provider'],row[1]['id']))
    return [row[1] for row in rows[:8]]
