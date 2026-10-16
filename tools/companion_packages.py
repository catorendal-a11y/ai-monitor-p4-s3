"""Bounded data-only companions. Never extract archives or execute package content."""
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
import zipfile
from itertools import islice

MAX_BLOB=2*1024*1024
MAX_ARCHIVE=4*1024*1024
MOODS=frozenset(('resting','working','testing','attention','success','error','warning','critical'))


@dataclass(frozen=True)
class Pack:
    id:str
    name:str
    blob:bytes
    manifest:dict


def pairs(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError('Duplicate companion field')
        result[key]=value
    return result


def fields(value,expected):
    if not isinstance(value,dict) or set(value)!=set(expected.split()):
        raise ValueError('Invalid companion fields')


def integer(value,low,high):
    if type(value) is not int or not low<=value<=high:raise ValueError('Invalid companion number')
    return value


def filename(value):
    if (not isinstance(value,str) or not re.fullmatch('[a-z0-9_-][a-z0-9_.-]{0,47}',value)
            or '..' in value or value.split('.')[0] in
            {'con','prn','aux','nul',*(f'com{i}' for i in range(1,10)),*(f'lpt{i}' for i in range(1,10))}):
        raise ValueError('Invalid companion filename')
    return value


def manifest_from(raw):
    if len(raw)>8192:raise ValueError('Companion manifest too large')
    try:m=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs)
    except (UnicodeError,ValueError,RecursionError) as error:raise ValueError('Invalid companion manifest') from error
    fields(m,'version name format codec fallback frames animations')
    if type(m['version']) is not int or m['version']!=2 or m['format']!='RGB565A8' or m['codec'] not in ('raw','lz4'):
        raise ValueError('Unsupported companion format')
    if not isinstance(m['name'],str) or not re.fullmatch('[A-Za-z0-9_ -]{1,32}',m['name']):raise ValueError('Invalid companion name')
    if type(m['frames']) is not list or not 1<=len(m['frames'])<=16:raise ValueError('Invalid companion frames')
    ids=set();names=set();geometry=None;total=0
    for frame in m['frames']:
        fields(frame,'id file width height originX originY encodedBytes decodedBytes encodedSha256 decodedSha256')
        if not isinstance(frame['id'],str) or not re.fullmatch('[a-z0-9_-]{1,24}',frame['id']):raise ValueError('Invalid companion frame ID')
        filename(frame['id'])
        name=filename(frame['file'])
        if frame['id'] in ids or name in names:raise ValueError('Duplicate companion frame')
        ids.add(frame['id']);names.add(name)
        if not name.endswith('.raw' if m['codec']=='raw' else '.lz4'):raise ValueError('Wrong companion codec extension')
        w=integer(frame['width'],1,430);h=integer(frame['height'],1,284)
        x=integer(frame['originX'],0,429);y=integer(frame['originY'],0,283)
        if x+w>430 or y+h>284 or (geometry is not None and geometry!=(w,h,x,y)):
            raise ValueError('Invalid companion crop')
        geometry=(w,h,x,y)
        count=integer(frame['encodedBytes'],1,430*284*3+64)
        if integer(frame['decodedBytes'],1,430*284*3)!=w*h*3 or (m['codec']=='raw' and count!=w*h*3):
            raise ValueError('Invalid companion frame size')
        for key in ('encodedSha256','decodedSha256'):
            if not isinstance(frame[key],str) or not re.fullmatch('[0-9a-f]{64}',frame[key]):raise ValueError('Invalid companion hash')
        total+=count
    if total+len(raw)+4>MAX_BLOB:raise ValueError('Companion exceeds device capacity')
    if type(m['animations']) is not list or not 1<=len(m['animations'])<=8:raise ValueError('Invalid companion animations')
    moods=set()
    for clip in m['animations']:
        fields(clip,'mood loop frames')
        if not isinstance(clip['mood'],str) or clip['mood'] not in MOODS or clip['mood'] in moods or type(clip['loop']) is not bool:
            raise ValueError('Invalid companion mood')
        moods.add(clip['mood'])
        if type(clip['frames']) is not list or not 1<=len(clip['frames'])<=16:raise ValueError('Invalid companion sequence')
        for step in clip['frames']:
            fields(step,'id durationMs')
            if not isinstance(step['id'],str) or step['id'] not in ids:raise ValueError('Unknown companion frame')
            integer(step['durationMs'],40,60000)
    if not isinstance(m['fallback'],str) or m['fallback'] not in moods:raise ValueError('Missing companion fallback')
    return m


def parse_blob(blob):
    if not isinstance(blob,bytes) or not 5<=len(blob)<=MAX_BLOB:raise ValueError('Invalid companion payload size')
    length=struct.unpack_from('<I',blob)[0]
    if not 1<=length<=8192 or 4+length>len(blob):raise ValueError('Invalid companion manifest size')
    m=manifest_from(blob[4:4+length]);offset=4+length
    for frame in m['frames']:
        end=offset+frame['encodedBytes']
        encoded=blob[offset:end];offset=end
        if len(encoded)!=frame['encodedBytes'] or hashlib.sha256(encoded).hexdigest()!=frame['encodedSha256']:
            raise ValueError('Companion frame checksum mismatch')
        if m['codec']=='lz4':
            import lz4.block
            try:decoded=lz4.block.decompress(encoded,uncompressed_size=frame['decodedBytes'])
            except lz4.block.LZ4BlockError as error:raise ValueError('Invalid companion compression') from error
        else:decoded=encoded
        if len(decoded)!=frame['decodedBytes'] or hashlib.sha256(decoded).hexdigest()!=frame['decodedSha256']:
            raise ValueError('Companion decoded checksum mismatch')
    if offset!=len(blob):raise ValueError('Unexpected companion data')
    return Pack(hashlib.sha256(blob).hexdigest(),m['name'],blob,m)


def parse_archive(raw):
    if not isinstance(raw,bytes) or len(raw)>MAX_ARCHIVE:raise ValueError('Companion archive too large')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            items=archive.infolist();names=[item.filename for item in items]
            if not 2<=len(items)<=19 or len(names)!=len(set(names)) or 'manifest.json' not in names:
                raise ValueError('Invalid companion archive entries')
            if sum(item.file_size for item in items)>MAX_BLOB+131072:raise ValueError('Companion archive expands too far')
            for item in items:
                if (item.flag_bits&1 or item.is_dir() or stat.S_ISLNK(item.external_attr>>16)
                        or item.file_size>MAX_BLOB or '/' in item.filename or '\\' in item.filename):
                    raise ValueError('Unsafe companion archive entry')
            info=archive.getinfo('manifest.json')
            if info.file_size>8192:raise ValueError('Companion manifest too large')
            manifest=archive.read(info);m=manifest_from(manifest)
            expected={'manifest.json',*(f['file'] for f in m['frames'])}
            if set(names)-expected-{'LICENSE','README.md'} or not expected<=set(names):raise ValueError('Unexpected companion archive entry')
            for name in ('LICENSE','README.md'):
                if name in names and archive.getinfo(name).file_size>65536:raise ValueError('Companion notice too large')
            blob=struct.pack('<I',len(manifest))+manifest
            for frame in m['frames']:
                if archive.getinfo(frame['file']).file_size!=frame['encodedBytes']:raise ValueError('Wrong companion asset size')
                blob+=archive.read(frame['file'])
            return parse_blob(blob)
    except (zipfile.BadZipFile,KeyError,NotImplementedError,RuntimeError,OverflowError) as error:
        raise ValueError('Invalid companion archive') from error


def directory(root,create=True):
    root=Path(root);path=root/'tools/companions'
    if path.is_symlink() or path.parent.is_symlink():raise ValueError('Invalid companion library')
    if create:path.mkdir(parents=True,exist_ok=True)
    return path


def write(path,data):
    if path.is_symlink():raise ValueError('Invalid companion library entry')
    descriptor,temporary=tempfile.mkstemp(prefix='.pack-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def install(root,source):
    with Path(source).open('rb') as stream:raw=stream.read(MAX_ARCHIVE+1)
    pack=parse_archive(raw);folder=directory(root)
    if not (folder/(pack.id+'.pack')).exists() and sum(1 for _ in islice(folder.glob('*.pack'),16))>=16:
        raise ValueError('Companion library is full; remove an unused pack first')
    write(folder/(pack.id+'.zip'),raw) # Keep author notices with the original archive.
    write(folder/(pack.id+'.pack'),pack.blob)
    return pack


def load(root,identifier):
    if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{64}',identifier):raise ValueError('Invalid companion selection')
    path=directory(root,create=False)/(identifier+'.pack')
    if path.is_symlink():raise ValueError('Invalid companion library entry')
    with path.open('rb') as stream:blob=stream.read(MAX_BLOB+1)
    pack=parse_blob(blob)
    if pack.id!=identifier:raise ValueError('Companion library checksum mismatch')
    return pack


def select(root,identifier):
    if identifier!='':load(root,identifier)
    write(directory(root)/'selection.json',json.dumps({'id':identifier}).encode('ascii'))


def selected(root):
    path=directory(root,create=False)/'selection.json'
    if not path.exists():return ''
    if path.is_symlink():raise ValueError('Invalid companion selection')
    with path.open('rb') as stream:raw=stream.read(129)
    if len(raw)>128:raise ValueError('Invalid companion selection')
    value=json.loads(raw,object_pairs_hook=pairs);fields(value,'id')
    identifier=value['id']
    if identifier!='' and (not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{64}',identifier)):
        raise ValueError('Invalid companion selection')
    return identifier


def remove(root,identifier):
    if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{64}',identifier):raise ValueError('Invalid companion selection')
    if selected(root)==identifier:raise ValueError('Choose built-in or another pack before removal')
    folder=directory(root,create=False)
    paths=[folder/(identifier+suffix) for suffix in ('.pack','.zip')]
    if any(path.is_symlink() for path in paths):raise ValueError('Invalid companion library entry')
    for path in paths:path.unlink(missing_ok=True)
