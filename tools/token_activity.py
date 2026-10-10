"""Read selected local usage metrics; retain no conversation content."""
import sqlite3
from contextlib import closing
from collections import OrderedDict
import time
from pathlib import Path
from local_activity import LocalActivity
from provider_catalog import PROVIDERS
from codex_support import codex_home


class TokenReporter:
    MAX_TRACKED = 8192  # Keep recent IDs across temporarily missing/evicted query rows.
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
        self.last_use = None
        self.last_poll = None
        self.poll_seconds = 2

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
        for provider in self.providers:
            bit = PROVIDERS[provider][1]
            if provider in ('codex', 'zcode'):
                counts = self.read_counts(provider, self.paths[provider])
            elif provider in ('claude', 'gemini'):
                counts = self.local.read(provider, self.paths[provider])
            elif provider == 'opencode':
                from opencode_activity import read_counts
                counts = read_counts(self.paths[provider])
            else:
                counts = None
            if self.activity_dir is not None:
                from telemetry_bridge import read_counters
                bridge = read_counters(self.activity_dir, provider)
                if bridge is not None:
                    counts = dict(counts or {}, **bridge)
            if counts is None:
                continue
            sources |= bit
            previous = self.previous.get(provider)
            if previous is not None:
                for key, value in counts.items():
                    # Codex forks/imports can contain history on first sight. Baseline new thread IDs.
                    baseline_new = provider == 'codex' or (provider == 'opencode' and key.startswith('session:'))
                    old = previous.get(key, value if baseline_new else 0)
                    delta += max(0, value - old)
            history = previous if previous is not None else OrderedDict()
            for key, value in counts.items():
                history[key] = value
                history.move_to_end(key)
            while len(history) > self.MAX_TRACKED:
                history.popitem(last=False)
            self.previous[provider] = history
        if delta:
            self.last_use = now
        idle = max(0, int(now - (self.last_use if self.last_use is not None else self.started)))
        return {"cmd": "token_activity", "known": bool(sources), "seen": self.last_use is not None,
                "sources": sources, "idleSeconds": min(0xffffffff, idle), "delta": min(0xffffffffffffffff, delta)}
