"""Validated submission/rotation counters; never equate flush chunks with display FPS."""


def validate_graphics(data):
    if not isinstance(data,dict) or data.get('type')!='graphics' or type(data.get('schema')) is not int or data['schema']!=1:
        raise ValueError('Unsupported graphics telemetry')
    for key in ('enabled','saturated','ppaActive'):
        if type(data.get(key)) is not bool: raise ValueError('Invalid graphics state')
    if data['ppaActive'] or data.get('displayRefreshHz') is not None: raise ValueError('Unverified scanout/acceleration state')
    result=dict(type='graphics',schema=1,enabled=data['enabled'],saturated=data['saturated'],
        ppaActive=False,displayRefreshHz=None)
    for key in ('bootId','uptimeMs','maxRotationUs','maxSubmissionUs','flushCalls','pixelsSubmitted','rotationUs','submissionUs'):
        value=data.get(key); maximum=0xffffffff if key in ('bootId','uptimeMs','maxRotationUs','maxSubmissionUs') else (1<<64)-1
        if type(value) is not int or not 0<=value<=maximum: raise ValueError('Invalid graphics counter')
        result[key]=value
    if not result['enabled'] and any(result[key] for key in ('flushCalls','pixelsSubmitted','rotationUs','submissionUs')):
        raise ValueError('Disabled instrumentation contains samples')
    if result['maxRotationUs']>result['rotationUs'] or result['maxSubmissionUs']>result['submissionUs']:
        raise ValueError('Inconsistent graphics times')
    return result


def interval(first,last):
    first,last=validate_graphics(first),validate_graphics(last)
    elapsed=(last['uptimeMs']-first['uptimeMs'])&0xffffffff
    if (not first['enabled'] or not last['enabled'] or first['saturated'] or last['saturated'] or
        first['bootId']!=last['bootId'] or not 0<elapsed<=600000): return None
    fields=('flushCalls','pixelsSubmitted','rotationUs','submissionUs')
    values={key:last[key]-first[key] for key in fields}
    if any(value<0 for value in values.values()): return None
    return dict(durationMs=elapsed,**values,
        meanRotationUs=values['rotationUs']/values['flushCalls'] if values['flushCalls'] else None,
        meanSubmissionUs=values['submissionUs']/values['flushCalls'] if values['flushCalls'] else None,
        displayRefreshHz=None,meaning='CPU rotation and driver submission; not physical display FPS or DMA completion')
