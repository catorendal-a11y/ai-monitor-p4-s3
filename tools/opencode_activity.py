"""Read numeric OpenCode V1/V2 usage projections, never credentials or messages."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import time


def database_path(home=None):
    home = Path.home() if home is None else Path(home)
    data = Path(os.environ.get('XDG_DATA_HOME') or home / '.local/share') / 'opencode'
    override = os.environ.get('OPENCODE_DB')
    if override == ':memory:': return None
    if override and override != ':memory:':
        path = Path(override).expanduser()
        return path if path.is_absolute() else data / path
    return data / 'opencode.db'


def read_counts(path):
    if path is None or not path.is_file(): return None
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=0.15)) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA trusted_schema=OFF')
            deadline = time.monotonic() + 0.1
            db.set_progress_handler(lambda: time.monotonic() > deadline, 1000)
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('message','session_v2')")}
            # V2 totals are already aggregated by the client's own usage projector.
            if 'session_v2' in tables:
                query = ('SELECT id,tokens_input,tokens_output,tokens_reasoning,tokens_cache_read,tokens_cache_write '
                         'FROM session_v2 ORDER BY time_updated DESC LIMIT 512')
            elif 'message' in tables:
                # SQLite extracts only numeric fields; no prompt/response JSON leaves the database.
                fields = ('input', 'output', 'reasoning', 'cache.read', 'cache.write')
                expressions = ','.join("json_extract(data,'$.tokens." + field + "')" for field in fields)
                valid = ' AND '.join("json_type(data,'$.tokens." + field + "')='integer'" for field in fields)
                query = ("SELECT id," + expressions + " FROM message WHERE json_valid(data) "
                         "AND json_extract(data,'$.role')='assistant' AND " + valid + ' ORDER BY time_updated DESC LIMIT 4096')
            else:
                return None
            counts = {}
            for identifier, *values in db.execute(query):
                if not isinstance(identifier, str) or not 1 <= len(identifier) <= 200: continue
                if any(type(v) is not int or not 0 <= v <= 0xffffffffffffffff for v in values): continue
                key = hashlib.sha256(identifier.encode()).hexdigest()
                counts[('session:' if 'session_v2' in tables else 'message:') + key] = min(0xffffffffffffffff, sum(values))
            return counts
    except (sqlite3.Error, OSError, ValueError):
        return None
