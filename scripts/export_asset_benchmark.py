"""Generate trusted standalone target fixtures; no runtime pack format is selected."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from benchmark_asset_codecs import ROOT, build_codecs, encode_frame

POSES = ('work', 'done', 'low', 'critical', 'sleep', 'blink')


def trusted_frames(folder):
    folder = Path(folder).resolve()
    with (folder/'frames.json').open('rb') as stream:
        data = json.loads(stream.read(16385))
    if (not isinstance(data, dict) or type(data.get('schema')) is not int or data['schema'] != 1
            or data.get('format') != 'RGB565A8' or not isinstance(data.get('frames'), list)
            or len(data['frames']) != 12): raise ValueError('Expected twelve exported RGB565A8 frames')
    seen = set(); result = []
    for frame in data['frames']:
        if not isinstance(frame, dict): raise ValueError('Invalid frame metadata')
        robot, pose = frame.get('robot'), frame.get('pose')
        if robot not in ('nova', 'orbit') or pose not in POSES or (robot, pose) in seen:
            raise ValueError('Invalid or duplicate companion pose')
        seen.add((robot, pose))
        name = robot+'-'+pose+'.rgb565a8'
        if frame.get('file') != name: raise ValueError('Invalid benchmark filename')
        if any(type(frame.get(key)) is not int for key in ('width', 'height', 'originX', 'originY', 'decodedBytes')):
            raise ValueError('Invalid frame geometry')
        w,h,x,y = (frame[key] for key in ('width','height','originX','originY'))
        if not (0<w<=430 and 0<h<=284 and 0<=x<=430-w and 0<=y<=284-h) or frame['decodedBytes']!=w*h*3:
            raise ValueError('Frame exceeds the companion canvas')
        digest=frame.get('sha256')
        if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest): raise ValueError('Invalid frame digest')
        path=folder/name
        if not path.resolve().is_relative_to(folder): raise ValueError('Frame escaped input directory')
        with path.open('rb') as stream: raw=stream.read(frame['decodedBytes']+1)
        if len(raw)!=frame['decodedBytes'] or hashlib.sha256(raw).hexdigest()!=digest:
            raise ValueError('Frame bytes do not match the trusted export')
        result.append((dict(robot=robot,pose=pose,decodedBytes=len(raw),sha256=digest,
            width=w,height=h,originX=x,originY=y),raw))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames',required=True,type=Path)
    parser.add_argument('--robot',required=True,choices=('nova','orbit'))
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--cc',default='gcc')
    args=parser.parse_args()
    compiler=shutil.which(args.cc)
    if not compiler: parser.error('A native C compiler is required for pinned LZ4')
    frames=trusted_frames(args.frames)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    scratch=ROOT/'work';scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='asset-target-export-',dir=scratch) as directory:
        codec=build_codecs(Path(directory),compiler)
        try:
            with args.output.open('w',encoding='ascii',newline='\n') as stream:
                stream.write('// Generated trusted benchmark data; never exported as a runtime pack.\n#pragma once\n')
                records=[]
                for frame,raw in frames:
                    if frame['robot']!=args.robot: continue
                    for name,encoded in encode_frame(raw,codec).items():
                        symbol='fixture_'+frame['pose']+'_'+name
                        stream.write('static const uint8_t '+symbol+'[]={\n')
                        for offset in range(0,len(encoded),32):
                            stream.write(','.join(str(byte) for byte in encoded[offset:offset+32])+',\n')
                        stream.write('};\n')
                        records.append('{"'+args.robot+'","'+frame['pose']+'",AssetCodec::'+name+','+
                            symbol+',sizeof('+symbol+'),'+str(len(raw))+',"'+frame['sha256']+'","'+
                            hashlib.sha256(encoded).hexdigest()+'",'+','.join(str(frame[key]) for key in
                            ('width','height','originX','originY'))+'}')
                stream.write('static const AssetFixture fixtures[]={\n'+',\n'.join(records)+'\n};\n')
        finally:
            if __import__('os').name=='nt':
                import _ctypes
                _ctypes.FreeLibrary(codec._handle)
        print('Generated 24 trusted target fixtures for '+args.robot+'.')


if __name__=='__main__': main()
