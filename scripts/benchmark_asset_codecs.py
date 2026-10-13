"""Host-only codec comparison using the pinned LVGL sources. Not an ESP32 timing result."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile
import time
import zlib

ROOT=Path(__file__).resolve().parents[1]


def rle_encode(raw):
    output=bytearray(); index=0
    def run(at):
        end=at+1
        while end<len(raw) and end-at<127 and raw[end]==raw[at]: end+=1
        return end-at
    while index<len(raw):
        count=run(index)
        if count>=3:
            output.extend((count,raw[index])); index+=count
        else:
            first=index; index+=count
            while index<len(raw) and index-first<127 and run(index)<3: index+=1
            output.append(0x80|(index-first)); output.extend(raw[first:index])
    return bytes(output)


def build_codecs(directory,compiler):
    lvgl=ROOT/'.pio/libdeps/esp32p4-release/lvgl'
    shim=directory/'stdlib_shim.c'
    shim.write_text('#include <stddef.h>\n#include <stdint.h>\n#include <string.h>\n'
        'void* lv_memcpy(void* d,const void* s,size_t n){return memcpy(d,s,n);}\n'
        'void* lv_memmove(void* d,const void* s,size_t n){return memmove(d,s,n);}\n'
        'void lv_memset(void* d,uint8_t v,size_t n){memset(d,v,n);}\n')
    library=directory/('codecs.dll' if __import__('os').name=='nt' else 'codecs.so')
    subprocess.run([compiler,'-shared','-O2','-fPIC','-DLV_USE_LZ4_INTERNAL=1','-DLV_USE_RLE=1',
        '-DLV_CONF_INCLUDE_SIMPLE=1','-I',str(ROOT/'lib'),'-I',str(lvgl),
        str(lvgl/'src/libs/lz4/lz4.c'),str(lvgl/'src/libs/rle/lv_rle.c'),str(shim),'-o',str(library)],check=True)
    codec=ctypes.CDLL(str(library))
    codec.LZ4_compressBound.argtypes=[ctypes.c_int];codec.LZ4_compressBound.restype=ctypes.c_int
    codec.LZ4_compress_default.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int]
    codec.LZ4_compress_default.restype=ctypes.c_int
    codec.LZ4_decompress_safe.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int]
    codec.LZ4_decompress_safe.restype=ctypes.c_int
    codec.lv_rle_decompress.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint8]
    codec.lv_rle_decompress.restype=ctypes.c_uint32
    return codec


def encode_frame(raw,codec):
    source=ctypes.create_string_buffer(raw)
    target=ctypes.create_string_buffer(codec.LZ4_compressBound(len(raw)))
    count=codec.LZ4_compress_default(source,target,len(raw),len(target))
    if count<=0: raise ValueError('LZ4 compression failed')
    return dict(raw=raw,rle=rle_encode(raw),lz4=target.raw[:count],deflate=zlib.compress(raw,9))


def compare_frame(raw,codec):
    decoded=ctypes.create_string_buffer(len(raw))
    encoded=encode_frame(raw,codec)
    result={}
    for name,data in encoded.items():
        compressed=ctypes.create_string_buffer(data)
        def decode():
            if name=='lz4':
                n=codec.LZ4_decompress_safe(compressed,decoded,len(data),len(raw))
                if n!=len(raw): raise ValueError('LZ4 decode failed')
                return decoded.raw
            if name=='rle':
                n=codec.lv_rle_decompress(compressed,len(data),decoded,len(raw),1)
                if n!=len(raw): raise ValueError('RLE decode failed')
                return decoded.raw
            if name=='deflate': return zlib.decompress(data)
            return memoryview(data).tobytes()
        if decode()!=raw: raise ValueError('Codec changed source pixels')
        timings=[]
        for _ in range(20):
            started=time.perf_counter_ns(); decode(); timings.append((time.perf_counter_ns()-started)/1000)
        result[name]=dict(encodedBytes=len(data),hostMedianDecodeUs=statistics.median(timings),
            decodedSha256=hashlib.sha256(raw).hexdigest(),encodedSha256=hashlib.sha256(data).hexdigest())
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--cc',default='gcc')
    args=parser.parse_args(); compiler=shutil.which(args.cc)
    if not compiler: parser.error('C compiler required for the pinned native codecs')
    folder=args.frames.resolve()
    with (folder/'frames.json').open('rb') as stream: metadata=json.loads(stream.read(16385))
    if metadata.get('schema')!=1 or len(metadata.get('frames',[]))!=12: parser.error('Export the 12 trusted frames first')
    scratch=ROOT/'work'; scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='codec-benchmark-',dir=scratch) as temporary:
        codec=build_codecs(Path(temporary),compiler); frames=[]
        try:
            for frame in metadata['frames']:
                file=folder/frame['file']
                if file.name!=frame['file'] or not file.resolve().is_relative_to(folder): raise ValueError('Invalid frame path')
                size=frame['decodedBytes']
                if type(size) is not int or not 0<size<=512*1024: raise ValueError('Invalid decoded size')
                with file.open('rb') as stream: raw=stream.read(size+1)
                if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=frame['sha256']: raise ValueError('Frame hash mismatch')
                frames.append(dict(frame,codecs=compare_frame(raw,codec)))
        finally:
            # Also release the temporary DLL on validation/decode failure.
            if __import__('os').name=='nt':
                import _ctypes
                _ctypes.FreeLibrary(codec._handle)
            del codec
    totals={name:sum(f['codecs'][name]['encodedBytes'] for f in frames) for name in ('raw','rle','lz4','deflate')}
    delivery={}
    for name in totals:
        manifest=json.dumps(dict(schema=1,codec=name,format='RGB565A8',frames=[dict(
            {k:f[k] for k in ('robot','pose','width','height','originX','originY','decodedBytes','sha256')},
            file=f['robot']+'-'+f['pose']+'.'+name,encodedBytes=f['codecs'][name]['encodedBytes'],
            encodedSha256=f['codecs'][name]['encodedSha256']) for f in frames]),separators=(',',':')).encode()
        delivery[name]=dict(payloadBytes=totals[name],manifestBytes=len(manifest),
            prototypeFolderBytes=totals[name]+len(manifest),fitsConservativeDesktopLimit=totals[name]+len(manifest)<1800000)
    result=dict(schema=1,mode='host-only; pinned codecs and stdlib shim; not ESP32 timings',
        targetDecodeMeasurements='pending physical hardware benchmark',runtimeFormatDecision='provisional; no production format changed',
        frames=frames,totals=totals,prototypeDelivery=delivery)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(mode=result['mode'],totals=totals,prototypeDelivery=delivery)))


if __name__=='__main__': main()
