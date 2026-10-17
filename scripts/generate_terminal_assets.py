"""Generate small terminal rasters from original NOVA vectors (development only)."""
import base64
import json
import os
from pathlib import Path
import zlib

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QRectF
from PySide6.QtGui import QGuiApplication,QImage,QPainter
from PySide6.QtSvg import QSvgRenderer

root=Path(__file__).resolve().parents[1]
app=QGuiApplication([])
width,height=40,26
frames={}
for pose in ('work','attention','error','done'):
    renderer=QSvgRenderer(str(root/'assets/nova'/f'{pose}.svg'))
    assert renderer.isValid()
    image=QImage(width,height,QImage.Format.Format_RGB32)
    image.fill(0x13231f)
    painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter,QRectF(0,0,width,height));painter.end()
    pixels=bytes(channel for y in range(height) for x in range(width)
                 for channel in (image.pixelColor(x,y).red(),image.pixelColor(x,y).green(),image.pixelColor(x,y).blue()))
    frames[pose]=base64.b85encode(zlib.compress(pixels,9)).decode('ascii')
target=root/'assets/terminal';target.mkdir(exist_ok=True)
(target/'nova.json').write_text(json.dumps(dict(width=width,height=height,frames=frames),indent=2)+'\n',encoding='utf-8')
print('Generated four original NOVA poses for terminal cells; no runtime Qt dependency.')
