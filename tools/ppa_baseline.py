"""Validate an isolated PPA measurement without implying production acceleration."""

STATES = frozenset(('not-run', 'unsupported', 'allocation-failed', 'registration-failed',
    'callback-failed', 'submission-failed', 'timeout-resources-retained', 'cleanup-unconfirmed',
    'passed', 'pixel-mismatch'))
FIELDS = ('type', 'schema', 'status', 'width', 'height', 'samples', 'cpuMedianUs',
    'ppaMedianUs', 'bitExact', 'resourcesRetained', 'isolated', 'productionPpaActive')


def validate_ppa(data):
    if (not isinstance(data, dict) or not set(FIELDS).issubset(data) or data.get('type') != 'ppa_benchmark' or
            type(data.get('schema')) is not int or data['schema'] != 1):
        raise ValueError('Unsupported PPA result')
    if not isinstance(data.get('status'), str) or data['status'] not in STATES: raise ValueError('Invalid benchmark status')
    for key in ('bitExact', 'resourcesRetained', 'isolated', 'productionPpaActive'):
        if type(data.get(key)) is not bool: raise ValueError('Invalid benchmark flag')
    if not data['isolated'] or data['productionPpaActive']: raise ValueError('Not an isolated benchmark')
    for key in ('width', 'height', 'samples', 'cpuMedianUs', 'ppaMedianUs'):
        if type(data.get(key)) is not int or not 0 <= data[key] <= 0xffffffff:
            raise ValueError('Invalid benchmark measurement')
    if (data['width'], data['height']) != (800, 480) or data['samples'] > 8:
        raise ValueError('Unexpected benchmark dimensions')
    if data['status'] in ('passed', 'pixel-mismatch'):
        if data['samples'] != 8 or not data['cpuMedianUs'] or not data['ppaMedianUs'] or data['resourcesRetained']:
            raise ValueError('Incomplete measurement')
        if data['bitExact'] != (data['status'] == 'passed'): raise ValueError('Inconsistent pixel comparison')
    if data['status'] in ('timeout-resources-retained', 'cleanup-unconfirmed') and not data['resourcesRetained']:
        raise ValueError('Unconfirmed buffer lifetime')
    return {key: data[key] for key in FIELDS}
