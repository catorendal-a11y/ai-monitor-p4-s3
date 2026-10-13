"""Run a standalone trusted-fixture benchmark; no firmware writes or runtime pack selection."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import serial
from host_security import serial_port
from asset_baseline import collect_assets


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--robot',required=True,choices=('nova','orbit'))
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();port=serial_port(args.port)
    if port=='auto':parser.error('Select the identified P4 port and stop its host first')
    try:
        cache={}
        with serial.Serial(port,115200,timeout=.2,write_timeout=2) as connection:
            rows=collect_assets(connection,args.robot,cache_report=cache)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(dict(schema=1,mode='physical target; standalone trusted fixtures',
            robot=args.robot,hashingExcludedFromDecodeTime=True,frames=rows,cache=cache),indent=2)+'\n',encoding='utf-8')
        print('All 24 target results saved with exact pixels. No runtime format was changed.')
        return 0
    except (ValueError,OSError,TimeoutError):
        print('Target benchmark unavailable or inconsistent. No result was published.',file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
