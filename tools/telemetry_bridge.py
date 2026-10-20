"""Numeric-only local bridge. No prompts, responses or credentials are saved."""
import hashlib
import math
import os  # noqa: F401 (tests patch os.replace through this module)
from pathlib import Path
import time
from provider_catalog import PROVIDERS
from host_security import read_local_json


def write_record(path, record):
    from private_files import write_json
    write_json(path,record)


def ingest(provider, payload, directory):
    if provider not in PROVIDERS or not isinstance(payload, dict):
        raise ValueError('Unsupported bridge provider or record')
    identifier, total = payload.get('session_id'), payload.get('total_tokens')
    if not isinstance(identifier, str) or not 1 <= len(identifier) <= 200 or type(total) is not int or not 0 <= total <= 0xffffffffffffffff:
        raise ValueError('Bridge requires session_id and cumulative total_tokens')
    key = hashlib.sha256(identifier.encode()).hexdigest()
    folder = Path(directory) / provider
    write_record(folder / (key + '.json'), {'total_tokens': total, 'received_at': time.time()})
    paths = sorted(folder.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in paths[128:]: old.unlink()


def read_counters(directory, provider):
    folder = Path(directory) / provider
    if not folder.is_dir(): return None
    counts = {}
    for path in list(folder.glob('*.json'))[:128]:
        try:
            if path.stat().st_size > 4096: continue
            record = read_local_json(path, 4096)
            value = record.get('total_tokens')
            if type(value) is int and 0 <= value <= 0xffffffffffffffff:
                counts['bridge:' + path.stem] = value
        except (OSError, ValueError, AttributeError): continue
    return counts or None


def claude_statusline(payload, directory):
    # These documented fields are plan rate limits, not context-window occupancy.
    rates = payload.get('rate_limits', {}) if isinstance(payload, dict) else {}
    rows = []
    if not isinstance(rates, dict): rates = {}
    for name, title, minutes in [('five_hour', 'Session', 300), ('seven_day', 'Week', 10080)]:
        value = rates.get(name)
        if not isinstance(value, dict): continue
        percent, reset = value.get('used_percentage'), value.get('resets_at')
        if type(percent) not in (int, float) or not math.isfinite(percent) or not 0 <= percent <= 100: continue
        if type(reset) not in (int, float) or not math.isfinite(reset) or not 0 <= reset <= 253402300799: continue
        rows.append({'title': title, 'usedPercent': percent, 'reset_epoch': reset, 'windowMinutes': minutes})
    write_record(Path(directory) / 'claude-quota.json', {'received_at': time.time(), 'rows': rows})
    return 'LimitBuddy: quota linked' if rows else 'LimitBuddy: local activity only'


def read_claude_quota(directory, now=None):
    try:
        path = Path(directory) / 'claude-quota.json'
        if path.stat().st_size > 4096: return None
        data = read_local_json(path, 4096)
        age = (time.time() if now is None else now) - data['received_at']
        if not 0 <= age <= 300 or not isinstance(data['rows'], list) or not 1 <= len(data['rows']) <= 2: return None
        for row in data['rows']:
            if not isinstance(row, dict) or row.get('title') not in ('Session', 'Week') or row.get('windowMinutes') not in (300, 10080): return None
            for key in ('usedPercent', 'reset_epoch'):
                if type(row.get(key)) not in (int, float) or not math.isfinite(row[key]): return None
            if not 0 <= row['usedPercent'] <= 100 or not 0 <= row['reset_epoch'] <= 253402300799: return None
        return data['rows']
    except (OSError, ValueError, KeyError, TypeError):
        return None
