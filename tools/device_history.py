"""Compact read-only device summaries from existing numeric history. No new database/model."""
from contextlib import closing
from datetime import datetime, timedelta
import math
import threading
import time
import sqlite3
from provider_catalog import PROVIDERS
from usage_history import connect, MAX_INTEGER


def day_boundaries(now):
    today = datetime.fromtimestamp(now).date()
    # Ask the OS for each local midnight, rather than assuming every day lasts 24 hours.
    days = [today + timedelta(days=offset) for offset in range(-6, 2)]
    return today.isoformat(), [int(time.mktime(datetime.combine(day, datetime.min.time()).timetuple())) // 60 for day in days]


def compact_history(directory, providers, enabled, now=None, boundaries=None):
    if type(enabled) is not bool or not isinstance(providers, (list, tuple)) or len(providers)>8 or len(set(providers))!=len(providers) or any(p not in PROVIDERS for p in providers):
        raise ValueError('Invalid device history selection')
    now = time.time() if now is None else now
    if type(now) not in (int, float) or not math.isfinite(now) or not 0<=now<=253402300799:
        raise ValueError('Invalid history clock')
    date, starts = day_boundaries(now) if boundaries is None else boundaries
    if (not isinstance(date,str) or len(date)!=10 or len(starts)!=8 or
        any(type(n) is not int or n<0 for n in starts) or any(not 1200<=b-a<=1680 for a,b in zip(starts,starts[1:]))):
        raise ValueError('Invalid local day boundaries')
    if datetime.strptime(date,'%Y-%m-%d').strftime('%Y-%m-%d')!=date:raise ValueError('Invalid local history date')
    minute = int(now)//60;hour = minute//60
    result=dict(enabled=enabled, date=date, sampledAt=now, providers=[], error=False)
    if not enabled:return result
    for provider in providers:
        result['providers'].append(dict(provider=provider,today=None,daily=[None]*7,hourly=[None]*24,quota=None,
            agents=dict(sessions=None,activeSeconds=None,completedTurns=None,failedTurns=None,
                        createdTasks=None,startedTasks=None,completedTasks=None,failedTasks=None)))
    try:
        database=connect(directory)
        if database is None:return result
        with closing(database):
            for record in result['providers']:
                provider=record['provider']
                from agent_history import summarize,task_summary
                record['agents']=summarize(database,provider,starts[6]*60,now)
                record['agents'].update(task_summary(database,provider,starts[6]*60,now))
                # At most seven days of minute buckets, with the DB's existing 500ms hard deadline.
                rows=database.execute('SELECT minute,tokens FROM tokens WHERE provider=? AND minute>=? AND minute<=? ORDER BY minute',
                    (provider,min(starts[0],(hour-23)*60),minute))
                for observed,count in rows:
                    if type(observed) is not int or type(count) is not int or not 0<=count<=MAX_INTEGER:
                        raise ValueError('Invalid numeric history')
                    for index in range(7):
                        if starts[index]<=observed<starts[index+1]:
                            record['daily'][index]=bounded_sum(record['daily'][index],count);break
                    bucket=observed//60-(hour-23)
                    if 0<=bucket<24:record['hourly'][bucket]=bounded_sum(record['hourly'][bucket],count)
                record['today']=record['daily'][6]
                # One explicitly identified model-quota window; never merge different resets/epochs.
                latest=database.execute('SELECT minute,window,used,reset,epoch FROM quota WHERE provider=? AND kind=? '
                    'AND minute>=? AND minute<=? ORDER BY minute DESC,window ASC LIMIT 1',(provider,'model',starts[6],minute)).fetchone()
                if latest:
                    observed,window,used,reset,epoch=latest
                    if (type(observed) is not int or type(window) is not int or not 0<=window<=525600 or
                        type(used) not in (int,float) or not math.isfinite(used) or not 0<=used<=100 or
                        type(reset) is not int or not 0<=reset<=253402300799 or type(epoch) is not int or not 0<=epoch<=MAX_INTEGER):
                        raise ValueError('Invalid quota history')
                    earliest=database.execute('SELECT minute,used FROM quota WHERE provider=? AND window=? AND kind=? '
                        'AND reset=? AND epoch=? AND minute>=? AND minute<=? ORDER BY minute LIMIT 1',
                        (provider,window,'model',reset,epoch,starts[6],observed)).fetchone()
                    delta=None
                    if earliest and type(earliest[0]) is int and earliest[0]<observed:
                        initial=earliest[1]
                        if type(initial) not in (int,float) or not math.isfinite(initial) or not 0<=initial<=100:raise ValueError('Invalid quota history')
                        if initial<=used:delta=round(used-initial,2)
                    record['quota']=dict(windowMinutes=window,usedPercent=float(used),changePercent=delta,ageMinutes=minute-observed)
    except (ValueError,TypeError,OSError,sqlite3.Error,OverflowError):
        result['error']=True
        for record in result['providers']:
            record.update(today=None,daily=[None]*7,hourly=[None]*24,quota=None,
                agents=dict(sessions=None,activeSeconds=None,completedTurns=None,failedTurns=None,
                            createdTasks=None,startedTasks=None,completedTasks=None,failedTasks=None))
    return result


def bounded_sum(previous,value):
    total=(previous or 0)+value
    if total>MAX_INTEGER:raise ValueError('History numeric limit reached')
    return total


class HistorySampler:
    """One bounded/coalesced background reader. SQLite never blocks the serial owner."""
    def __init__(self,directory,providers,enabled=False,clock=time.monotonic):
        self.directory=directory;self.clock=clock;self.condition=threading.Condition()
        self.closed=False;self.enabled=False;self.providers=();self.generation=0
        self.pending=False;self.latest=None;self.next_read=0
        self.configure(enabled,providers)
        self.worker=threading.Thread(target=self._run,daemon=True,name='aim-device-history');self.worker.start()
    def configure(self,enabled,providers):
        if type(enabled) is not bool or len(providers)>8 or len(set(providers))!=len(providers) or any(p not in PROVIDERS for p in providers):
            raise ValueError('Invalid device history selection')
        with self.condition:
            if (enabled,tuple(providers))==(self.enabled,self.providers):return
            self.enabled=enabled;self.providers=tuple(providers);self.generation+=1
            self.latest=None;self.next_read=0;self.pending=False
    def take(self):
        with self.condition:
            value=self.latest;self.latest=None
            if not self.closed and not self.pending and self.clock()>=self.next_read:
                self.pending=True;self.next_read=self.clock()+30;self.condition.notify()
            return value
    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.pending or self.closed)
                if self.closed:return
                enabled,providers,generation=self.enabled,self.providers,self.generation;self.pending=False
            try:value=compact_history(self.directory,providers,enabled)
            except (ValueError,OverflowError,OSError):continue # Clock/storage recovery can retry; never fabricate a date.
            with self.condition:
                if generation==self.generation:self.latest=value
    def close(self):
        with self.condition:self.closed=True;self.condition.notify()
        self.worker.join(timeout=1)
