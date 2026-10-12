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
    return result


def collect(panel,board_id):
    board=get_board(board_id)
    panel.send_line('{"cmd":"get_info"}')
    info=panel.wait_for('info')
    if not matches_info(board,info): raise ValueError('Device identity mismatch')
    panel.send_line('{"cmd":"get_hardware"}')
    try: reply=panel.wait_for('hardware',seconds=3)
    except RuntimeError:
        return dict(schema=1,identitySource='firmware-report',boardId=board.id,chip=board.chip,
            telemetry='unavailable-in-installed-firmware',hosted=dict(probeState='not-probed'),ppa=dict(active=False))
    return dict(schema=1,identitySource='firmware-report',telemetry='available',hardware=validate_hardware(reply,board_id))
