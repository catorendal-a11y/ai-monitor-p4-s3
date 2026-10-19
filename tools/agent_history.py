"""Opt-in fixed lifecycle journal. No prompts, arguments, outputs or permission hints."""
from contextlib import closing
import math
import os
import hashlib
from pathlib import Path
import re
import secrets
import sqlite3
import time
from host_security import read_local_json
from provider_catalog import PROVIDERS

EVENTS=frozenset(('SessionStart','SessionEnd','UserPromptSubmit','PreToolUse','PostToolUse',
    'PermissionRequest','Notification','Stop','StopFailure','Interrupt','SubagentStart','SubagentStop',
    'PostToolUseFailure','PermissionDenied','TeammateIdle','TaskCreated','TaskCompleted'))
STATES=frozenset(('IDLE','WORKING','READING','SEARCHING','EDITING','WRITING','RUNNING',
                 'WAITING','NEEDS_ATTENTION','ERROR','COMPLETED','closed','TASK_REQUESTED'))
ACTIVE=STATES-{'IDLE','WAITING','NEEDS_ATTENTION','ERROR','COMPLETED','closed','TASK_REQUESTED'}
MAX_EVENTS=50000
APPLICATION_ID=0x41494d48
CONSENT_LEASE_SECONDS=90


def configure(directory,enabled,epoch):
    if type(enabled) is not bool or type(epoch) is not int or not 0<epoch<(1<<63):
        raise ValueError('Invalid agent history preference')
    import history_consent as authority
    Path(directory).mkdir(parents=True,exist_ok=True)
    with authority.lock(directory):return authority.publish_locked(directory,enabled,epoch)


def revoke(directory):
    """Explicit revocation serializes with hook/numeric commits; storage errors propagate."""
    import history_consent as authority
    if not Path(directory).exists():return
    with authority.lock(directory):authority.revoke_locked(directory)


def valid_consent(consent):
    from history_consent import valid
    return valid(consent)


def create_schema(database):
    database.execute('CREATE TABLE IF NOT EXISTS agent_events('
        'id TEXT PRIMARY KEY,provider TEXT NOT NULL,agent TEXT NOT NULL,generation INTEGER NOT NULL,'
        'epoch INTEGER NOT NULL,event TEXT NOT NULL,state TEXT NOT NULL,at REAL NOT NULL,root INTEGER NOT NULL)')
    database.execute('CREATE INDEX IF NOT EXISTS agent_event_time ON agent_events(provider,at)')
    database.execute('CREATE INDEX IF NOT EXISTS agent_turn_identity ON agent_events(provider,agent,generation,epoch,at) '
        "WHERE root=1 AND event IN ('UserPromptSubmit','Stop','StopFailure','Interrupt','SessionEnd')")
    database.execute('CREATE TABLE IF NOT EXISTS task_events('
        'id TEXT PRIMARY KEY,provider TEXT NOT NULL,task TEXT NOT NULL,generation INTEGER NOT NULL,'
        'epoch INTEGER NOT NULL,event TEXT NOT NULL,at REAL NOT NULL)')
    database.execute('CREATE INDEX IF NOT EXISTS task_event_time ON task_events(provider,at)')


def observe_task(directory,payload,generation,at):
    """Claude 2.1.296 verified post-tool contract. Requests/TaskGet never prove completion time."""
    if (not isinstance(payload,dict) or payload.get('hook_event_name')!='PostToolUse'
            or type(generation) is not int or not 0<generation<(1<<63)
            or type(at) not in (int,float) or not math.isfinite(at) or not 0<=at<=253402300799):return
    session,use=payload.get('session_id'),payload.get('tool_use_id')
    if any(not isinstance(value,str) or not 1<=len(value)<=200 for value in (session,use)):return
    response,inputs=payload.get('tool_response'),payload.get('tool_input')
    if not isinstance(response,dict) or not isinstance(inputs,dict) or 'error' in response or response.get('is_error') is True:return
    event=task=None
    if payload.get('tool_name')=='TaskCreate':
        value=response.get('task')
        if not isinstance(value,dict) or ('success' in response and response['success'] is not True):return
        task=value.get('id');event='created'
    elif payload.get('tool_name')=='TaskUpdate':
        task=inputs.get('taskId');change=response.get('statusChange')
        if response.get('success') is not True or response.get('taskId')!=task or not isinstance(change,dict):return
        target,previous=change.get('to'),change.get('from')
        if not isinstance(target,str) or inputs.get('status')!=target or not isinstance(previous,str):return
        if target=='completed' and previous in ('pending','in_progress'):event='completed'
        elif target=='in_progress' and previous in ('pending','completed'):event='started'
    if event is None or not isinstance(task,str) or not 1<=len(task)<=200:return
    from claude_paths import config_root
    config=os.path.normcase(str(config_root().resolve()))
    scope=os.environ.get('CLAUDE_CODE_TASK_LIST_ID') or session
    if len(config)>4096 or len(scope)>4096:return
    key='v2:'+hashlib.sha256((str(len(config))+':'+config+str(len(scope))+':'+scope+task).encode()).hexdigest()
    try:
        folder=Path(directory);path=folder/'history.db'
        import history_consent as authority
        with authority.lock(folder,timeout=.02):
            consent=read_local_json(folder/'agent-history-consent.json',256)
            if not authority.admitted(folder,consent) or not path.is_file() or path.is_symlink():return
            with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=rw',uri=True,timeout=.02)) as database,database:
                database.execute('PRAGMA trusted_schema=OFF')
                if (database.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID or
                        database.execute('PRAGMA user_version').fetchone()[0]!=2):return
                deadline=time.monotonic()+.05
                database.set_progress_handler(lambda:time.monotonic()>deadline,100)
                current=read_local_json(folder/'agent-history-consent.json',256)
                if not authority.admitted(folder,current) or current['epoch']!=consent['epoch']:return
                identity=hashlib.sha256((key+':'+str(generation)+':'+str(consent['epoch'])+':'+use+':'+event).encode()).hexdigest()
                database.execute('INSERT OR IGNORE INTO task_events VALUES(?,?,?,?,?,?,?)',
                    (identity,'claude',key,generation,consent['epoch'],event,float(at)))
                database.execute('DELETE FROM task_events WHERE at<?',(at-30*86400,))
                database.execute('DELETE FROM task_events WHERE id IN '
                    '(SELECT id FROM task_events ORDER BY at DESC,rowid DESC LIMIT -1 OFFSET ?)',(MAX_EVENTS,))
    except (OSError,ValueError,TypeError,sqlite3.Error):pass


def task_summary(database,provider,start,end,end_exclusive=False,include_reasons=False):
    if (not isinstance(provider,str) or provider not in PROVIDERS or
            any(type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=253402300799
                for value in (start,end)) or end<start):raise ValueError('Invalid task history interval')
    empty=dict(createdTasks=None,startedTasks=None,completedTasks=None,failedTasks=None)
    reasons={field:('unsupported_tasks' if provider!='claude' or field=='failedTasks' else 'no_task_evidence') for field in empty}
    if include_reasons:empty['unknownReasons']=reasons
    if not database.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='task_events'").fetchone():return empty
    rows=database.execute('SELECT task,generation,epoch,event,at FROM task_events '
        'WHERE provider=? AND at>=? AND at<=? ORDER BY at,rowid LIMIT ?',
        (provider,start,end,MAX_EVENTS+1)).fetchall()
    if len(rows)>MAX_EVENTS:raise ValueError('Task history limit reached')
    counts={event:set() for event in ('created','started','completed')}
    for task,generation,epoch,event,at in rows:
        if (not isinstance(task,str) or not re.fullmatch('(?:v2:)?[0-9a-f]{64}',task)
                or type(generation) is not int or not 0<generation<(1<<63)
                or type(epoch) is not int or not 0<epoch<(1<<63) or event not in counts
                or type(at) not in (int,float) or not math.isfinite(at) or not 0<=at<=253402300799):
            raise ValueError('Invalid task history')
        if not end_exclusive or at<end:counts[event].add(task)
    for field,event in [('createdTasks','created'),('startedTasks','started'),('completedTasks','completed')]:
        if counts[event]:
            # Old session-scoped hashes cannot be mapped to new task-list identities.
            # Preserve records but never sum possibly duplicate mixed-era tasks.
            versions={task.startswith('v2:') for task in counts[event]}
            if len(versions)==1:
                empty[field]=len(counts[event]);reasons.pop(field,None)
            else:reasons[field]='mixed_task_identity'
    return empty


def record(directory,provider,agent,generation,event,state,at,root):
    """Best effort on the hook process, with a 20ms SQLite lock deadline. Never fails a hook."""
    if (provider not in ('claude','codex','zcode') or not isinstance(agent,str) or not re.fullmatch('[0-9a-f]{64}',agent)
            or type(generation) is not int or not 0<generation<(1<<63)
            or not isinstance(event,str) or event not in EVENTS or not isinstance(state,str) or state not in STATES
            or type(at) not in (int,float) or not math.isfinite(at) or not 0<=at<=253402300799 or type(root) is not bool):return
    try:
        folder=Path(directory);path=folder/'history.db'
        import history_consent as authority
        with authority.lock(folder,timeout=.02):
            consent=read_local_json(folder/'agent-history-consent.json',256)
            if not authority.admitted(folder,consent) or not path.is_file() or path.is_symlink():return
            with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=rw',uri=True,timeout=.02)) as database,database:
                database.execute('PRAGMA trusted_schema=OFF')
                if (database.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID
                        or database.execute('PRAGMA user_version').fetchone()[0]!=2):return
                deadline=time.monotonic()+.05
                database.set_progress_handler(lambda:time.monotonic()>deadline,100)
                # Recheck after obtaining SQLite authority; a disabled generation cannot be imported later.
                current=read_local_json(folder/'agent-history-consent.json',256)
                if not authority.admitted(folder,current) or current['epoch']!=consent['epoch']:return
                database.execute('INSERT INTO agent_events VALUES(?,?,?,?,?,?,?,?,?)',
                    (secrets.token_hex(16),provider,agent,generation,consent['epoch'],event,state,float(at),int(root)))
                database.execute('DELETE FROM agent_events WHERE at<?',(at-30*86400,))
                database.execute('DELETE FROM agent_events WHERE id IN '
                    '(SELECT id FROM agent_events ORDER BY at DESC,rowid DESC LIMIT -1 OFFSET ?)',(MAX_EVENTS,))
    except (OSError,ValueError,TypeError,sqlite3.Error):pass


def summarize(database,provider,start,end,end_exclusive=False):
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
    previous={};sessions=set();turns={};finished=set();seeded=set();intervals=[];completed=failed=0;observed=False
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
        in_period=at>=start and (not end_exclusive or at<end)
        if in_period:observed=True
        old=previous.get(key)
        if old and old[1] in ACTIVE and 0<=at-old[0]<=900:
            left,right=max(start,old[0]),min(end,at)
            if left<right:intervals.append((left,right))
        previous[key]=(at,state)
        if event=='SessionStart' and root and in_period:sessions.add((agent,generation))
        if root and event in ('UserPromptSubmit','Stop','StopFailure','Interrupt','SessionEnd') and key not in seeded:
            seeded.add(key)
            # Activity needs only a 900s lookback. A first terminal event may
            # close a much older prompt; fetch one indexed prior lifecycle event
            # for this exact identity instead of rescanning 30 days for every day.
            if event!='UserPromptSubmit':
                prior=database.execute('SELECT event,state,at FROM agent_events WHERE provider=? '
                    'AND agent=? AND generation=? AND epoch=? AND at<? AND root=1 AND event IN '
                    "('UserPromptSubmit','Stop','StopFailure','Interrupt','SessionEnd') "
                    'ORDER BY at DESC,rowid DESC LIMIT 1',(provider,agent,generation,epoch,start-900)).fetchone()
                if prior:
                    prior_event,prior_state,prior_at=prior
                    if (prior_event not in EVENTS or prior_state not in STATES
                            or type(prior_at) not in (int,float) or not math.isfinite(prior_at)
                            or not 0<=prior_at<=253402300799):raise ValueError('Invalid agent history')
                    if prior_event=='UserPromptSubmit':turns[key]=prior_at
        if event=='UserPromptSubmit' and root:turns[key]=at
        if event in ('Stop','StopFailure','Interrupt','SessionEnd') and key in turns:
            identity=(key,turns.pop(key))
            if identity not in finished and in_period:
                if event in ('Stop','StopFailure'):
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


def daily_summaries(database,provider,days,now,include_reasons=False):
    """Local calendar days; a boundary event closes time but belongs to the next day."""
    from usage_history import calendar_days
    rows=[]
    for date,start,finish in calendar_days(now,days):
        row=summarize(database,provider,max(0,start),min(finish,now),end_exclusive=finish<=now)
        row.update(task_summary(database,provider,max(0,start),min(finish,now),end_exclusive=finish<=now,
                                include_reasons=include_reasons))
        if include_reasons:
            for field,reason in [('sessions','no_session_start'),('activeSeconds','no_activity_interval'),
                                 ('completedTurns','no_terminal_evidence'),('failedTurns','no_terminal_evidence')]:
                if row[field] is None:row['unknownReasons'][field]=reason
        rows.append(dict(provider=provider,date=date,**row))
    return rows
