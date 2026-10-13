"""Read the standalone P4/C6 test; never flash, retry initialization or create BLE services."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import serial
from host_security import serial_port
from c6_baseline import collect_probe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    port = serial_port(args.port)
    if port == 'auto': parser.error('Choose the identified P4 port and stop its host first')
    try:
        with serial.Serial(port, 115200, timeout=0.2, write_timeout=2) as connection:
            result = collect_probe(connection)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print('Standalone result saved: ' + result['stage'] + '. Controller RPC is not a BLE pairing test.')
        return 0
    except (OSError, ValueError, TimeoutError):
        print('Probe unavailable. Use the standalone C6 test on the explicitly identified P4 port.', file=sys.stderr)
        return 1


if __name__ == '__main__': sys.exit(main())
