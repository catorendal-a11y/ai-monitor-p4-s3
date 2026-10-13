"""Strict standalone probe results; controller RPC is not a BLE connection."""
import re
import json
import time

STAGES = frozenset(('pending', 'completed', 'deadline-exceeded', 'nvs-init-failed',
    'event-loop-failed', 'host-init-failed', 'transport-failed',
    'coprocessor-identity-unverified', 'version-query-failed', 'controller-init-failed',
    'controller-enable-failed', 'task-allocation-failed'))
FIELDS = ('type', 'schema', 'stage', 'error', 'hostVersion', 'coprocessorResponded',
    'coprocessorVersion', 'configuredSlaveTarget', 'detectedChip', 'controllerEnableConfirmed',
    'deadlineExceeded', 'retryAllowed')


def version(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}', value) is not None


def validate_probe(data):
    if (not isinstance(data, dict) or not set(FIELDS).issubset(data) or data.get('type') != 'c6_probe' or
            type(data.get('schema')) is not int or data['schema'] != 1):
        raise ValueError('Unsupported C6 probe result')
    stage = data.get('stage')
    if not isinstance(stage, str) or stage not in STAGES or type(data.get('error')) is not int or not -2147483648 <= data['error'] <= 2147483647:
        raise ValueError('Invalid probe state')
    for key in ('coprocessorResponded', 'controllerEnableConfirmed', 'deadlineExceeded', 'retryAllowed'):
        if type(data.get(key)) is not bool: raise ValueError('Invalid probe flag')
    if data['retryAllowed'] or data.get('configuredSlaveTarget') != 'esp32c6' or not version(data.get('hostVersion')):
        raise ValueError('Invalid probe configuration')
    chip = data.get('detectedChip')
    if chip not in (None, 'esp32c6'): raise ValueError('Unsupported coprocessor')
    if data['coprocessorResponded']:
        if chip != 'esp32c6' or not version(data.get('coprocessorVersion')):
            raise ValueError('Unverified coprocessor version')
    elif data.get('coprocessorVersion') is not None:
        raise ValueError('Unexpected coprocessor version')
    if data['controllerEnableConfirmed'] and not data['coprocessorResponded']:
        raise ValueError('Unverified controller')
    if data['deadlineExceeded'] != (stage == 'deadline-exceeded'):
        raise ValueError('Inconsistent deadline')
    if stage == 'completed' and (data['error'] != 0 or not data['controllerEnableConfirmed']):
        raise ValueError('Incomplete controller probe')
    if stage not in ('pending', 'completed') and data['error'] == 0:
        raise ValueError('Failure without error')
    return {key: data[key] for key in FIELDS}


def collect_probe(serial, clock=time.monotonic):
    """Query an already installed standalone probe, with bounded framing and time."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('Duplicate probe field')
            result[key] = value
        return result
    began = clock(); next_query = began
    line = bytearray(); dropping = False
    while clock() - began < 15:
        now = clock()
        if now >= next_query:
            if serial.write(b'probe\n') != 6: raise OSError('Incomplete probe query')
            next_query = now + 0.5
        for byte in serial.read(256):
            if byte == 10:
                raw = bytes(line); line.clear()
                discarded = dropping; dropping = False
                if discarded or not raw.startswith(b'{'): continue
                try:
                    data = json.loads(raw, object_pairs_hook=unique)
                except (ValueError, RecursionError):
                    raise ValueError('Malformed probe response') from None
                if not isinstance(data, dict) or data.get('type') != 'c6_probe': continue
                result = validate_probe(data)
                if result['stage'] != 'pending': return result
            elif not dropping:
                if len(line) == 2048:
                    line.clear(); dropping = True
                else: line.append(byte)
    raise TimeoutError('Standalone C6 probe did not return a terminal result')
