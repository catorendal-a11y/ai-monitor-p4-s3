"""Strict standalone target measurements; not a runtime companion-pack parser."""
import json
import re
import time

POSES=('work','done','low','critical','sleep','blink')
CODECS=('raw','rle','lz4','deflate')
FIELDS=('type','schema','robot','pose','codec','encodedBytes','decodedBytes','samples',
    'medianDecodeUs','bitExact','outputBufferBytes','decoderStateBytes','cpuMHz','decodedSha256')


def validate_asset(data):
    if not isinstance(data,dict) or not set(FIELDS).issubset(data) or data['type']!='asset_benchmark' or type(data['schema']) is not int or data['schema']!=1:
        raise ValueError('Unsupported asset measurement')
    if data['robot'] not in ('nova','orbit') or data['pose'] not in POSES or data['codec'] not in CODECS:
        raise ValueError('Invalid fixture identity')
    for key in ('encodedBytes','decodedBytes','samples','medianDecodeUs','outputBufferBytes','decoderStateBytes','cpuMHz'):
        if type(data[key]) is not int or not 0<=data[key]<=0xffffffff:raise ValueError('Invalid asset metric')
    if type(data['bitExact']) is not bool:raise ValueError('Invalid pixel comparison')
    if not 0<data['encodedBytes']<=400000 or not 0<data['decodedBytes']<=366360 or data['decodedBytes']%3:
        raise ValueError('Invalid frame size')
    if not data['decodedBytes']<=data['outputBufferBytes']<=366360 or data['decoderStateBytes']>32768 or not 1<=data['cpuMHz']<=400:
        raise ValueError('Invalid buffer budget')
    if data['codec']=='raw' and data['encodedBytes']!=data['decodedBytes']:raise ValueError('Invalid raw size')
    if data['samples']>5 or (data['bitExact'] and (data['samples']!=5 or data['medianDecodeUs']==0)):
        raise ValueError('Incomplete measurement')
    digest=data['decodedSha256']
    if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):raise ValueError('Invalid pixel digest')
    return {key:data[key] for key in FIELDS}


def collect_assets(connection,robot,clock=time.monotonic,cache_report=None):
    if robot not in ('nova','orbit'):raise ValueError('Choose a benchmark companion')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate asset field')
            result[key]=value
        return result
    began=clock();next_query=began
    line=bytearray();dropping=False;rows={}
    while clock()-began<30:
        now=clock()
        if now>=next_query and not rows:
            if connection.write(b'assets\n')!=7:raise OSError('Incomplete benchmark query')
            next_query=now+.5
        for byte in connection.read(256):
            if byte==10:
                raw=bytes(line);line.clear();discarded=dropping;dropping=False
                if discarded or not raw.startswith(b'{'):continue
                try:data=json.loads(raw,object_pairs_hook=unique)
                except (ValueError,RecursionError):raise ValueError('Malformed asset response') from None
                if not isinstance(data,dict):continue
                if data.get('type')=='asset_benchmark_error':raise ValueError('Target benchmark failed')
                if data.get('type')=='asset_benchmark':
                    value=validate_asset(data);key=(value['pose'],value['codec'])
                    if value['robot']!=robot or key in rows:raise ValueError('Wrong or duplicate fixture')
                    rows[key]=value
                elif data.get('type')=='asset_cache':
                    fields=('type','schema','loads','allocatedBytes','totalLoadUs','hashRejected','decodeRejected','pinPreserved')
                    if not set(fields).issubset(data) or type(data['schema']) is not int or data['schema']!=1:
                        raise ValueError('Invalid cache report')
                    for key,limit in (('loads',6),('allocatedBytes',732800),('totalLoadUs',30000000)):
                        if type(data[key]) is not int or not 0<=data[key]<=limit:raise ValueError('Invalid cache metric')
                    if any(type(data[key]) is not bool for key in ('hashRejected','decodeRejected','pinPreserved')):
                        raise ValueError('Invalid cache state')
                    if cache_report is not None:
                        if cache_report:raise ValueError('Duplicate cache result')
                        cache_report.update({key:data[key] for key in fields})
                elif data.get('type')=='asset_benchmark_end':
                    if type(data.get('schema')) is not int or data['schema']!=1 or type(data.get('count')) is not int or data['count']!=24 or len(rows)!=24:
                        raise ValueError('Incomplete benchmark batch')
                    result=[rows[(pose,codec)] for pose in POSES for codec in CODECS]
                    if any(not row['bitExact'] for row in result):raise ValueError('Decoded pixels do not match')
                    for pose in POSES:
                        group=[rows[(pose,codec)] for codec in CODECS]
                        if len({(row['decodedSha256'],row['decodedBytes']) for row in group})!=1:
                            raise ValueError('Codecs did not use identical pixels')
                    return result
            elif not dropping:
                if len(line)==2048:line.clear();dropping=True
                else:line.append(byte)
    raise TimeoutError('Target asset benchmark did not finish')
