"""Bounded usage extraction. Conversation text is never retained or exported."""
from collections import OrderedDict
import hashlib
import json
from host_security import read_local_json

MAX_FILES = 16
MAX_BYTES = 4 * 1024 * 1024
MAX_RECORD = 1024 * 1024


def numeric(value):
    return type(value) is int and 0 <= value <= 0xffffffffffffffff


class LocalActivity:
    def __init__(self):
        self.files = OrderedDict()

    @staticmethod
    def usage(provider, record):
        if not isinstance(record, dict):
            return None
        if provider == 'claude':
            if record.get('type') != 'assistant':
                return None
            message = record.get('message')
            if not isinstance(message, dict):
                return None
            usage = message.get('usage')
            identifier = message.get('id') or record.get('uuid')
            fields = ('input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')
            if not isinstance(usage, dict) or not isinstance(identifier, str) or not identifier:
                return None
            if not any(field in usage for field in fields) or any(not numeric(usage.get(field, 0)) for field in fields):
                return None
            return identifier, min(0xffffffffffffffff, sum(usage.get(field, 0) for field in fields))
        if provider == 'gemini' and record.get('type') == 'gemini':
            tokens = record.get('tokens')
            identifier = record.get('id')
            if isinstance(tokens, dict) and numeric(tokens.get('total')) and isinstance(identifier, str) and identifier:
                return identifier, tokens['total']
        return None

    def read(self, provider, root):
        if not root.is_dir():
            return None
        try:
            patterns = ('**/*.jsonl',) if provider == 'claude' else ('*/chats/session-*.json', '*/chats/session-*.jsonl')
            candidates = [path for pattern in patterns for path in root.glob(pattern) if path.is_file()]
            paths = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[:MAX_FILES]
        except OSError:
            return None
        if not paths:
            return None
        counts, readable = {}, False
        for path in paths:
            try:
                stat = path.stat(); state = self.files.get(path)
                if state is None or stat.st_size < state['offset'] or (stat.st_size == state['offset'] and stat.st_mtime_ns != state['mtime']):
                    state = {'offset': 0, 'mtime': 0, 'counts': OrderedDict()}
                if stat.st_size != state['offset'] or stat.st_mtime_ns != state['mtime']:
                    if path.suffix == '.json':
                        if stat.st_size > MAX_BYTES:
                            continue
                        document = read_local_json(path, MAX_BYTES)
                        if not isinstance(document, dict) or not isinstance(document.get('messages'), list):
                            continue
                        state['counts'].clear()
                        for record in document['messages']:
                            item = self.usage(provider, record)
                            if item: state['counts'][item[0]] = item[1]
                        state['offset'] = stat.st_size
                    else:
                        with path.open('rb') as data:
                            offset = state['offset']
                            if stat.st_size - offset > MAX_BYTES:
                                offset = stat.st_size - MAX_BYTES; data.seek(offset); data.readline(MAX_RECORD)
                            else: data.seek(offset)
                            while data.tell() < stat.st_size:
                                position = data.tell(); line = data.readline(MAX_RECORD + 1)
                                if len(line) > MAX_RECORD:
                                    while line and not line.endswith(b'\n'): line = data.readline(MAX_RECORD + 1)
                                    continue
                                if not line.endswith(b'\n'):
                                    data.seek(position); break  # an incomplete write is retried next poll
                                try: item = self.usage(provider, json.loads(line))
                                except (ValueError, UnicodeError, RecursionError): continue
                                if item: state['counts'][item[0]] = item[1]
                            state['offset'] = data.tell()
                    state['mtime'] = stat.st_mtime_ns
                while len(state['counts']) > 1024: state['counts'].popitem(last=False)
                self.files[path] = state; self.files.move_to_end(path)
                readable = True
                prefix = hashlib.sha256(str(path).encode()).hexdigest()[:16]
                counts.update({prefix + ':' + key: value for key, value in state['counts'].items()})
            except (OSError, ValueError, UnicodeError, RecursionError):
                continue
        while len(self.files) > MAX_FILES: self.files.popitem(last=False)
        return counts if readable else None
