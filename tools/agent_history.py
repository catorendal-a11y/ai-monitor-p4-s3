"""Opt-in fixed lifecycle journal. No prompts, arguments, outputs or permission hints."""
from contextlib import closing
import math
from pathlib import Path
import re
import secrets
import sqlite3
import time
from host_security import read_local_json
from telemetry_bridge import write_record
from provider_catalog import PROVIDERS

EVENTS=frozenset(('SessionStart','SessionEnd','UserPromptSubmit','PreToolUse','PostToolUse',
    'PermissionRequest','Notification','Stop','StopFailure','Interrupt','SubagentStart','SubagentStop',
    'PostToolUseFailure','PermissionDenied','TeammateIdle','TaskCreated','TaskCompleted'))
STATES=frozenset(('IDLE','WORKING','READING','SEARCHING','EDITING','WRITING','RUNNING',
                 'WAITING','NEEDS_ATTENTION','ERROR','COMPLETED','closed','TASK_REQUESTED'))
ACTIVE=STATES-{'IDLE','WAITING','NEEDS_ATTENTION','ERROR','COMPLETED','closed','TASK_REQUESTED'}
MAX_EVENTS=50000
APPLICATION_ID=0x41494d48


def configure(directory,enabled,epoch):
    if type(enabled) is not bool or type(epoch) is not int or not 0<epoch<(1<<63):
        raise ValueError('Invalid agent history preference')
    write_record(Path(directory)/'agent-history-consent.json',dict(enabled=enabled,epoch=epoch))


def create_schema(database):
    database.execute('CREATE TABLE IF NOT EXISTS agent_events('
        'id TEXT PRIMARY KEY,provider TEXT NOT NULL,agent TEXT NOT NULL,generation INTEGER NOT NULL,'
        'epoch INTEGER NOT NULL,event TEXT NOT NULL,state TEXT NOT NULL,at REAL NOT NULL,root INTEGER NOT NULL)')
    database.execute('CREATE INDEX IF NOT EXISTS agent_event_time ON agent_events(provider,at)')


def record(directory,provider,agent,generation,event,state,at,root):
    """Best effort on the hook process, with a 20ms SQLite lock deadline. Never fails a hook."""
    if (provider not in ('claude','codex') or not isinstance(agent,str) or not re.fullmatch('[0-9a-f]{64}',agent)
            or type(generation) is not int or not 0<generation<(1<<63)
            or not isinstance(event,str) or event not in EVENTS or not isinstance(state,str) or state not in STATES
            or type(at) not in (int,float) or not math.isfinite(at) or not 0<=at<=253402300799 or type(root) is not bool):return
    try:
        folder=Path(directory);path=folder/'history.db'
        consent=read_local_json(folder/'agent-history-consent.json',256)
        if (not isinstance(consent,dict) or set(consent)!={'enabled','epoch'} or consent['enabled'] is not True
                or type(consent['epoch']) is not int or not 0<consent['epoch']<(1<<63)
                or not path.is_file() or path.is_symlink()):return
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=rw',uri=True,timeout=.02)) as database,database:
            database.execute('PRAGMA trusted_schema=OFF')
            if (database.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID
                    or database.execute('PRAGMA user_version').fetchone()[0]!=2):return
            deadline=time.monotonic()+.05
            database.set_progress_handler(lambda:time.monotonic()>deadline,100)
            # Recheck after obtaining SQLite authority; a disabled generation cannot be imported later.
            if read_local_json(folder/'agent-history-consent.json',256)!=consent:return
            database.execute('INSERT INTO agent_events VALUES(?,?,?,?,?,?,?,?,?)',
                (secrets.token_hex(16),provider,agent,generation,consent['epoch'],event,state,float(at),int(root)))
            database.execute('DELETE FROM agent_events WHERE at<?',(at-30*86400,))
            database.execute('DELETE FROM agent_events WHERE id IN '
                '(SELECT id FROM agent_events ORDER BY at DESC,rowid DESC LIMIT -1 OFFSET ?)',(MAX_EVENTS,))
    except (OSError,ValueError,TypeError,sqlite3.Error):pass


def summarize(database,provider,start,end):
    """Observed metrics only. Waiting/gaps excluded; concurrent activity intervals are unioned."""
    if (not isinstance(provider,str) or provider not in PROVIDERS
            or any(type(value) not in (int,float) or not math.isfinite(value)
                   or not 0<=value<=253402300799 for value in (start,end)) or end<start):
        raise ValueError('Invalid agent history interval')
    empty=dict(sessions=None,activeSeconds=None,completedTurns=None,failedTurns=None)
    if database.execute('PRAGMA user_version').fetchone()[0]!=2:return empty
    rows=database.execute('SELECT agent,generation,epoch,event,state,at,root FROM agent_events '
        'WHERE provider=? AND at>=? AND at<=? ORDER BY at,rowid LIMIT ?',
        (provider,start-900,end,MAX_EVENTS+1)).fetchall()
    if len(rows)>MAX_EVENTS:raise ValueError('Agent history limit reached')
    previous={};sessions=set();turns={};finished=set();intervals=[];completed=failed=0;observed=False
    for agent,generation,epoch,event,state,at,root in rows:
        if (not isinstance(agent,str) or not re.fullmatch('[0-9a-f]{64}',agent)
                or type(generation) is not int or not 0<generation<(1<<63)
                or type(epoch) is not int or not 0<epoch<(1<<63)
                or event not in EVENTS or state not in STATES or type(at) not in (int,float)
                or not math.isfinite(at) or not 0<=at<=253402300799
                or type(root) is not int or root not in (0,1)):
            raise ValueError('Invalid agent history')
        key=(agent,generation,epoch)
        if state=='TASK_REQUESTED':continue  # Hook requests are not confirmed task success.
        if at>=start:observed=True
        old=previous.get(key)
        if old and old[1] in ACTIVE and 0<=at-old[0]<=900:
            left,right=max(start,old[0]),min(end,at)
            if left<right:intervals.append((left,right))
        previous[key]=(at,state)
        if event=='SessionStart' and root and at>=start:sessions.add((agent,generation))
        if event=='UserPromptSubmit' and root:turns[key]=at
        if event in ('Stop','StopFailure','Interrupt','SessionEnd') and key in turns:
            identity=(key,turns.pop(key))
            if identity not in finished and at>=start:
                finished.add(identity)
                completed+=event=='Stop';failed+=event=='StopFailure'
    if not observed:return empty
    total=0.;right=None
    for left,end_at in sorted(intervals):
        if right is None or left>right:total+=end_at-left;right=end_at
        elif end_at>right:total+=end_at-right;right=end_at
    # Absence of a SessionStart is unknown, not proof that no sessions occurred.
    return dict(sessions=len(sessions) if sessions else None,activeSeconds=int(total) if intervals else None,
                completedTurns=completed if finished else None,failedTurns=failed if finished else None)
