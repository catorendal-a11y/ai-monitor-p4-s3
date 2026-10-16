"""Opt-in local numeric history. One bounded writer, no USB or model access."""
from collections import OrderedDict, deque
from contextlib import closing
from datetime import datetime, timezone
import math
from pathlib import Path
import sqlite3
import threading
import time
from provider_catalog import PROVIDERS

APPLICATION_ID = 0x41494d48
MAX_INTEGER = (1 << 63)-1
RETENTION_SECONDS = 30*86400
CONSENT_RENEW_SECONDS = 30
ERRORS = frozenset(('History numeric limit reached','History queue full; some observations were missed',
                   'History unavailable; check local storage. Some observations were missed.'))


def connect(directory, create=False):
    path = Path(directory)/'history.db'
    if path.is_symlink(): raise ValueError('Invalid history database path')
    if not create and not path.is_file(): return None
    if create: path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    database = sqlite3.connect(path if create else path.resolve().as_uri()+'?mode=ro',
                               uri=not create, timeout=.1)
    try:
        deadline = time.monotonic()+.5
        database.set_progress_handler(lambda: time.monotonic()>deadline, 1000)
        database.execute('PRAGMA trusted_schema=OFF')
        if not create: database.execute('PRAGMA query_only=ON')
        if exists:
            if database.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID:
                raise ValueError('Unsupported history database')
            schema=database.execute('PRAGMA user_version').fetchone()[0]
            if schema not in (1,2):
                raise ValueError('Unsupported history schema')
        else:
            database.executescript(f'''
                PRAGMA application_id={APPLICATION_ID}; PRAGMA user_version=1;
                CREATE TABLE tokens(provider TEXT NOT NULL, minute INTEGER NOT NULL, tokens INTEGER NOT NULL,
                    PRIMARY KEY(provider,minute));
                CREATE TABLE quota(provider TEXT NOT NULL, minute INTEGER NOT NULL, window INTEGER NOT NULL,
                    kind TEXT NOT NULL, used REAL NOT NULL, reset INTEGER NOT NULL, epoch INTEGER NOT NULL,
                    PRIMARY KEY(provider,minute,window,kind));
            ''')
        if create:
            from agent_history import create_schema
            with database:
                create_schema(database)
                database.execute('PRAGMA user_version=2')
        return database
    except Exception:
        database.close(); raise


def quota_rows(provider, rows, timestamp):
    result = []
    for row in (rows or [])[:3]:
        percent, minutes = row.get('usedPercent'), row.get('windowMinutes',0)
        if type(percent) not in (int,float) or not math.isfinite(percent) or not 0 <= percent <= 100: continue
        if type(minutes) is not int or not 0 <= minutes <= 525600: continue
        reset = 0
        raw = row.get('resetsAt')
        if isinstance(raw,str) and len(raw)<=40 and raw:
            try:
                parsed = datetime.fromisoformat(raw.replace('Z','+00:00'))
                if parsed.tzinfo is not None: reset = int(parsed.timestamp())
            except (ValueError,OverflowError,OSError): pass
        if not 0 <= reset <= 253402300799: reset=0
        # Store only a fixed metric kind, never arbitrary API text/account IDs.
        kind = 'tools' if 'mcp' in str(row.get('title','')).lower() else 'model'
        result.append((provider,int(timestamp)//60,minutes,kind,float(percent),reset))
    return result


class HistoryRecorder:
    def __init__(self, directory, enabled=False, clock=time.time, policy_path=None):
        if type(enabled) is not bool: raise ValueError('History preference must be boolean')
        self.directory, self.clock = Path(directory), clock
        self.policy_path=policy_path
        self.enabled, self.closed = bool(enabled), False
        self.condition = threading.Condition()
        self.generation = 0
        self.epoch = time.time_ns()
        self.needs_epoch = bool(enabled)
        self.recheck_requested = False
        self.request_epoch = self.epoch
        self.tokens = OrderedDict()
        self.quotas = deque(maxlen=128)
        self.last_error = None
        self.worker = threading.Thread(target=self._write,daemon=True,name='aim-numeric-history')
        self.worker.start()

    def configure(self, enabled):
        if type(enabled) is not bool: raise ValueError('History preference must be boolean')
        with self.condition:
            if self.closed:return
            if self.enabled==enabled:
                if enabled:
                    self.recheck_requested=True;self.request_epoch=max(time.time_ns(),self.epoch+1)
                    self.condition.notify()
                return
        # Minting/validation belongs to the existing writer, never the USB owner.
        with self.condition:
            if self.closed or self.enabled == enabled:return
            self.enabled=enabled;self.generation+=1
            self.epoch=max(time.time_ns(),self.epoch+1);self.needs_epoch=enabled
            if not enabled:self.tokens.clear();self.quotas.clear()
            self.condition.notify()

    def _publish_consent(self, enabled, epoch, allow_shutdown=False):
        """Caller holds cross-process authority; disabled policy never renews an old host."""
        from agent_history import configure
        from history_consent import policy_allows
        if enabled and not policy_allows(self.directory,self.policy_path):
            configure(self.directory,False,epoch)
            return False
        admitted=configure(self.directory,enabled,epoch)
        with self.condition:
            stale = (self.closed and not allow_shutdown) or self.epoch != epoch or self.enabled != enabled
            current_epoch = self.epoch
        if enabled and stale:
            configure(self.directory,False,current_epoch)
            return False
        return admitted is not False

    def record_tokens(self, deltas):
        minute = int(self.clock())//60
        with self.condition:
            if not self.enabled or self.closed: return
            for provider, count in deltas.items():
                if provider not in PROVIDERS or type(count) is not int or not 0 < count <= MAX_INTEGER: continue
                key=(provider,minute)
                total=self.tokens.get(key,0)+count
                if total>MAX_INTEGER: self.last_error='History numeric limit reached'; continue
                self.tokens[key]=total
            while len(self.tokens)>256:
                self.tokens.popitem(last=False); self.last_error='History queue full; some observations were missed'
            self.condition.notify()

    def record_quota(self, provider, rows):
        if provider not in PROVIDERS: raise ValueError('Unsupported history provider')
        validated = quota_rows(provider,rows,self.clock())
        with self.condition:
            if not self.enabled or self.closed: return
            if len(self.quotas)==self.quotas.maxlen: self.last_error='History queue full; some observations were missed'
            self.quotas.extend(tuple(row)+(self.epoch,) for row in validated)
            self.condition.notify()

    def _write(self):
        published_epoch=0
        while True:
            with self.condition:
                self.condition.wait_for(lambda:self.tokens or self.quotas or self.closed or self.epoch!=published_epoch or self.recheck_requested,
                                        timeout=CONSENT_RENEW_SECONDS if self.enabled else None)
                tokens, quotas, generation, enabled, epoch = self.tokens, list(self.quotas), self.generation, self.enabled, self.epoch
                self.tokens=OrderedDict(); self.quotas.clear()
                stopped=self.closed
                needs_epoch=self.needs_epoch
                explicit_recheck=self.recheck_requested;self.recheck_requested=False
                request_epoch=self.request_epoch
            # No disk I/O under the queue lock: quota submission/USB stays
            # responsive. Disabling discards queued work; an in-flight sample
            # that was observed before disabling may finish its transaction.
            try:
                from agent_history import configure
                if not enabled or (stopped and not (tokens or quotas)):
                    self._publish_consent(False,epoch);published_epoch=epoch
                    if stopped:return
                    continue
                from history_consent import lock,mint_epoch,floor
                if explicit_recheck and not needs_epoch:
                    with lock(self.directory):revoked=epoch<=floor(self.directory)
                    if revoked:
                        needs_epoch=True;epoch=request_epoch
                        # Samples queued under revoked authority never move into a fresh epoch.
                        tokens=OrderedDict();quotas=[]
                        with self.condition:self.tokens.clear();self.quotas.clear()
                if needs_epoch:
                    fresh=mint_epoch(self.directory,request_epoch=epoch)
                    with self.condition:
                        if generation!=self.generation or not self.enabled:continue
                        self.epoch=epoch=fresh;self.needs_epoch=False
                    quotas=[row[:-1]+(epoch,) for row in quotas]
                with closing(connect(self.directory,create=True)) as database, lock(self.directory):
                    with self.condition:
                        if generation != self.generation or not self.enabled: continue
                    if not self._publish_consent(True,epoch,allow_shutdown=stopped):
                        published_epoch=epoch
                        continue
                    published_epoch=epoch
                    with database:
                        for (provider,minute),count in tokens.items():
                            old=database.execute('SELECT tokens FROM tokens WHERE provider=? AND minute=?',
                                                 (provider,minute)).fetchone()
                            total=(old[0] if old else 0)+count
                            if total>MAX_INTEGER: raise ValueError('History numeric limit reached')
                            database.execute('INSERT OR REPLACE INTO tokens VALUES(?,?,?)',(provider,minute,total))
                        database.executemany('INSERT OR REPLACE INTO quota VALUES(?,?,?,?,?,?,?)',
                                             [row[:-1]+(epoch,) for row in quotas])
                        oldest=int(self.clock()-RETENTION_SECONDS)//60
                        database.execute('DELETE FROM tokens WHERE minute<?',(oldest,))
                        database.execute('DELETE FROM quota WHERE minute<?',(oldest,))
                        # Hook sources may be idle for weeks; shared maintenance owns retention.
                        for table in ('agent_events','task_events'):
                            database.execute('DELETE FROM '+table+' WHERE at<?',(self.clock()-RETENTION_SECONDS,))
                if stopped:
                    configure(self.directory,False,epoch)
                    return
            except (ValueError,OSError,sqlite3.Error):
                self.last_error='History unavailable; check local storage. Some observations were missed.'
                published_epoch=epoch
                # A failed DB/migration must not leave observational hooks writing
                # under an old enabled marker, especially after host shutdown.
                try: self._publish_consent(False,epoch)
                except (ValueError,OSError): pass
                if stopped:return

    def close(self):
        with self.condition:
            self.closed=True; self.condition.notify()
        self.worker.join(timeout=1)


def read_history(directory, providers, days=7, now=None):
    if type(days) is not int or days not in (7,30): raise ValueError('Choose 7 or 30 history days')
    if len(providers)>8 or any(p not in PROVIDERS for p in providers): raise ValueError('Invalid history providers')
    now=time.time() if now is None else now
    if type(now) not in (int,float) or not math.isfinite(now) or not 0<=now<=253402214399:
        raise ValueError('Invalid history clock')
    result={'tokens':[], 'quota':[], 'forecasts':[], 'daily_agents':[], 'error':None}
    if not providers: return result
    try:
        database=connect(directory)
        if database is None: return result
        with closing(database):
            for provider in providers:
                from agent_history import daily_summaries
                result['daily_agents']+=daily_summaries(database,provider,days,now)
                totals=list(database.execute(
                    'SELECT minute/1440,SUM(tokens) FROM tokens WHERE provider=? AND minute>=? AND minute<=? '
                    'GROUP BY minute/1440 ORDER BY minute/1440 LIMIT 31',
                    (provider,int(now-days*86400)//60,int(now)//60)))
                if any(type(day) is not int or type(total) is not int or not 0<=total<=MAX_INTEGER for day,total in totals):
                    raise ValueError('Invalid numeric history')
                result['tokens'] += [dict(provider=provider,day=day,total=total) for day,total in totals]
                rows=list(database.execute('SELECT minute,window,kind,used,reset,epoch FROM quota '
                    'WHERE provider=? AND minute>=? AND minute<=? ORDER BY minute DESC LIMIT 256',
                    (provider,int(now-days*86400)//60,int(now)//60)))
                for m,w,k,u,r,e in rows:
                    if (type(m) is not int or type(w) is not int or not 0<=w<=525600 or k not in ('model','tools')
                            or type(u) not in (int,float) or not math.isfinite(u) or not 0<=u<=100
                            or type(r) is not int or not 0<=r<=253402300799 or type(e) is not int or not 0<=e<=MAX_INTEGER):
                        raise ValueError('Invalid quota history')
                result['quota'] += [dict(provider=provider,minute=m,window=w,kind=k,used=u,reset=r,epoch=e)
                                   for m,w,k,u,r,e in rows]
                latest={}
                for m,w,k,u,r,e in rows: latest.setdefault((w,k),(m,u,r,e))
                for (window,kind),(minute,used,reset,epoch) in latest.items():
                    if not 0<=now-minute*60<=600 or not now<reset<=now+RETENTION_SECONDS: continue
                    samples=sorted((m,u) for m,w,k,u,r,e in rows if (w,k,r,e)==(window,kind,reset,epoch)
                                   and 0<=minute-m<=60)
                    if len(samples)<3 or samples[-1][0]-samples[0][0]<2: continue
                    if any(b[0]-a[0]>10 for a,b in zip(samples,samples[1:])): continue
                    if any(b[1]<a[1] for a,b in zip(samples,samples[1:])): continue
                    rate=(samples[-1][1]-samples[0][1])*60/(samples[-1][0]-samples[0][0])
                    if rate<=0: continue
                    hours=max(0,(100-used)/rate)
                    result['forecasts'].append(dict(provider=provider,window=window,kind=kind,
                        percent_per_hour=rate,estimated_hours_to_limit=hours if now+hours*3600<reset else None,reset=reset))
    except (ValueError,OSError,sqlite3.Error,TypeError,OverflowError):
        result=dict(tokens=[],quota=[],forecasts=[],daily_agents=[],error='History unavailable. Check local storage; existing data was preserved.')
    return result
