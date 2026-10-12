"""Collect bounded read-only telemetry on an explicitly selected USB port."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from board_profiles import BOARDS
from host_security import serial_port
from aim_host import Panel
from hardware_baseline import collect


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board',required=True,choices=BOARDS)
    parser.add_argument('--port',required=True)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    port=serial_port(args.port)
    if port=='auto': parser.error('Select an explicit port. Stop its host before collecting.')
    panel=None
    try:
        panel=Panel(port); result=collect(panel,args.board)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print('Read-only baseline saved. No flash, radio initialization, keys or conversation reads.')
        return 0
    except (ValueError,OSError,RuntimeError):
        print('Baseline unavailable. Check the exact board/port and stop its host before retrying.',file=sys.stderr)
        return 1
    finally:
        if panel is not None: panel.close()


if __name__=='__main__': sys.exit(main())
