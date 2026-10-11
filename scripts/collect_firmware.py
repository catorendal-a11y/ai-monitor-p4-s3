"""Collect a matched board-specific firmware pair after a successful build."""
import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from board_profiles import BOARDS
from firmware_layout import validate_factory
from project_version import fw_version


def latest_factory(build):
    """Newest factory image of this build, or a clear error when none exists."""
    candidates = list(build.glob('fw_*.factory.bin'))
    if not candidates:
        raise ValueError('No factory image was produced by this build; '
                         'run the matching PlatformIO environment first')
    return max(candidates, key=lambda path: path.stat().st_mtime)


def collect(environment, output):
    board = next((item for item in BOARDS.values() if item.environment == environment), None)
    if board is None: raise ValueError('Unknown firmware build target')
    build = ROOT / '.pio/build-fw' / environment
    factory = latest_factory(build)
    application = factory.with_name(factory.name.replace('.factory.bin', '.bin'))
    version = fw_version(ROOT)
    if version.encode() not in application.read_bytes(): raise ValueError('Application does not match current firmware version')
    validate_factory(factory.read_bytes(), application.read_bytes(), board)
    folder = output / board.id
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(application, folder / 'application.bin')
    shutil.copy2(factory, folder / 'factory.bin')
    print('Collected ' + board.name + ' (' + version + ')')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', required=True, choices=[item.environment for item in BOARDS.values()])
    parser.add_argument('--output', type=Path, default=ROOT/'work/prebuilt')
    args = parser.parse_args()
    collect(args.environment, args.output.resolve())
