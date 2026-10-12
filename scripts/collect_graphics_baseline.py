"""Collect a read-only interval from explicitly enabled graphics telemetry firmware."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from board_profiles import BOARDS
from aim_host import Panel
from hardware_baseline import collect
from graphics_baseline import validate_graphics,interval
from host_security import serial_port


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board',required=True,choices=BOARDS)
    parser.add_argument('--port',required=True)
    parser.add_argument('--seconds',type=int,default=10)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if not 1<=args.seconds<=60: parser.error('Use an interval of 1-60 seconds')
    port=serial_port(args.port)
    if port=='auto': parser.error('Choose an explicit port and stop its host first')
    panel=None
    try:
        panel=Panel(port); baseline=collect(panel,args.board)
        def sample():
            panel.send_line('{"cmd":"get_graphics"}'); return validate_graphics(panel.wait_for('graphics',seconds=3))
        first=sample()
        if not first['enabled']: raise ValueError('Use an explicitly enabled graphics build')
        time.sleep(args.seconds)
        last=sample(); measurement=interval(first,last)
        if measurement is None: raise ValueError('Invalid graphics interval or reboot')
        result=dict(schema=1,baseline=baseline,first=first,last=last,interval=measurement)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print('Graphics interval saved. Physical scanout FPS and PPA performance are not measured by these counters.')
        return 0
    except (ValueError,OSError,RuntimeError):
        print('Graphics interval unavailable. Check the explicit port and diagnostic build.',file=sys.stderr); return 1
    finally:
        if panel is not None: panel.close()


if __name__=='__main__': sys.exit(main())
