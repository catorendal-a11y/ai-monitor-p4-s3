"""Export trusted committed NOVA/ORBIT pixels as verified version-2 external packs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile
import lz4.block
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from companion_packages import parse_archive
from project_version import fw_version
POSES=('work','done','low','critical','sleep','blink')


def build(robot,output):
    if robot not in ('nova','orbit'):raise ValueError('Choose NOVA or ORBIT')
    source=(ROOT/'src/ui/nova_assets.cpp').read_text(encoding='utf-8')
    header=(ROOT/'src/ui/nova_assets.h').read_text(encoding='utf-8')
    origins=[int(re.search(robot+r'_origin_'+axis+r' = (\d+)',header)[1]) for axis in ('x','y')]
    frames=[];files={}
    for pose in POSES:
        symbol=('orbit_' if robot=='orbit' else '')+pose
        array=re.search(r'const uint8_t '+symbol+r'_pixels\[\] = \{(.*?)\};',source,re.S)
        geometry=re.search(r'const lv_image_dsc_t '+symbol+r' = \{ \{LV_IMAGE_HEADER_MAGIC, LV_COLOR_FORMAT_RGB565A8, 0, (\d+), (\d+),',source)
        if not array or not geometry:raise ValueError('Committed companion source is incomplete')
        raw=bytes(int(value,16) for value in re.findall(r'0x([0-9a-fA-F]{2})',array[1]))
        width,height=map(int,geometry.groups())
        if len(raw)!=width*height*3:raise ValueError('Committed companion pixel count is invalid')
        encoded=lz4.block.compress(raw,store_size=False)
        filename=pose+'.lz4';files[filename]=encoded
        frames.append(dict(id=pose,file=filename,width=width,height=height,originX=origins[0],originY=origins[1],
            encodedBytes=len(encoded),decodedBytes=len(raw),encodedSha256=hashlib.sha256(encoded).hexdigest(),
            decodedSha256=hashlib.sha256(raw).hexdigest()))
    clips=[]
    animation=(ROOT/'src/companions/builtin_animation.h').read_text()
    for mood,loop,count,steps in re.findall(r'\{Mood::(\w+),(true|false),(\d+),\{(.*?)\}\}',animation):
        sequence=[dict(id=POSES[int(index)],durationMs=int(duration)) for index,duration in re.findall(r'(\d+),(\d+)',steps)]
        if len(sequence)!=int(count):raise ValueError('Committed companion timing is invalid')
        clips.append(dict(mood=mood,loop=loop=='true',frames=sequence))
    if len(clips)!=8:raise ValueError('Committed companion animations are incomplete')
    manifest=dict(version=2,name=robot.upper()+' PACK',format='RGB565A8',codec='lz4',fallback='resting',
                  frames=frames,animations=clips)
    files['manifest.json']=json.dumps(manifest,separators=(',',':')).encode('ascii')
    files['LICENSE']=(ROOT/'LICENSE').read_bytes()
    files['README.md']=(robot.upper()+' original companion export / '+fw_version(ROOT)+'\n'
        'Original project artwork, MIT license. Version-2 RGB565A8/LZ4 animations.\n'
        'Import through the LimitBuddy Companions tab on supported P4 firmware.\n').encode('ascii')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    target=output/(robot+'-'+fw_version(ROOT)+'.aimcompanion')
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,files[name])
    parse_archive(target.read_bytes())
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    for robot in ('nova','orbit'):print(build(robot,args.output))
