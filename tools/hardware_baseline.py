"""Read-only device telemetry. Compiled capabilities never imply runtime detection."""
from board_profiles import get_board,matches_info


def validate_hardware(data,board_id):
    board=get_board(board_id)
    if not isinstance(data,dict) or data.get('type')!='hardware' or type(data.get('schema')) is not int or data['schema']!=1:
        raise ValueError('Unsupported hardware telemetry schema')
    if not matches_info(board,data): raise ValueError('Hardware identity mismatch')
    def number(container,key):
        value=container.get(key)
        if type(value) is not int or not 0<=value<=0xffffffff: raise ValueError('Invalid hardware metric')
        return value
    def text(key):
        value=data.get(key)
        if not isinstance(value,str) or not 1<=len(value)<=96 or any(ord(c)<32 or ord(c)>126 for c in value):
            raise ValueError('Invalid hardware version')
        return value
    result=dict(type='hardware',schema=1,boardId=board.id,chip=board.chip,
        firmwareVersion=text('firmwareVersion'),sdkVersion=text('sdkVersion'),
        chipRevision=number(data,'chipRevision'),cpuMHz=number(data,'cpuMHz'),
        bootId=number(data,'bootId'),uptimeMs=number(data,'uptimeMs'))
    fields={'flash':('bytes','frequencyHz','applicationBytes','partitionBytes','partitionOffset'),
        'internalHeap':('total','free','minimumFree','largestFreeBlock'),
        'psram':('sizeBytes','heapTotal','free','minimumFree','largestFreeBlock'),
        'display':('width','height','drawBytes','drawCount','rotationBytes','framebufferBytes','framebufferCount','bounceBytes')}
    for section,keys in fields.items():
        value=data.get(section)
        if not isinstance(value,dict): raise ValueError('Missing hardware section')
        result[section]={key:number(value,key) for key in keys}
    for section,total in [('internalHeap','total'),('psram','heapTotal')]:
        value=result[section]
        if not value['minimumFree']<=value['free']<=value[total] or value['largestFreeBlock']>value['free']:
            raise ValueError('Inconsistent memory metrics')
    if result['psram']['heapTotal']>result['psram']['sizeBytes']: raise ValueError('Inconsistent PSRAM capacity')
    flash=result['flash']
    if flash['applicationBytes']>flash['partitionBytes'] or flash['partitionOffset']+flash['partitionBytes']>flash['bytes']:
        raise ValueError('Inconsistent application partition')
    free=flash['partitionBytes']-flash['applicationBytes']
    if 'freeApplicationBytes' in data['flash'] and number(data['flash'],'freeApplicationBytes')!=free:
        raise ValueError('Inconsistent free application space')
    flash['freeApplicationBytes']=free
    if 'startupMemory' in data:
        stages=data['startupMemory']
        names=('before-display','after-display','after-lvgl','after-companion')
        if not isinstance(stages,list) or len(stages)!=4: raise ValueError('Invalid startup checkpoints')
        result['startupMemory']=[]; missing=False; previous=None
        for stage,name in zip(stages,names):
            if (not isinstance(stage,dict) or stage.get('stage')!=name or
                type(stage.get('captured')) is not bool): raise ValueError('Invalid startup stage')
            captured=stage['captured']; item=dict(stage=name,captured=captured)
            if captured:
                if missing: raise ValueError('Out-of-order startup checkpoints')
                timestamp=number(stage,'uptimeMs')
                if previous is not None and ((timestamp-previous)&0xffffffff)>600000:
                    raise ValueError('Invalid startup interval')
                previous=timestamp; item['uptimeMs']=timestamp
                for section in ('internalHeap','psram'):
                    reading=stage.get(section)
                    if not isinstance(reading,dict): raise ValueError('Missing startup memory')
                    values={key:number(reading,key) for key in ('total','free','minimumFree','largestFreeBlock')}
                    if not values['minimumFree']<=values['free']<=values['total'] or values['largestFreeBlock']>values['free']:
                        raise ValueError('Inconsistent startup memory')
                    if section=='psram' and values['total']>result['psram']['sizeBytes']:
                        raise ValueError('Invalid startup PSRAM capacity')
                    item[section]=values
            else: missing=True
            result['startupMemory'].append(item)
    display=result['display']
    if (display['width'],display['height'])!=(800,480) or display['drawCount']>2 or display['framebufferCount']>2:
        raise ValueError('Unsupported display memory layout')
    if data['display'].get('color')!='RGB565': raise ValueError('Unsupported display color')
    display['color']='RGB565'
    hosted=data.get('hosted'); ppa=data.get('ppa')
    if (not isinstance(hosted,dict) or type(hosted.get('compiled')) is not bool or
        hosted.get('probeState')!='not-probed' or hosted.get('detectedChip') is not None or
        hosted.get('coprocessorVersion') is not None): raise ValueError('Unverified radio state')
    version=hosted.get('hostVersion')
    if not isinstance(version,str) or not 1<=len(version)<=24 or any(ord(c)<32 or ord(c)>126 for c in version):
        raise ValueError('Invalid hosted version')
    result['hosted']=dict(compiled=hosted['compiled'],hostVersion=version,probeState='not-probed',
        detectedChip=None,coprocessorVersion=None)
    if not isinstance(ppa,dict) or type(ppa.get('supported')) is not bool or ppa.get('active') is not False:
        raise ValueError('Unverified graphics acceleration')
    result['ppa']=dict(supported=ppa['supported'],active=False)
    if 'companionCache' in data:
        cache=data['companionCache']
        if (not isinstance(cache,dict) or type(cache.get('enabled')) is not bool or
                type(cache.get('active')) is not bool): raise ValueError('Invalid companion cache state')
        values={key:number(cache,key) for key in
                ('allocatedBytes','decodedFrames','failures','lastSwitchUs','maxSwitchUs')}
        if (values['allocatedBytes']>2*430*284*3+128 or
                values['lastSwitchUs']>values['maxSwitchUs'] or
                (cache['active'] and not cache['enabled']) or
                (not cache['enabled'] and values['allocatedBytes'])):
            raise ValueError('Inconsistent companion cache metrics')
        result['companionCache']=dict(values,enabled=cache['enabled'],active=cache['active'])
    return result


def collect(panel,board_id):
    board=get_board(board_id)
    # Opening USB can restart the board. Keep the same connection while waiting
    # for its bounded initialization; identity mismatch is never retried.
    for attempt in range(3):
        panel.send_line('{"cmd":"get_info"}')
        try:
            info=panel.wait_for('info',seconds=3)
            break
        except TimeoutError:
            if attempt == 2: raise
    if not matches_info(board,info): raise ValueError('Device identity mismatch')
    panel.send_line('{"cmd":"get_hardware"}')
    try: reply=panel.wait_for('hardware',seconds=3)
    except RuntimeError:
        return dict(schema=1,identitySource='firmware-report',boardId=board.id,chip=board.chip,
            telemetry='unavailable-in-installed-firmware',hosted=dict(probeState='not-probed'),ppa=dict(active=False))
    hardware=validate_hardware(reply,board_id)
    if 'bootId' in info and (type(info['bootId']) is not int or info['bootId']!=hardware['bootId']):
        raise ValueError('Device restarted during telemetry collection')
    return dict(schema=1,identitySource='firmware-report',telemetry='available',hardware=hardware)
