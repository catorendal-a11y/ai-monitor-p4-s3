"""Read selected local usage metrics; retain no conversation content."""
import sqlite3
import hashlib
from contextlib import closing
from collections import OrderedDict
import time
import threading
from pathlib import Path
from local_activity import LocalActivity
from provider_catalog import PROVIDERS
from codex_support import codex_home


class TokenSampler:
    """One coalesced read worker; local I/O never owns or blocks USB.

    A stuck local source makes its signal expire, rather than creating more
    threads or delaying the heartbeat. Configuration changes discard old work.
    """
    def __init__(self, history=None, **options):
        self.options = options
        self.history = history
        self.condition = threading.Condition()
        self.reporter = TokenReporter(**options)
        self.generation = 0
        self.result = None
        self.requested = self.busy = self.closed = False
        self.next_poll = 0
        self.worker = threading.Thread(target=self._read, daemon=True, name='aim-local-counts')
        self.worker.start()

    @property
    def poll_seconds(self):
        with self.condition: return self.reporter.poll_seconds

    @poll_seconds.setter
    def poll_seconds(self, value):
        with self.condition: self.reporter.poll_seconds = value

    def configure(self, providers):
        with self.condition:
            self.reporter = TokenReporter(**dict(self.options, providers=list(providers)))
            self.generation += 1
            self.result = None
            self.next_poll = 0

    def poll(self):
        with self.condition:
            result, self.result = self.result, None
            now = time.monotonic()
            if not self.closed and not self.busy and not self.requested and now >= self.next_poll:
                self.next_poll = now + self.reporter.poll_seconds
                self.requested = True
                self.condition.notify()
            return result

    def _read(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.requested or self.closed)
                if self.closed: return
                self.requested = False
                self.busy = True
                reporter, generation = self.reporter, self.generation
            try:
                value = reporter.poll()
                if value is not None:
                    value['deltas'] = dict(reporter.deltas)
                    from session_activity import summary
                    try:
                        value['sessions'] = summary(self.options.get('activity_dir'), reporter.providers) if self.options.get('activity_dir') else {'cmd':'session_activity','providers':[]}
                    except (OSError,ValueError,TypeError,RecursionError): value['sessions']={'cmd':'session_activity','providers':[]}
                    with self.condition: current = generation == self.generation and not self.closed
                    if current and self.history is not None:
                        try: self.history.record_tokens(reporter.deltas)
                        except (OSError,ValueError,TypeError): pass  # Optional history never suppresses activity delivery.
            except Exception: value = None  # No source content or exceptions are exported.
            with self.condition:
                self.busy = False
                if self.closed: return
                if generation == self.generation and value is not None: self.result = value

    def close(self):
        with self.condition:
            self.closed = True
            self.result = None
            self.condition.notify()


class RetiredIds:
    """Bounded conservative tombstones: a false positive baselines, never invents use."""
    def __init__(self): self.bits = bytearray(65536)

    def positions(self, key):
        digest = hashlib.sha256(key.encode()).digest()
        return [int.from_bytes(digest[i:i+4], 'little') % (len(self.bits)*8) for i in (0, 4, 8, 12)]

    def add(self, key):
        for position in self.positions(key): self.bits[position//8] |= 1 << (position%8)

    def contains(self, key):
        return all(self.bits[position//8] & (1 << (position%8)) for position in self.positions(key))


class TokenReporter:
    MAX_TRACKED = 16384  # Accommodate all 16 x 1024 bounded local-file records.
    def __init__(self, home=None, clock=None, providers=None, activity_dir=None):
        default_home = home is None
        home = Path.home() if default_home else Path(home)
        self.paths = {"codex": home / ".codex/state_5.sqlite", "zcode": home / ".zcode/cli/db/db.sqlite"}
        if default_home: self.paths['codex'] = codex_home() / 'state_5.sqlite'
        self.paths.update(claude=home / '.claude/projects', gemini=home / '.gemini/tmp')
        from opencode_activity import database_path
        self.paths['opencode'] = database_path(home)
        self.providers = ['codex', 'zcode'] if providers is None else list(providers)
        self.activity_dir = Path(activity_dir) if activity_dir is not None else None
        self.local = LocalActivity()
        self.clock = time.monotonic if clock is None else clock
        self.started = None
        self.previous = {}
        self.retired = {}
        self.last_use = None
        self.last_poll = None
        self.poll_seconds = 2
        self.deltas = {}

    @staticmethod
    def read_counts(provider, path):
        if not path.is_file():
            return None
        query = ("SELECT id,tokens_used FROM threads ORDER BY updated_at_ms DESC LIMIT 512" if provider == "codex" else
                 "SELECT id,computed_total_tokens FROM model_usage ORDER BY started_at DESC LIMIT 4096")
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.15)) as database:
                database.execute("PRAGMA query_only=ON")
                database.execute("PRAGMA trusted_schema=OFF")
                deadline = time.monotonic() + 0.1
                database.set_progress_handler(lambda: time.monotonic() > deadline, 1000)
                return {str(key): count for key, count in database.execute(query)
                        if type(count) is int and 0 <= count <= 0xffffffffffffffff}
        except (sqlite3.Error, OSError):
            return None

    def poll(self):
        now = self.clock()
        if self.started is None:
            self.started = now
        if self.last_poll is not None and now - self.last_poll < self.poll_seconds:
            return None
        self.last_poll = now
        delta, sources = 0, 0
        self.deltas = {}
        for provider in self.providers:
            bit = PROVIDERS[provider][1]
            try:
                if provider in ('codex', 'zcode'):
                    counts = self.read_counts(provider, self.paths[provider])
                elif provider in ('claude', 'gemini'):
                    counts = self.local.read(provider, self.paths[provider])
                elif provider == 'opencode':
                    from opencode_activity import read_counts
                    counts = read_counts(self.paths[provider])
                else:
                    counts = None
            except (OSError, ValueError, RecursionError):
                counts = None  # One failed source must not interrupt the other AIs or USB.
            if self.activity_dir is not None:
                from telemetry_bridge import read_counters
                try: bridge = read_counters(self.activity_dir, provider)
                except (OSError, ValueError, RecursionError): bridge = None
                if bridge is not None:
                    counts = dict(counts or {}, **bridge)
            if counts is None:
                continue
            sources |= bit
            previous = self.previous.get(provider)
            provider_delta = 0
            if previous is not None:
                for key, value in counts.items():
                    # Codex forks/imports can contain history on first sight. Baseline new thread IDs.
                    baseline_new = (provider == 'codex' or (provider == 'opencode' and key.startswith('session:')) or
                                    (key not in previous and provider in self.retired and self.retired[provider].contains(key)))
                    old = previous.get(key, value if baseline_new else 0)
                    provider_delta += max(0, value - old)
            delta += provider_delta
            self.deltas[provider] = provider_delta
            history = previous if previous is not None else OrderedDict()
            for key, value in counts.items():
                history[key] = value
                history.move_to_end(key)
            while len(history) > self.MAX_TRACKED:
                key, _value = history.popitem(last=False)
                if provider not in self.retired: self.retired[provider] = RetiredIds()
                self.retired[provider].add(key)
            self.previous[provider] = history
        now = self.clock()  # Record observation time after local reads finish.
        if delta:
            self.last_use = now
        idle = max(0, int(now - (self.last_use if self.last_use is not None else self.started)))
        return {"cmd": "token_activity", "known": bool(sources), "seen": self.last_use is not None,
                "sources": sources, "idleSeconds": min(0xffffffff, idle), "delta": min(0xffffffffffffffff, delta)}
