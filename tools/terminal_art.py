"""Small original NOVA rasters rendered as RGB half-blocks, without GUI libraries."""
import base64
from functools import lru_cache
import json
from pathlib import Path
import zlib
import sys
from rich.style import Style
from rich.text import Text


@lru_cache(maxsize=4)
def pixels(pose):
    root=Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
    path=root/'assets/terminal/nova.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    width,height=data['width'],data['height']
    if (width,height)!=(40,26):raise ValueError('Unexpected terminal artwork dimensions')
    raw=zlib.decompress(base64.b85decode(data['frames'][pose]))
    if len(raw)!=width*height*3:raise ValueError('Unexpected terminal artwork bytes')
    return width,height,raw


LIFT=1.45       # how strongly the robot is pulled away from the panel colour it was drawn on
LIFT_FLOOR=6    # colour distance below which a pixel is background glow and stays untouched


def lifted(raw,width,height):
    """The artwork is dark teal on a dark panel; amplify its difference from the background so it reads."""
    base=raw[:3];out=bytearray(raw)
    for offset in range(0,len(raw),3):
        pixel=raw[offset:offset+3]
        if sum(abs(pixel[i]-base[i]) for i in range(3))<LIFT_FLOOR:continue
        for i in range(3):out[offset+i]=max(0,min(255,round(base[i]+(pixel[i]-base[i])*LIFT)))
    return bytes(out)


def nova_cells(pose,rows=6):
    """One terminal row holds two square pixels; preserve the source aspect ratio."""
    rows=max(2,min(10,rows));columns=round(rows*2*40/26)
    try:width,height,raw=pixels(pose)
    except (OSError,ValueError,KeyError):return Text('NOVA',style='bold #95ffc2')
    raw=lifted(raw,width,height)
    text=Text()
    def color(x,y):
        offset=(y*width+x)*3
        return '#'+raw[offset:offset+3].hex()
    for y in range(rows):
        for x in range(columns):
            px=x*width//columns
            text.append('▀',Style(color=color(px,y*2*height//(rows*2)),
                                  bgcolor=color(px,(y*2+1)*height//(rows*2))))
        if y<rows-1:text.append('\n')
    return text
