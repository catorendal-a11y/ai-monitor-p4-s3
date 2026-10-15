"""Opt-in lifecycle metadata. No transcripts, tool arguments, decisions or model calls."""
import hashlib
from contextlib import contextmanager
from itertools import islice
import math
import os
from pathlib import Path
import re
import time
import threading
from host_security import read_local_json
from session_activity import link_marker, MAX_SESSIONS
from telemetry_bridge import write_record
from usb_live import STATES

SOURCES = frozenset(('codex', 'claude', 'zcode'))
ZCODE_EVENTS = frozenset(('SessionStart','UserPromptSubmit','PreToolUse','PermissionRequest',
                         'PostToolUse','PostToolUseFailure','Stop'))
LEASE_SECONDS = 900
TERMINAL_SECONDS = 30
MAX_DURATION = 604800


def marker(directory, provider):
    if provider == 'claude': return link_marker(directory)
    if provider not in ('codex','zcode'): return {'enabled': False, 'generation': 0}
    try:
        value = read_local_json(Path(directory)/(provider+'-session-link.json'),1024)
        if (isinstance(value,dict) and type(value.get('enabled')) is bool and
                type(value.get('generation')) is int and 0 < value['generation'] < (1 << 63)):
            return value
    except (ValueError,OSError,TypeError): pass
    return {'enabled': False, 'generation': 0}


def lifecycle_event(provider, payload, directory, generation, now=None):
    if provider not in SOURCES:return
    current=marker(directory,provider)
    if not current['enabled'] or current['generation']!=generation:return
    with _event_lock(Path(directory),provider):
        _lifecycle_event(provider,payload,directory,generation,now)


@contextmanager
def _event_lock(directory,provider):
    """Bounded same-PC serialization; concurrent hooks cannot overwrite a newer timer."""
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/('.live-'+provider+'.lock')
    if path.is_symlink():raise ValueError('Invalid event lock')
    with path.open('a+b') as stream:
        if os.name=='nt':
            import msvcrt
            if path.stat().st_size==0:stream.write(b'0');stream.flush()
            deadline=time.monotonic()+.2
            while True:
                try:
                    stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1);break
                except OSError:
                    if time.monotonic()>=deadline:raise
                    time.sleep(.01)
            try:yield
            finally:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            deadline=time.monotonic()+.2
            while True:
                try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:
                    if time.monotonic()>=deadline:raise
                    time.sleep(.01)
            try:yield
            finally:fcntl.flock(stream,fcntl.LOCK_UN)


def _lifecycle_event(provider, payload, directory, generation, now=None):
    if provider not in SOURCES or not isinstance(payload,dict) or type(generation) is not int: return
    current = marker(directory,provider)
    if not current['enabled'] or current['generation'] != generation: return
    session,event = payload.get('session_id'),payload.get('hook_event_name')
    if not isinstance(session,str) or not 1 <= len(session) <= 200 or not isinstance(event,str): return
    if provider=='zcode' and event not in ZCODE_EVENTS:return
    if provider=='claude' and event in ('TaskCreated','TaskCompleted'):
        task=payload.get('task_id');timestamp=time.time() if now is None else now
        if (not isinstance(task,str) or not 1<=len(task)<=200 or type(timestamp) not in (int,float)
                or not math.isfinite(timestamp)):return
        # These hooks fire before other handlers can veto. Never count them as confirmed success.
        key=hashlib.sha256(f'task:{len(session)}:{session}{task}'.encode()).hexdigest()
        folder=Path(directory)/'task-events'/provider/str(generation)
        write_record(folder/(key+'.json'),dict(schema=1,generation=generation,received_at=timestamp,
            event='TASK_CREATE_REQUESTED' if event=='TaskCreated' else 'TASK_COMPLETE_REQUESTED'))
        paths=[p for p in islice(folder.glob('*.json'),MAX_SESSIONS*2)
               if re.fullmatch(r'[0-9a-f]{64}\.json',p.name) and not p.is_symlink()]
        paths.sort(key=lambda p:p.stat().st_mtime,reverse=True)
        for path in paths[MAX_SESSIONS:]:path.unlink()
        return
    state = {'SessionStart':'IDLE','UserPromptSubmit':'WORKING','PermissionRequest':'WAITING',
             'PreToolUse':'WORKING','PostToolUse':'WORKING','Stop':'COMPLETED','SessionEnd':'closed',
             'Interrupt':'IDLE','SubagentStart':'WORKING','SubagentStop':'COMPLETED'}.get(event)
    if provider == 'claude':
        state = {'StopFailure':'ERROR','PostToolUseFailure':'ERROR',
                 'PermissionDenied':'NEEDS_ATTENTION','TeammateIdle':'IDLE'}.get(event,state)
        if event == 'PostToolUseFailure' and payload.get('is_interrupt') is True: state='IDLE'
    if provider=='zcode' and event=='PostToolUseFailure':
        state='IDLE' if payload.get('is_interrupt') is True else 'ERROR'
    if event == 'Notification' and provider == 'claude':
        state = 'WAITING' if payload.get('notification_type') in ('permission_prompt','elicitation_dialog','agent_needs_input') else None
    if event == 'PreToolUse':
        tool=payload.get('tool_name')
        if tool in (('apply_patch',) if provider=='codex' else ('Edit','MultiEdit')): state='EDITING'
        if provider in ('claude','zcode'):
            state={'Write':'WRITING','Read':'READING','Grep':'SEARCHING','Glob':'SEARCHING',
                   'WebSearch':'SEARCHING','WebFetch':'READING','Bash':'RUNNING','PowerShell':'RUNNING'}.get(tool,state)
    if state is None: return
    identity='session:'+session
    agent=payload.get('agent_id')
    if event in ('SubagentStart','SubagentStop') or (provider=='claude' and agent is not None):
        if not isinstance(agent,str) or not 1 <= len(agent) <= 200: return
        # Length prefixes avoid composite-ID collisions; no raw identifiers are persisted.
        identity=f'agent:{len(session)}:{session}{agent}'
    if provider=='claude' and event=='TeammateIdle' and agent is None:
        teammate=payload.get('teammate_name')
        if not isinstance(teammate,str) or not 1<=len(teammate)<=200:return
        identity=f'teammate:{len(session)}:{session}{teammate}'
    timestamp=time.time() if now is None else now
    if type(timestamp) not in (int,float) or not math.isfinite(timestamp): return
    folder=Path(directory)/'live'/provider/str(generation)
    key=hashlib.sha256(identity.encode('utf-8')).hexdigest()
    path=folder/(key+'.json')
    previous=_read_record(path,generation)
    if previous and previous['received_at']>timestamp:return
    record=dict(schema=2,state=state,received_at=timestamp,generation=generation)
    if event in ('UserPromptSubmit','SubagentStart'):
        record['started_at']=timestamp
    elif previous and event!='SessionStart' and 'started_at' in previous:
        start=previous['started_at']
        if 0<=timestamp-start<=MAX_DURATION:record['started_at']=start
    if 'started_at' in record:
        if (event in ('Stop','SubagentStop','StopFailure','Interrupt','SessionEnd','TeammateIdle') or
                (event=='PostToolUseFailure' and payload.get('is_interrupt') is True)):
            record['finished_at']=timestamp
        elif previous and 'finished_at' in previous and event not in ('UserPromptSubmit','SubagentStart'):
            # No new start was observed: never resume an old completed timer on tool metadata.
            record.pop('started_at',None)
    write_record(path,record)
    from agent_history import record as record_history
    record_history(directory,provider,key,generation,event,state,timestamp,identity.startswith('session:'))
    # Bounded scan, even if the local directory was filled with unrelated files.
    paths=[path for path in islice(folder.glob('*.json'),MAX_SESSIONS*2)
           if re.fullmatch(r'[0-9a-f]{64}\.json',path.name) and not path.is_symlink()]
    paths.sort(key=lambda path:path.stat().st_mtime,reverse=True)
    for path in paths[MAX_SESSIONS:]: path.unlink()


def _read_record(path,generation):
    try:
        value=read_local_json(path,1024)
        required={'schema','state','received_at','generation'}
        if (not isinstance(value,dict) or not required<=set(value) or
                set(value)-required-{'started_at','finished_at'} or
                type(value['schema']) is not int or value['schema'] not in (1,2) or
                type(value['generation']) is not int or value['generation']!=generation or
                not isinstance(value['state'],str) or value['state'] not in STATES|{'closed'}):return None
        for key in ('received_at','started_at','finished_at'):
            if key in value and (type(value[key]) not in (int,float) or not math.isfinite(value[key])):return None
        if 'finished_at' in value and 'started_at' not in value:return None
        if 'started_at' in value and not 0<=value['received_at']-value['started_at']<=MAX_DURATION:return None
        if 'finished_at' in value and not value['started_at']<=value['finished_at']<=value['received_at']:return None
        return value
    except (ValueError,OSError,TypeError,RecursionError):return None


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
                value=_read_record(path,current['generation'])
                if not value or value['state'] not in STATES:continue
                age=timestamp-value['received_at']
                limit=TERMINAL_SECONDS if value['state'] in ('COMPLETED','DONE','FAILED','ERROR','IDLE') else LEASE_SECONDS
                if not 0<=age<limit:continue
                row=dict(provider=provider,id=path.stem,state=value['state'],observedAgeSeconds=int(age))
                if 'started_at' in value:
                    end=value.get('finished_at',timestamp)
                    elapsed=end-value['started_at']
                    if 0<=elapsed<=MAX_DURATION:row['elapsedSeconds']=int(elapsed)
                rows.append((value['received_at'],row))
            except (OSError,ValueError,TypeError,RecursionError): continue
    rows.sort(key=lambda row:(row[1]['state'] not in ('WAITING','FAILED','ERROR','NEEDS_ATTENTION'),-row[0],row[1]['provider'],row[1]['id']))
    return [row[1] for row in rows[:8]]


class LiveSampler:
    """Independent bounded event reader; numeric source I/O never delays this worker."""
    def __init__(self,directory,providers):
        self.directory=directory
        self.providers=list(providers)
        self.condition=threading.Condition()
        self.result=None
        self.requested=self.busy=self.closed=False
        self.generation=0
        self.next_poll=0
        self.worker=threading.Thread(target=self._read,daemon=True,name='aim-live-events')
        self.worker.start()

    def configure(self,providers):
        with self.condition:
            self.providers=list(providers)
            self.generation+=1
            self.result=None
            self.next_poll=0

    def poll(self):
        with self.condition:
            value,self.result=self.result,None
            now=time.monotonic()
            if not self.closed and not self.busy and not self.requested and now>=self.next_poll:
                self.next_poll=now+2
                self.requested=True
                self.condition.notify_all()
            return value

    def _read(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.requested or self.closed)
                if self.closed:return
                self.requested=False;self.busy=True
                providers,generation=list(self.providers),self.generation
            try:rows=live_agents(self.directory,providers)
            except (OSError,ValueError,TypeError,RecursionError):rows=[]
            value={'live_agents':rows,'live_sampled_at':time.monotonic()}
            with self.condition:
                self.busy=False
                if self.closed:return
                if generation==self.generation:self.result=value
                self.condition.notify_all()

    def close(self):
        with self.condition:
            self.closed=True;self.result=None
            self.condition.notify_all()
